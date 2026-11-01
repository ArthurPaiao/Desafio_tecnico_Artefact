import pytest

from emporio.data import load_db, normalize_text


@pytest.fixture(scope="module")
def db():
    return load_db()


def count(db, table):
    return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_row_counts(db):
    assert count(db, "products") == 65
    assert count(db, "categories") == 9
    assert count(db, "customers") == 50
    assert count(db, "orders") == 20
    assert count(db, "order_items") == 22
    assert count(db, "promotions") == 25


def test_foreign_keys_are_consistent(db):
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_payment_method_is_split_into_method_and_installments(db):
    row = db.execute("SELECT payment_method, installments FROM orders WHERE order_id = 2").fetchone()
    assert (row["payment_method"], row["installments"]) == ("credit", 6)
    row = db.execute("SELECT payment_method, installments FROM orders WHERE order_id = 1").fetchone()
    assert (row["payment_method"], row["installments"]) == ("pix", 1)


def test_blank_tracking_becomes_null(db):
    row = db.execute("SELECT tracking_code, estimated_delivery FROM orders WHERE order_id = 9").fetchone()
    assert row["tracking_code"] is None and row["estimated_delivery"] is None


def test_only_four_promotions_are_active(db):
    ids = {r[0] for r in db.execute("SELECT product_id FROM promotions WHERE is_active = 1")}
    assert ids == {127, 121, 90, 94}


def test_phone_digits_and_email_are_normalised(db):
    row = db.execute("SELECT phone_digits, email FROM customers WHERE customer_id = 1").fetchone()
    assert row["phone_digits"] == "67998123456"
    assert row["email"] == row["email"].lower()


def test_accent_insensitive_search_column(db):
    assert normalize_text("Violão Clássico") == "violao classico"
    hits = db.execute("SELECT COUNT(*) FROM products WHERE name_norm LIKE '%takamine%'").fetchone()[0]
    assert hits == 4
