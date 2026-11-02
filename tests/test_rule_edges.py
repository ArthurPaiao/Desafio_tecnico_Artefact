"""Boundary values for the manual's rules. Expected numbers come from the manual's
text (section numbers in the comments), not from reading the implementation."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from emporio import catalog, orders, policies, pricing, store
from emporio.data import load_db


@pytest.fixture(scope="module")
def db():
    return load_db()


# Order 7: bought 2026-02-03, estimated delivery (receipt) 2026-02-17, customer 14.
CONTACT = "leticia.rocha@jmail.com"


def outcome(db, reason, today):
    return orders.check_return_eligibility(db, 7, CONTACT, reason, today=today)


@pytest.mark.parametrize("today, expected", [
    (date(2026, 3, 5), "eligible"),                # day 30 from purchase (4.2: 30 days)
    (date(2026, 3, 6), "needs_human"),             # day 31
    (date(2026, 3, 10), "needs_human"),            # day 35 from purchase, 21 from receipt
    (date(2026, 5, 18), "needs_human"),            # 90 days from receipt (8.1: 90 days)
    (date(2026, 5, 19), "manufacturer_warranty"),  # 91 days from receipt
])
def test_defect_windows(db, today, expected):
    assert outcome(db, "defeito", today)["outcome"] == expected


@pytest.mark.parametrize("reason, today, expected", [
    ("arrependimento", date(2026, 2, 24), "eligible"),                  # day 7 from receipt (4.1)
    ("arrependimento", date(2026, 2, 25), "not_eligible"),              # day 8
    ("preferencia", date(2026, 2, 24), "eligible_subject_to_stock"),    # 4.3: 7 days
    ("preferencia", date(2026, 2, 25), "not_eligible"),
    ("arrependimento", date(2026, 2, 10), "needs_human"),               # "delivered" before the estimate
])
def test_regret_and_preference_windows(db, reason, today, expected):
    assert outcome(db, reason, today)["outcome"] == expected


def test_eligible_answers_carry_the_exclusions_warning(db):
    assert "venda final" in outcome(db, "arrependimento", date(2026, 2, 20))["explanation"]


@pytest.mark.parametrize("total, most", [
    (99.99, 1), (100.00, 2), (149.99, 2), (150.00, 3), (319.99, 3),     # 3.1: up to 3x, at least R$ 50
    (320.00, 4), (479.99, 5), (480.00, 6), (699.99, 6),                 # 4 to 6x, at least R$ 80
    (700.00, 7), (1199.99, 11), (1200.00, 12),                          # 7 to 12x, at least R$ 100
])
def test_instalment_tiers(total, most):
    assert max(o["installments"] for o in pricing.installment_options(total)) == most


def test_pix_rounds_half_up_on_the_list_price():
    assert pricing.pix_price(359.90, has_promotion=False) == Decimal("341.91")   # 341.905
    assert pricing.pix_price(359.90, has_promotion=True) is None                 # 6.2


@pytest.mark.parametrize("product_id, fee", [(90, 0.0), (121, 35.0)])
def test_local_shipping_uses_the_price_actually_charged(db, product_id, fee):
    # 121 lists at R$ 549 but sells at R$ 439,20 on promotion: below the R$ 500 threshold.
    assert catalog.get_product(db, product_id=product_id, city="Campo Grande")["shipping"]["fee"] == fee


@pytest.mark.parametrize("city", ["Campo Grande", " campo grande ", "Campo Grande - MS", "Campo Grande/MS"])
def test_campo_grande_is_recognised_however_it_is_written(city):
    assert pricing.shipping(100, city)["method"] == "motoboy"


@pytest.mark.parametrize("moment, is_open, extra", [
    (datetime(2026, 3, 10, 8, 59), False, {"next_opening": "terça-feira, 10/03 às 09:00"}),
    (datetime(2026, 3, 10, 9, 0), True, {}),
    (datetime(2026, 3, 10, 17, 59), True, {}),
    (datetime(2026, 3, 8, 10, 0), False, {"next_opening": "segunda-feira, 09/03 às 09:00"}),     # Sunday
    (datetime(2026, 6, 13, 10, 0), False, {"holiday": "Dia de Santo Antônio (municipal, Campo Grande)"}),  # Saturday
    (datetime(2026, 11, 15, 10, 0), False, {"holiday": "Proclamação da República"}),            # Sunday
    (datetime(2026, 12, 31, 18, 30), False, {"next_opening": "sábado, 02/01 às 09:00"}),        # 01/01/2027 is a holiday
    (datetime(2026, 4, 3, 10, 0), False, {"holiday": "Sexta-feira Santa"}),
])
def test_opening_hours_edges(moment, is_open, extra):
    status = store.open_status(moment)
    assert status["open"] is is_open
    for key, value in extra.items():
        assert status[key] == value


def test_return_question_reaches_the_seven_day_rule():
    sections = [s["section"] for s in policies.search_policies("quanto tempo para devolver")["sections"]]
    assert "4.1" in sections


def test_weather_question_matches_no_policy():
    assert policies.search_policies("previsão do tempo")["found"] is False
