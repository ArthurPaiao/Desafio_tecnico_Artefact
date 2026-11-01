"""Loads the store CSVs into an in-memory SQLite database, with light cleaning.

SQLite keeps the data layer simple: the agent tools are plain parameterised SQL
and there are no extra dependencies. The database is rebuilt from the CSVs on
every start, so the CSVs stay the single source of truth.
"""

import csv
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

PRODUCT_STATUSES = {"active", "discontinued", "coming_soon"}
ORDER_STATUSES = {"pending", "confirmed", "shipped", "delivered", "cancelled"}

SCHEMA = """
CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT
);
CREATE TABLE products (
    product_id     INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    name_norm      TEXT NOT NULL,   -- lowercase, no accents: for search
    category_id    INTEGER NOT NULL REFERENCES categories(category_id),
    description    TEXT,
    price_brl      REAL NOT NULL,
    stock_quantity INTEGER NOT NULL,
    status         TEXT NOT NULL,   -- active | discontinued | coming_soon
    specs          TEXT NOT NULL,   -- JSON object
    created_at     TEXT
);
CREATE TABLE promotions (
    promotion_id     INTEGER PRIMARY KEY,
    product_id       INTEGER NOT NULL REFERENCES products(product_id),
    discount_percent REAL NOT NULL,
    description      TEXT,
    is_active        INTEGER NOT NULL
);
CREATE TABLE customers (
    customer_id  INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    phone        TEXT,
    phone_digits TEXT,               -- digits only, for matching
    email        TEXT,               -- lowercase
    city         TEXT
);
CREATE TABLE orders (
    order_id           INTEGER PRIMARY KEY,
    customer_id        INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date         TEXT NOT NULL,  -- ISO date
    status             TEXT NOT NULL,
    total_brl          REAL NOT NULL,
    payment_method     TEXT NOT NULL,  -- pix | boleto | debit | credit
    installments       INTEGER NOT NULL DEFAULT 1,
    tracking_code      TEXT,
    estimated_delivery TEXT,
    notes              TEXT
);
CREATE TABLE order_items (
    order_id   INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity   INTEGER NOT NULL
);
"""


def normalize_text(text: str) -> str:
    """Lowercase and strip accents, so 'Violão' matches 'violao'."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower().strip()


def _blank_to_none(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _read(data_dir: Path, name: str) -> list[dict]:
    with open(data_dir / f"{name}.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _parse_payment(raw: str) -> tuple[str, int]:
    """'credit_6x' -> ('credit', 6); 'pix' -> ('pix', 1)."""
    match = re.fullmatch(r"(credit)_(\d+)x", raw.strip())
    if match:
        return match.group(1), int(match.group(2))
    return raw.strip(), 1


def _insert(conn: sqlite3.Connection, table: str, rows: list[dict]) -> None:
    cols = list(rows[0])
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
    conn.executemany(sql, [tuple(r[c] for c in cols) for r in rows])


def load_db(data_dir: Path = DATA_DIR) -> sqlite3.Connection:
    """Build the in-memory database. Raises ValueError on malformed data."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)

    _insert(conn, "categories", [
        {"category_id": int(r["category_id"]), "name": r["name"].strip(),
         "description": _blank_to_none(r["description"])}
        for r in _read(data_dir, "categories")
    ])

    products = []
    for r in _read(data_dir, "products"):
        if r["status"] not in PRODUCT_STATUSES:
            raise ValueError(f"product {r['product_id']}: unknown status {r['status']!r}")
        json.loads(r["specs"])  # fail early if a specs value is not valid JSON
        products.append({
            "product_id": int(r["product_id"]),
            "name": r["name"].strip(),
            "name_norm": normalize_text(r["name"]),
            "category_id": int(r["category_id"]),
            "description": _blank_to_none(r["description"]),
            "price_brl": float(r["price_brl"]),
            "stock_quantity": int(r["stock_quantity"]),
            "status": r["status"],
            "specs": r["specs"],
            "created_at": _blank_to_none(r["created_at"]),
        })
    _insert(conn, "products", products)

    _insert(conn, "promotions", [
        {"promotion_id": int(r["promotion_id"]), "product_id": int(r["product_id"]),
         "discount_percent": float(r["discount_percent"]),
         "description": _blank_to_none(r["description"]),
         "is_active": int(r["is_active"])}
        for r in _read(data_dir, "promotions")
    ])

    _insert(conn, "customers", [
        {"customer_id": int(r["customer_id"]), "name": r["name"].strip(),
         "phone": _blank_to_none(r["phone"]),
         "phone_digits": re.sub(r"\D", "", r["phone"] or ""),
         "email": (r["email"] or "").strip().lower() or None,
         "city": _blank_to_none(r["city"])}
        for r in _read(data_dir, "customers")
    ])

    orders = []
    for r in _read(data_dir, "orders"):
        if r["status"] not in ORDER_STATUSES:
            raise ValueError(f"order {r['order_id']}: unknown status {r['status']!r}")
        method, installments = _parse_payment(r["payment_method"])
        orders.append({
            "order_id": int(r["order_id"]), "customer_id": int(r["customer_id"]),
            "order_date": r["order_date"], "status": r["status"],
            "total_brl": float(r["total_brl"]),
            "payment_method": method, "installments": installments,
            "tracking_code": _blank_to_none(r["tracking_code"]),
            "estimated_delivery": _blank_to_none(r["estimated_delivery"]),
            "notes": _blank_to_none(r["notes"]),
        })
    _insert(conn, "orders", orders)

    _insert(conn, "order_items", [
        {"order_id": int(r["order_id"]), "product_id": int(r["product_id"]),
         "quantity": int(r["quantity"])}
        for r in _read(data_dir, "order_items")
    ])

    conn.commit()
    return conn
