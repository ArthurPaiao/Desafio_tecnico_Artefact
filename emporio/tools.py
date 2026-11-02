"""Tool definitions for the model, and the dispatcher that runs them.

Seven tools in three families:
  data      search_products, get_product, get_order_status, check_return_eligibility
  policies  search_policies, get_store_info
  action    escalate_to_human
"""

import sqlite3
from pathlib import Path

from emporio import catalog, handoff, orders, policies, store

MAX_FAILED_VERIFICATIONS = 3

TOOL_DEFS = [
    {
        "name": "search_products",
        "description": (
            "Search the instrument catalog. Use for any question about what the store sells, prices "
            "within a budget, or availability by type. Returns only products that can be bought now "
            "unless include_unavailable is true. Prices already include any active promotion."),
        "input_schema": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Words that must appear in the name, description or specs, e.g. 'aço folk' or 'takamine'."},
            "category": {"type": "string", "description": "Category in plain words: violões, guitarras, baixos, baterias, teclados, ukuleles."},
            "max_price": {"type": "number", "description": "Maximum price in BRL the customer would pay."},
            "min_price": {"type": "number", "description": "Minimum price in BRL."},
            "include_unavailable": {"type": "boolean"},
            "limit": {"type": "integer", "description": "Max products to return (default 8)."},
        }},
    },
    {
        "name": "get_product",
        "description": (
            "Full detail for ONE product: price, active promotion, stock status, PIX price, credit-card "
            "instalments and shipping. Use for 'how much is X', 'is X available', or payment and shipping "
            "questions about a specific product. Pass product_id (from a search) or a product name; "
            "partial names work. Pass city when the customer says where they live, to get the shipping rule."),
        "input_schema": {"type": "object", "properties": {
            "product_id": {"type": "integer"}, "name": {"type": "string"}, "city": {"type": "string"}}},
    },
    {
        "name": "get_order_status",
        "description": (
            "Status of an order. Requires BOTH the order number and a contact (e-mail or phone) that "
            "belongs to the customer who placed it. Ask the customer for both before calling. Never "
            "call it with a guessed or made-up contact."),
        "input_schema": {"type": "object", "properties": {
            "order_id": {"type": "integer"},
            "contact": {"type": "string", "description": "E-mail or phone used when buying."}},
            "required": ["order_id", "contact"]},
    },
    {
        "name": "check_return_eligibility",
        "description": (
            "Apply the store's return/exchange rules to a specific order. Requires the same order "
            "number and contact as get_order_status. reason is 'arrependimento' (changed their mind), "
            "'preferencia' (wants another colour/model/size) or 'defeito' (defect). Ask which one if unclear."),
        "input_schema": {"type": "object", "properties": {
            "order_id": {"type": "integer"}, "contact": {"type": "string"},
            "reason": {"type": "string", "enum": ["arrependimento", "preferencia", "defeito"]}},
            "required": ["order_id", "contact", "reason"]},
    },
    {
        "name": "search_policies",
        "description": (
            "Search the store policy manual: payment methods and instalment rules, exchanges and "
            "returns, shipping and delivery, promotions, warranty, privacy, service guidelines. Use "
            "for 'how does X work' questions. Pass a short Portuguese query with the key words."),
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}},
                         "required": ["query"]},
    },
    {
        "name": "get_store_info",
        "description": (
            "Address, phone numbers, e-mail, opening hours, and whether the store is open right now "
            "(with the next opening time)."),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Register the case for a human attendant and get a ticket number. Use for complaints, "
            "cases a tool marks as needing a human, requests to complete a purchase, or anything you "
            "cannot resolve. Write the summary so the attendant needs no extra questions."),
        "input_schema": {"type": "object", "properties": {
            "reason": {"type": "string", "enum": list(handoff.REASONS)},
            "summary": {"type": "string", "description": "What the customer wants and what was already checked."},
            "customer_contact": {"type": "string", "description": "Only if the customer offered one."}},
            "required": ["reason", "summary"]},
    },
]


TOOL_NAMES = {t["name"] for t in TOOL_DEFS}


class ToolBox:
    """Runs tool calls for one conversation and keeps its security state."""

    def __init__(self, conn: sqlite3.Connection, session_id: str, state_dir: Path,
                 failed_verifications: int = 0):
        self.conn = conn
        self.session_id = session_id
        self.state_dir = state_dir
        self.failed_verifications = failed_verifications   # saved with the session

    def call(self, name: str, args: dict) -> dict:
        # The model chooses the name, so only the declared tools can be reached.
        if name not in TOOL_NAMES:
            return {"error": f"Ferramenta desconhecida: {name}"}
        try:
            return getattr(self, f"_{name}")(**(args or {}))
        except (TypeError, ValueError) as e:
            return {"error": f"Argumentos inválidos para {name}: {e}"}
        except Exception as e:   # a tool bug must not abort the whole conversation turn
            return {"error": f"Falha ao executar {name}: {type(e).__name__}"}

    # data -------------------------------------------------------------
    def _search_products(self, **kw):
        if "limit" in kw:
            kw["limit"] = int(kw["limit"])
        return catalog.search_products(self.conn, **kw)

    def _get_product(self, **kw):
        if kw.get("product_id") is not None:
            kw["product_id"] = int(kw["product_id"])
        return catalog.get_product(self.conn, **kw)

    def _verified(self, fn, order_id, contact, **extra):
        if self.failed_verifications >= MAX_FAILED_VERIFICATIONS:
            return {"verified": False, "locked": True,
                    "message": "Muitas tentativas de verificação nesta conversa. Não consulte mais "
                               "pedidos: ofereça encaminhar a um atendente (escalate_to_human)."}
        result = fn(self.conn, int(order_id), contact, **extra)
        if result.get("verified") is False:
            self.failed_verifications += 1   # never reset on success: alternating with a valid lookup must not help a guesser
        return result

    def _get_order_status(self, order_id, contact):
        return self._verified(orders.get_order_status, order_id, contact)

    def _check_return_eligibility(self, order_id, contact, reason):
        return self._verified(orders.check_return_eligibility, order_id, contact, reason=reason)

    # policies ---------------------------------------------------------
    def _search_policies(self, query):
        return policies.search_policies(query)

    def _get_store_info(self):
        return store.store_info()

    # action -----------------------------------------------------------
    def _escalate_to_human(self, reason, summary, customer_contact=None):
        return handoff.create_ticket(self.state_dir, reason, summary, self.session_id, customer_contact)
