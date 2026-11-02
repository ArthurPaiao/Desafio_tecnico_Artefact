"""Money rules from the store policy manual, computed in code (never by the LLM).

Where the manual contradicts itself, the choice made here is documented next to
the rule and repeated in the README ("Assumptions").
"""

import re
from decimal import ROUND_HALF_UP, Decimal

PIX_DISCOUNT_PERCENT = 5
FREE_SHIPPING_ABOVE = Decimal("500.00")  # "acima de R$ 500,00": strictly greater
LOCAL_SHIPPING_FEE = Decimal("35.00")
MAX_INSTALLMENTS = 12

# Section 3.1 (tiered minimum instalment). The summary table in section 3 says a
# flat R$ 100 minimum for all credit purchases, which would contradict 3.1.
# ASSUMPTION: the tiered rules in 3.1 are the specific ones, so they win.
# "sem valor mínimo (exceto abaixo de R$ 50,00)" is read as: up to 3x, no
# instalment may be smaller than R$ 50.
MIN_INSTALLMENT = [(3, Decimal("50.00")), (6, Decimal("80.00")), (12, Decimal("100.00"))]

# Section 5.1 only says "Região Metropolitana de Campo Grande" and lists no
# towns. ASSUMPTION: only Campo Grande itself gets the local motoboy delivery;
# every other city goes through Correios/Jadlog.
LOCAL_CITY = "campo grande"


def _normalize_city(city: str) -> str:
    """'Campo Grande - MS', 'campo grande/MS' and ' Campo Grande ' are the same city."""
    return re.split(r"\s*[-/,]\s*", city.strip().lower())[0]


def money(value) -> Decimal:
    """Round to cents, half up (what a cashier expects)."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def brl(value) -> str:
    """Format as Brazilian currency: 1299.9 -> 'R$ 1.299,90'."""
    text = f"{money(value):,.2f}"
    return "R$ " + text.replace(",", "X").replace(".", ",").replace("X", ".")


def promo_price(price, discount_percent) -> Decimal:
    return money(Decimal(str(price)) * (Decimal(100) - Decimal(str(discount_percent))) / 100)


def pix_price(price, has_promotion: bool) -> Decimal | None:
    """5% off the list price. Promotions are not cumulative, so no PIX
    discount on a price that is already promotional (manual, section 6.2)."""
    if has_promotion:
        return None
    return promo_price(price, PIX_DISCOUNT_PERCENT)


def _min_installment(n: int) -> Decimal:
    for upto, minimum in MIN_INSTALLMENT:
        if n <= upto:
            return minimum
    raise ValueError(n)


def installment_options(total) -> list[dict]:
    """Every allowed credit-card split of `total`, interest free, 1x..12x."""
    total = Decimal(str(total))
    options = []
    for n in range(1, MAX_INSTALLMENTS + 1):
        if n > 1 and total / n < _min_installment(n):
            continue
        options.append({"installments": n, "installment_value": float(money(total / n)),
                        "installment_text": f"{n}x de {brl(total / n)} sem juros"})
    return options


def shipping(total, city: str | None, special_freight: bool = False) -> dict:
    """Shipping rule for an order total and destination city. Manual 5.2 (other
    cities) is where large instruments get an individually quoted freight; 5.1
    (Campo Grande) has no such exception, so local buyers get the motoboy rule."""
    if not city or not city.strip():
        return {"method": "unknown_city",
                "text": "Informe a cidade de entrega para calcular o frete."}
    if _normalize_city(city) != LOCAL_CITY and special_freight:
        return {"method": "special_quote",
                "text": "Instrumento de grande porte: o frete é cotado individualmente pela loja."}
    if _normalize_city(city) == LOCAL_CITY:
        if Decimal(str(total)) > FREE_SHIPPING_ABOVE:
            return {"method": "motoboy", "fee": 0.0,
                    "text": "Frete grátis (pedido acima de R$ 500,00). Entrega por motoboy em 1 a 3 dias úteis."}
        return {"method": "motoboy", "fee": float(LOCAL_SHIPPING_FEE),
                "text": f"Taxa fixa de {brl(LOCAL_SHIPPING_FEE)}. Entrega por motoboy em 1 a 3 dias úteis."}
    return {"method": "correios_jadlog",
            "text": "Envio por Correios (PAC 5 a 12 dias úteis, SEDEX 2 a 5) ou Jadlog (3 a 8 dias úteis), "
                    "com seguro incluso. O valor é calculado pelo CEP de destino, peso e dimensões."}
