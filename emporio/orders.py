"""Order tools: status lookup and return/exchange eligibility.

Order data is personal, so every call needs the order number AND a contact
(e-mail or phone) that belongs to the customer who placed that order. The
contact is checked against the order's own customer, not looked up on its own:
two customers in the sample data share the same e-mail address.
"""

import re
import sqlite3
from datetime import date

from emporio import clock, pricing

RETURN_WINDOW_DAYS = 7        # manual 4.1 and 4.3, counted from receipt
DEFECT_EXCHANGE_DAYS = 30     # manual 4.2, counted from purchase
LEGAL_WARRANTY_DAYS = 90      # manual 8.1, counted from receipt

STATUS_TEXT = {
    "pending": "Aguardando confirmação do pagamento",
    "confirmed": "Pagamento confirmado, pedido em preparação",
    "shipped": "Enviado",
    "delivered": "Entregue",
    "cancelled": "Cancelado",
}
PAYMENT_TEXT = {"pix": "PIX", "boleto": "Boleto", "debit": "Cartão de débito"}

NOT_FOUND = {
    "verified": False,
    "message": "Não encontrei um pedido com esses dados. Peça ao cliente para conferir o "
               "número do pedido e o e-mail ou telefone usados na compra.",
}


def _digits(text: str) -> str:
    digits = re.sub(r"\D", "", text or "")
    return digits[2:] if digits.startswith("55") and len(digits) > 11 else digits


def _contact_matches(customer: sqlite3.Row, contact: str) -> bool:
    contact = (contact or "").strip()
    if "@" in contact:
        return contact.lower() == (customer["email"] or "")
    digits = _digits(contact)
    return len(digits) >= 10 and digits == customer["phone_digits"]


def _verified_order(conn, order_id, contact):
    """Return (order, customer) when the contact owns the order, else None.
    Missing order and wrong contact are indistinguishable to the caller."""
    order = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    if order is None:
        return None
    customer = conn.execute("SELECT * FROM customers WHERE customer_id = ?",
                            (order["customer_id"],)).fetchone()
    return (order, customer) if _contact_matches(customer, contact) else None


def _payment_text(order) -> str:
    if order["payment_method"] == "credit":
        return f"Cartão de crédito em {order['installments']}x"
    return PAYMENT_TEXT[order["payment_method"]]


def get_order_status(conn, order_id: int, contact: str, today: date | None = None) -> dict:
    today = today or clock.today()
    found = _verified_order(conn, order_id, contact)
    if found is None:
        return dict(NOT_FOUND)
    order, customer = found

    items = [{"name": r["name"], "quantity": r["quantity"]} for r in conn.execute(
        "SELECT p.name, oi.quantity FROM order_items oi JOIN products p USING (product_id) "
        "WHERE oi.order_id = ?", (order_id,))]
    out = {
        "verified": True,
        "customer_first_name": customer["name"].split()[0],
        "order_id": order["order_id"],
        "order_date": order["order_date"],
        "status": order["status"],
        "status_text": STATUS_TEXT[order["status"]],
        "items": items,
        "total_text": pricing.brl(order["total_brl"]),
        "payment_text": _payment_text(order),
    }
    status = order["status"]
    if status == "pending":
        out["next_step"] = "O pedido só segue depois que o pagamento for confirmado."
    elif status == "confirmed":
        out["next_step"] = ("Pedido em separação. O código de rastreamento é enviado por e-mail e "
                            "WhatsApp assim que for despachado.")
    elif status in ("shipped", "delivered"):
        out["tracking_code"] = order["tracking_code"]
        out["estimated_delivery"] = order["estimated_delivery"]
        out["next_step"] = "O rastreio pode ser consultado no site dos Correios ou da Jadlog."
        if status == "shipped" and order["estimated_delivery"] and \
                date.fromisoformat(order["estimated_delivery"]) < today:
            late = (today - date.fromisoformat(order["estimated_delivery"])).days
            out["delayed_days"] = late
            out["needs_human"] = (f"A entrega estimada era {order['estimated_delivery']} "
                                  f"({late} dias atrás). Registrar e encaminhar a um atendente.")
    elif status == "cancelled":
        out["cancel_reason"] = order["notes"]
    return out


# The data has no sales channel and no flag for these, so the code cannot check them.
EXCLUSIONS_NOTE = ("Aviso: o direito de arrependimento vale para compras online, e o manual (4.4) exclui "
                   "itens personalizados ou sob encomenda e itens de promoção de liquidação com aviso "
                   "de \"venda final\". Se o cliente comprou algo assim, encaminhar a um atendente.")


def check_return_eligibility(conn, order_id: int, contact: str, reason: str,
                             today: date | None = None) -> dict:
    """Apply manual section 4 to one order.

    reason: 'arrependimento' (changed mind), 'preferencia' (colour/model/size),
            or 'defeito' (defect).
    The data has no receipt date, so the estimated delivery date stands in for
    it (flagged in the result). Anything the manual does not define is sent to
    a human instead of guessed.
    """
    if reason not in ("arrependimento", "preferencia", "defeito"):
        return {"error": "reason deve ser 'arrependimento', 'preferencia' ou 'defeito'."}
    today = today or clock.today()
    found = _verified_order(conn, order_id, contact)
    if found is None:
        return dict(NOT_FOUND)
    order, _ = found
    status = order["status"]

    def result(outcome, text, **extra):
        return {"verified": True, "order_id": order_id, "reason": reason,
                "outcome": outcome, "explanation": text, **extra}

    if status == "cancelled":
        return result("not_applicable", "O pedido está cancelado, então não há o que devolver.")
    if status in ("pending", "confirmed", "shipped"):
        return result("needs_human",
                      "O pedido ainda não foi entregue. O prazo de devolução só conta depois do "
                      "recebimento, e o manual não define o cancelamento antes da entrega. "
                      "Encaminhar a um atendente.")

    received = date.fromisoformat(order["estimated_delivery"])
    since_receipt = (today - received).days
    since_purchase = (today - date.fromisoformat(order["order_date"])).days
    basis = {"receipt_date_is_estimated": True, "received_on": order["estimated_delivery"],
             "days_since_receipt": since_receipt, "days_since_purchase": since_purchase}

    if since_receipt < 0:
        return result("needs_human",
                      f"A entrega estimada ({order['estimated_delivery']}) ainda não chegou, embora o "
                      "pedido conste como entregue. Encaminhar a um atendente para conferir a data real.",
                      **basis)

    if reason in ("arrependimento", "preferencia"):
        if since_receipt > RETURN_WINDOW_DAYS:
            return result("not_eligible",
                          f"O prazo de {RETURN_WINDOW_DAYS} dias corridos após o recebimento já passou "
                          f"({since_receipt} dias). Se o cliente receber em outra data, encaminhar a "
                          "um atendente para conferir.", **basis)
        if reason == "arrependimento":
            return result("eligible",
                          "Dentro do prazo de arrependimento. Condições: embalagem original, sem sinais "
                          "de uso, com acessórios e manuais. Reembolso na mesma forma de pagamento em "
                          "até 10 dias úteis, e o frete da devolução é por conta da loja. " + EXCLUSIONS_NOTE, **basis)
        return result("eligible_subject_to_stock",
                      "Dentro do prazo para troca por preferência, sujeita à disponibilidade do produto "
                      "desejado. Produto em perfeito estado e na embalagem original. A diferença de "
                      "valor é cobrada ou reembolsada. " + EXCLUSIONS_NOTE, **basis)

    # defect
    if since_purchase <= DEFECT_EXCHANGE_DAYS:
        return result("eligible",
                      f"Defeito de fabricação dentro de {DEFECT_EXCHANGE_DAYS} dias da compra: dá direito "
                      "à troca. Danos por mau uso, queda, umidade ou modificação não são cobertos.", **basis)
    if since_receipt <= LEGAL_WARRANTY_DAYS:
        return result("needs_human",
                      f"Passou de {DEFECT_EXCHANGE_DAYS} dias da compra, mas ainda está dentro da garantia "
                      f"legal de {LEGAL_WARRANTY_DAYS} dias do recebimento. O manual trata os dois prazos "
                      "de forma diferente, então um atendente deve avaliar o caso.", **basis)
    return result("manufacturer_warranty",
                  "Fora da garantia legal. Resta a garantia do fabricante (6 meses a 2 anos, conforme o "
                  "certificado). A loja pode intermediar o processo se o cliente pedir.", **basis)
