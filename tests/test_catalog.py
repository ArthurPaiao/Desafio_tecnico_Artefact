import pytest

from emporio import catalog
from emporio.data import load_db


@pytest.fixture(scope="module")
def db():
    return load_db()


def names(result):
    return [p["name"] for p in result["products"]]


def test_takamine_gd20_by_partial_name(db):
    p = catalog.get_product(db, name="Takamine GD20")
    assert p["product_id"] == 95
    assert p["availability"] == "available"
    assert p["list_price_text"].startswith("R$ ")
    assert p["pix"]["discount_percent"] == 5  # its old promotion is inactive


def test_ambiguous_name_returns_candidates(db):
    r = catalog.get_product(db, name="Takamine")
    assert r["ambiguous"] and len(r["candidates"]) == 4


def test_unknown_product_is_not_invented(db):
    r = catalog.get_product(db, name="Gibson SG Standard")
    assert "error" in r


def test_acoustic_guitars_up_to_1000_are_sorted_and_available(db):
    r = catalog.search_products(db, category="violões", max_price=1000)
    effective = [p.get("promotion", {}).get("promo_price", p["list_price"]) for p in r["products"]]
    assert r["total_found"] >= 1
    assert all(p["availability"] == "available" for p in r["products"])
    assert all(p.get("promotion", {}).get("promo_price", p["list_price"]) <= 1000 for p in r["products"])
    assert effective == sorted(effective)
    assert len(r["price_range_of_all_results"]) == 2


def test_price_filter_uses_promotional_price(db):
    # Taylor 110e: list R$ 5.999, 8% active promotion -> R$ 5.519,08
    assert "Taylor 110e Dreadnought Natural" in names(catalog.search_products(db, query="taylor 110e", max_price=5600))
    assert catalog.search_products(db, query="taylor 110e", max_price=5400)["total_found"] == 0


def test_active_promotion_shows_original_price_and_blocks_pix(db):
    p = catalog.get_product(db, product_id=94)
    assert p["promotion"]["discount_percent"] == 8
    assert p["promotion"]["promo_price"] == 5519.08
    assert p["list_price"] == 5999
    assert p["pix"]["available"] is False


def test_inactive_promotion_is_ignored(db):
    # product 93 has several promotions in the table, none active
    assert "promotion" not in catalog.get_product(db, product_id=93)


def test_out_of_stock_has_alternatives(db):
    p = catalog.get_product(db, product_id=96)  # Giannini, stock 0
    assert p["availability"] == "out_of_stock"
    assert p["alternatives"] and all(a["availability"] == "available" for a in p["alternatives"])
    assert "pix" not in p


def test_discontinued_with_stock_is_sold_with_a_notice(db):
    p = catalog.get_product(db, product_id=136)  # discontinued, stock 13
    assert p["availability"] == "available"
    assert p["stock_quantity"] == 13
    assert "discontinued_notice" in p
    assert "pix" in p
    assert 136 in [x["product_id"] for x in catalog.search_products(db, category="baixos")["products"]]


def test_discontinued_without_stock_leaves_the_catalog(db):
    p = catalog.get_product(db, product_id=113)  # discontinued, stock 0
    assert p["availability"] == "discontinued"
    assert p["alternatives"]
    assert 113 not in [x["product_id"] for x in catalog.search_products(db, category="violões", limit=100)["products"]]


def test_coming_soon_is_not_for_sale(db):
    assert catalog.get_product(db, product_id=130)["availability"] == "coming_soon"
    assert 130 not in [p["product_id"] for p in catalog.search_products(db, category="ukulele")["products"]]


def test_unavailable_hidden_by_default(db):
    ids = [p["product_id"] for p in catalog.search_products(db, limit=100)["products"]]
    assert 96 not in ids and 113 not in ids and 130 not in ids
    assert 136 in ids  # discontinued but still has stock


def test_empty_category_is_reported_not_invented(db):
    r = catalog.search_products(db, category="Instrumentos de Sopro (Madeiras)")
    assert r["total_found"] == 0 and "note" in r


def test_unknown_category_lists_valid_ones(db):
    r = catalog.search_products(db, category="pedais")
    assert "error" in r and "Violões" in r["valid_categories"]


def test_accent_insensitive_query(db):
    assert catalog.search_products(db, query="aço folk")["total_found"] > 0
    assert catalog.search_products(db, query="aco folk")["total_found"] == catalog.search_products(db, query="aço folk")["total_found"]


def test_large_instruments_use_special_freight_only_outside_campo_grande(db):
    # Manual 5.2 (other cities) is where the individually quoted freight is described.
    # 5.1 (Campo Grande) has no exception: the R$ 4.439 drum kit ships free by motoboy.
    local = catalog.get_product(db, product_id=139, city="Campo Grande")["shipping"]
    assert (local["method"], local["fee"]) == ("motoboy", 0.0)
    assert catalog.get_product(db, product_id=139, city="Dourados")["shipping"]["method"] == "special_quote"


def test_shipping_depends_on_city(db):
    cheap = catalog.get_product(db, product_id=83, city="Campo Grande")  # R$ 429,90
    assert cheap["shipping"]["fee"] == 35.0
    assert catalog.get_product(db, product_id=83, city="Dourados")["shipping"]["method"] == "correios_jadlog"
