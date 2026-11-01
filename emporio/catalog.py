"""Product tools: search the catalog and get a product with price conditions.

Everything the agent says about price, stock and promotions must come from
these functions (manual, section 7.1: never state prices or stock without
consulting the system).
"""

import json
import sqlite3

from emporio import pricing
from emporio.data import normalize_text

# Words customers use that do not appear verbatim in category names.
CATEGORY_ALIASES = {
    "violao": 5, "violoes": 5, "folk": 5,
    "ukulele": 9, "ukuleles": 9, "ukelele": 9,
    "guitarra": 1, "guitarras": 1,
    "baixo": 2, "baixos": 2, "contrabaixo": 2,
    "bateria": 3, "baterias": 3, "percussao": 3,
    "teclado": 4, "teclados": 4, "piano": 4, "pianos": 4, "sintetizador": 4,
}

SPECIAL_FREIGHT_HINTS = ("bateria acustica", "piano", "contrabaixo")


def resolve_category(conn: sqlite3.Connection, text: str) -> int | None:
    """Map free text ('violões', 'Ukuleles') to a category_id, or None."""
    wanted = normalize_text(text)
    if wanted in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[wanted]
    for row in conn.execute("SELECT category_id, name FROM categories"):
        name = normalize_text(row["name"])
        if wanted == name or wanted in name.split() or (len(wanted) > 3 and wanted in name):
            return row["category_id"]
    return None


def _promotion(conn, product_id: int) -> dict | None:
    """Best active promotion. Promotions are not cumulative (section 6.2), so
    if several were ever active at once only the largest one applies."""
    row = conn.execute(
        "SELECT description, discount_percent FROM promotions "
        "WHERE product_id = ? AND is_active = 1 ORDER BY discount_percent DESC LIMIT 1",
        (product_id,)).fetchone()
    return dict(row) if row else None


def _availability(row) -> str:
    # Business rule (confirmed by the store owner's side of the case): a
    # discontinued model is sold until its remaining stock runs out, and only
    # then leaves the catalog. Pulling it early would waste inventory already
    # paid for. Section 7.3 of the manual still asks us to tell the customer,
    # which is what the `discontinued_notice` field is for.
    if row["status"] == "coming_soon":
        return "coming_soon"
    if row["stock_quantity"] > 0:
        return "available"
    return "discontinued" if row["status"] == "discontinued" else "out_of_stock"


def _summary(conn, row) -> dict:
    """The compact view of a product used in search results."""
    promo = _promotion(conn, row["product_id"])
    price = row["price_brl"]
    out = {
        "product_id": row["product_id"],
        "name": row["name"],
        "category": row["category"],
        "availability": _availability(row),
        "list_price": price,
        "list_price_text": pricing.brl(price),
    }
    if promo:
        final = pricing.promo_price(price, promo["discount_percent"])
        out["promotion"] = {
            "name": promo["description"],
            "discount_percent": promo["discount_percent"],
            "promo_price": float(final),
            "promo_price_text": pricing.brl(final),
            "note": "Mostrar sempre junto do preço original e do percentual de desconto.",
        }
    if out["availability"] == "available":
        out["stock_quantity"] = row["stock_quantity"]
        if row["status"] == "discontinued":
            out["discontinued_notice"] = (
                "Modelo descontinuado: restam apenas as unidades em estoque e ele não será reposto. "
                "Informar o cliente.")
    return out


_BASE_SELECT = (
    "SELECT p.*, c.name AS category FROM products p "
    "JOIN categories c USING (category_id)"
)


def search_products(conn, query: str | None = None, category: str | None = None,
                    max_price: float | None = None, min_price: float | None = None,
                    include_unavailable: bool = False, limit: int = 8) -> dict:
    """Find products. `query` words must all appear in the name, description,
    category or specs. Price filters compare against the price the customer
    would actually pay (promotional price when a promotion is active)."""
    category_id = None
    if category:
        category_id = resolve_category(conn, category)
        if category_id is None:
            valid = [r["name"] for r in conn.execute("SELECT name FROM categories ORDER BY category_id")]
            return {"error": f"Categoria '{category}' não reconhecida.", "valid_categories": valid}

    rows = conn.execute(
        _BASE_SELECT + (" WHERE p.category_id = ?" if category_id else ""),
        (category_id,) if category_id else ()).fetchall()

    tokens = [t for t in normalize_text(query or "").split() if t]
    results = []
    for row in rows:
        if tokens:
            haystack = normalize_text(" ".join([
                row["name"], row["description"] or "", row["category"],
                " ".join(str(v) for v in json.loads(row["specs"]).values())]))
            if not all(t in haystack for t in tokens):
                continue
        item = _summary(conn, row)
        if item["availability"] != "available" and not include_unavailable:
            continue
        effective = item.get("promotion", {}).get("promo_price", item["list_price"])
        if max_price is not None and effective > max_price:
            continue
        if min_price is not None and effective < min_price:
            continue
        item["_effective"] = effective
        results.append(item)

    results.sort(key=lambda r: r["_effective"])
    total = len(results)
    price_range = ([results[0]["_effective"], results[-1]["_effective"]] if results else None)
    for r in results:
        del r["_effective"]
    out = {"total_found": total, "products": results[:limit]}
    if price_range:
        out["price_range_of_all_results"] = [pricing.brl(price_range[0]), pricing.brl(price_range[1])]
    if total > limit:
        out["note"] = f"Mostrando os {limit} mais baratos de {total}. Ofereça refinar a busca."
    if category_id and total == 0:
        out["note"] = "Nenhum produto desta categoria atende aos filtros no catálogo atual."
    return out


def _alternatives(conn, row, limit: int = 3) -> list[dict]:
    """Available products in the same category with a similar price."""
    rows = conn.execute(
        _BASE_SELECT + " WHERE p.category_id = ? AND p.product_id != ? "
        "AND p.status = 'active' AND p.stock_quantity > 0",
        (row["category_id"], row["product_id"])).fetchall()
    rows.sort(key=lambda r: abs(r["price_brl"] - row["price_brl"]))
    return [_summary(conn, r) for r in rows[:limit]]


def get_product(conn, product_id: int | None = None, name: str | None = None,
                city: str | None = None) -> dict:
    """Full detail for one product, with payment conditions and shipping.

    Pass `product_id`, or a `name` (partial names work). If a name matches more
    than one product the candidates are returned so the agent can ask which one.
    """
    if product_id is None:
        if not name:
            return {"error": "Informe product_id ou name."}
        found = search_products(conn, query=name, include_unavailable=True, limit=5)
        if found["total_found"] == 0:
            return {"error": f"Nenhum produto encontrado para '{name}'.",
                    "note": "Não invente o produto. Ofereça buscar por categoria ou faixa de preço."}
        if found["total_found"] > 1:
            return {"ambiguous": True, "candidates": found["products"],
                    "note": "Mais de um produto corresponde. Pergunte qual deles o cliente quer."}
        product_id = found["products"][0]["product_id"]

    row = conn.execute(_BASE_SELECT + " WHERE p.product_id = ?", (product_id,)).fetchone()
    if row is None:
        return {"error": f"Produto {product_id} não existe."}

    out = _summary(conn, row)
    out["description"] = row["description"]
    out["specs"] = json.loads(row["specs"])

    if out["availability"] != "available":
        out["alternatives"] = _alternatives(conn, row)
        out["note"] = {
            "out_of_stock": "Temporariamente sem estoque. Sugerir alternativas disponíveis.",
            "discontinued": "Descontinuado e sem estoque: não faz mais parte do catálogo. Oferecer modelos equivalentes.",
            "coming_soon": "Ainda não está à venda. Não confirmar data nem reservar.",
        }[out["availability"]]
        return out

    promo = out.get("promotion")
    charged = promo["promo_price"] if promo else row["price_brl"]
    pix = pricing.pix_price(row["price_brl"], has_promotion=promo is not None)
    out["price_to_pay"] = charged
    out["price_to_pay_text"] = pricing.brl(charged)
    out["pix"] = ({"price": float(pix), "price_text": pricing.brl(pix), "discount_percent": 5}
                  if pix else {"available": False,
                               "reason": "Preço já promocional: o desconto de PIX não é cumulativo."})
    out["credit_card_options"] = pricing.installment_options(charged)
    out["other_payments"] = "Débito e boleto à vista, pelo mesmo preço."
    special = any(h in normalize_text(row["name"]) for h in SPECIAL_FREIGHT_HINTS)
    out["shipping"] = pricing.shipping(charged, city, special_freight=special)
    return out
