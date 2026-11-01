from emporio import pricing


def test_brl_format():
    assert pricing.brl(1299.9) == "R$ 1.299,90"
    assert pricing.brl(35) == "R$ 35,00"
    assert pricing.brl(1234567.5) == "R$ 1.234.567,50"


def test_promo_price_rounds_half_up():
    assert float(pricing.promo_price(5999, 8)) == 5519.08
    assert float(pricing.promo_price(359, 10)) == 323.10


def test_pix_discount_only_on_list_price():
    assert float(pricing.pix_price(1000, has_promotion=False)) == 950.00
    assert pricing.pix_price(1000, has_promotion=True) is None


def test_installments_follow_tiered_minimums():
    def ns(total):
        return [o["installments"] for o in pricing.installment_options(total)]
    assert ns(120) == [1, 2]            # 3x would be R$ 40, under the R$ 50 floor
    assert ns(480) == [1, 2, 3, 4, 5, 6]  # 6x = R$ 80 is allowed; 7x = R$ 68.57 is not
    assert max(ns(1200)) == 12          # 12x = R$ 100 exactly is allowed
    assert max(ns(1190)) == 11          # 12x = R$ 99.17 is under R$ 100; 11x = R$ 108.18
    assert ns(40) == [1]


def test_shipping_rules():
    assert pricing.shipping(500, "Campo Grande")["fee"] == 35.0   # "acima de" 500: 500 itself pays
    assert pricing.shipping(500.01, "campo grande")["fee"] == 0.0
    assert pricing.shipping(100, "Dourados")["method"] == "correios_jadlog"
    assert pricing.shipping(100, None)["method"] == "unknown_city"
    assert pricing.shipping(4439, "Campo Grande", special_freight=True)["method"] == "special_quote"
