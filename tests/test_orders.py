from datetime import date

import pytest

from emporio import orders
from emporio.data import load_db


@pytest.fixture(scope="module")
def db():
    return load_db()


def contact(db, order_id, kind="email"):
    row = db.execute("SELECT c.email, c.phone FROM orders o JOIN customers c USING (customer_id) "
                     "WHERE o.order_id = ?", (order_id,)).fetchone()
    return row[kind]


def test_status_with_matching_email(db):
    r = orders.get_order_status(db, 8, contact(db, 8))
    assert r["verified"] and r["status"] == "shipped"
    assert r["customer_first_name"] == "Ana"
    assert r["tracking_code"] == "BRJL5544332BR"


def test_phone_matches_in_any_format(db):
    for variant in ("(67) 99654-7821", "67996547821", "+55 67 99654-7821"):
        assert orders.get_order_status(db, 8, variant)["verified"]


def test_wrong_contact_and_missing_order_look_the_same(db):
    wrong = orders.get_order_status(db, 8, "outra.pessoa@jmail.com")
    missing = orders.get_order_status(db, 999, "qualquer@jmail.com")
    assert wrong == missing and wrong["verified"] is False


def test_empty_or_short_contact_never_matches(db):
    for bad in ("", "   ", "123", "@"):
        assert not orders.get_order_status(db, 8, bad)["verified"]


def test_shared_email_does_not_leak_the_other_customers_order(db):
    # customers 11 and 43 share bruno.martins@jmail.com; order 10 belongs to 11 only,
    # and the check goes through the order's own customer.
    assert orders.get_order_status(db, 10, "bruno.martins@jmail.com")["verified"]
    # a phone number of another customer must not unlock it
    assert not orders.get_order_status(db, 10, "(67) 99456-3456")["verified"]


def test_shipped_order_past_estimate_is_flagged(db):
    r = orders.get_order_status(db, 8, contact(db, 8), today=date(2026, 3, 25))
    assert r["delayed_days"] == 25 and "needs_human" in r
    r = orders.get_order_status(db, 8, contact(db, 8), today=date(2026, 2, 20))
    assert "needs_human" not in r


def test_confirmed_order_has_no_tracking_yet(db):
    r = orders.get_order_status(db, 9, contact(db, 9))
    assert "tracking_code" not in r and "despachado" in r["next_step"]


def test_cancelled_order_shows_reason(db):
    r = orders.get_order_status(db, 18, contact(db, 18))
    assert r["status"] == "cancelled" and "estoque" in r["cancel_reason"]


def test_regret_inside_window_is_eligible(db):
    # order 7 delivered on 2026-02-17
    r = orders.check_return_eligibility(db, 7, contact(db, 7), "arrependimento", today=date(2026, 2, 20))
    assert r["outcome"] == "eligible" and r["days_since_receipt"] == 3
    assert r["receipt_date_is_estimated"] is True


def test_regret_on_day_seven_is_still_eligible_day_eight_is_not(db):
    c = contact(db, 7)
    assert orders.check_return_eligibility(db, 7, c, "arrependimento", today=date(2026, 2, 24))["outcome"] == "eligible"
    assert orders.check_return_eligibility(db, 7, c, "arrependimento", today=date(2026, 2, 25))["outcome"] == "not_eligible"


def test_exchange_by_preference_depends_on_stock(db):
    r = orders.check_return_eligibility(db, 7, contact(db, 7), "preferencia", today=date(2026, 2, 20))
    assert r["outcome"] == "eligible_subject_to_stock"


def test_defect_windows(db):
    c = contact(db, 7)  # bought 2026-02-03, received 2026-02-17
    assert orders.check_return_eligibility(db, 7, c, "defeito", today=date(2026, 3, 5))["outcome"] == "eligible"
    assert orders.check_return_eligibility(db, 7, c, "defeito", today=date(2026, 4, 1))["outcome"] == "needs_human"
    assert orders.check_return_eligibility(db, 7, c, "defeito", today=date(2026, 7, 1))["outcome"] == "manufacturer_warranty"


def test_undelivered_and_cancelled_orders(db):
    assert orders.check_return_eligibility(db, 8, contact(db, 8), "arrependimento")["outcome"] == "needs_human"
    assert orders.check_return_eligibility(db, 17, contact(db, 17), "arrependimento")["outcome"] == "not_applicable"


def test_return_check_also_requires_verification(db):
    assert orders.check_return_eligibility(db, 7, "x@y.com", "arrependimento")["verified"] is False


def test_invalid_reason(db):
    assert "error" in orders.check_return_eligibility(db, 7, contact(db, 7), "talvez")
