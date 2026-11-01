from datetime import date, datetime

from emporio import policies, store


def top(query, n=1):
    return [s["section"] for s in policies.search_policies(query, top_k=n)["sections"]]


def test_manual_is_split_into_numbered_chunks():
    sections = {c["section"] for c in policies.load_chunks()}
    assert {"1", "1.2", "2", "3", "3.1", "4.1", "4.2", "4.3", "4.4", "5.1", "5.2", "5.3",
            "6.1", "6.2", "7.1", "7.3", "8.1", "8.2", "8.3", "9", "10"} <= sections


def test_return_question_finds_regret_policy():
    assert "4.1" in top("me arrependi da compra, posso devolver o pedido?", 2)


def test_defect_question_finds_defect_policy():
    assert top("o violão chegou com defeito, posso trocar?") == ["4.2"]


def test_installments_question():
    assert "3.1" in top("posso parcelar em 10x no cartão?", 2)


def test_free_shipping_question():
    assert "5.1" in top("qual o valor do frete para Campo Grande?", 2)


def test_pix_discount_with_promotion_finds_promotion_rules():
    assert "6.2" in top("o desconto do pix vale junto com promoção?", 2)


def test_accessory_question_finds_scope_rule():
    assert "7.1" in top("vocês vendem cordas e cabos?", 2) or "1" in top("vocês vendem cordas e cabos?", 2)


def test_gibberish_returns_not_found():
    r = policies.search_policies("qual a previsão do tempo amanhã em Paris")
    assert r["found"] is False


def test_manual_keeps_both_phone_numbers_and_fixes_only_the_email():
    text = " ".join(c["text"] for c in policies.load_chunks())
    assert "3341-4444" in text and "3321-4500" in text
    assert "empóriodamusica" not in text and "contato@emporiodamusica.com.br" in text


def d(y, m, day, h, mi):
    return datetime(y, m, day, h, mi)


def test_open_on_a_weekday_morning():
    s = store.open_status(d(2026, 3, 10, 10, 0))   # Tuesday
    assert s["open"] and s["closes_at"] == "18:00"


def test_closed_exactly_at_closing_time():
    assert not store.open_status(d(2026, 3, 10, 18, 0))["open"]


def test_saturday_hours_end_at_13():
    assert store.open_status(d(2026, 3, 7, 12, 59))["open"]
    s = store.open_status(d(2026, 3, 7, 13, 0))
    assert not s["open"] and s["next_opening"] == "segunda-feira, 09/03 às 09:00"


def test_before_opening_reopens_the_same_day():
    assert store.open_status(d(2026, 3, 10, 7, 30))["next_opening"] == "terça-feira, 10/03 às 09:00"


def test_holiday_is_closed_and_skipped_when_finding_next_opening():
    s = store.open_status(d(2026, 11, 2, 10, 0))   # Finados, a Monday
    assert not s["open"] and s["holiday"] == "Finados"
    assert s["next_opening"] == "terça-feira, 03/11 às 09:00"


def test_store_info_lists_phone_and_whatsapp_as_printed_in_the_manual():
    info = store.store_info(d(2026, 3, 10, 10, 0))
    assert info["phone"] == "(67) 3341-4444" and info["whatsapp"] == "(67) 3321-4500"


def test_easter_dates():
    assert store.easter(2026) == date(2026, 4, 5)
    assert store.easter(2027) == date(2027, 3, 28)


def test_local_and_state_holidays_close_the_store():
    # 26 Aug 2026 (Wednesday) is Campo Grande's anniversary; 11 Oct 2027 (Monday) is the state holiday.
    assert not store.open_status(d(2026, 8, 26, 10, 0))["open"]
    assert store.open_status(d(2026, 8, 26, 10, 0))["holiday"].startswith("Aniversário de Campo Grande")
    assert not store.open_status(d(2027, 10, 11, 10, 0))["open"]
    assert store.open_status(d(2026, 8, 27, 10, 0))["open"]


def test_2027_movable_holidays_and_optional_days():
    assert not store.open_status(d(2027, 3, 26, 10, 0))["open"]            # Good Friday
    carnival = store.open_status(d(2027, 2, 9, 10, 0))                     # Carnival Tuesday
    assert carnival["open"] and "warning" in carnival                      # optional: open, but confirm
    assert "optional_holiday" in store.open_status(d(2027, 5, 27, 10, 0))  # Corpus Christi
    assert "optional_holiday" in store.open_status(d(2026, 12, 24, 10, 0))


def test_off_topic_questions_find_nothing():
    for q in ("quem ganhou o jogo ontem", "me indica uma receita de bolo", "qual a previsão do tempo amanhã em Paris"):
        assert policies.search_policies(q)["found"] is False, q


def test_short_real_questions_still_match():
    assert policies.search_policies("tem garantia?")["found"]
    assert "2" in top("qual o horário de funcionamento?", 2)
    assert "9" in top("como funciona a política de privacidade e meus dados?", 2)
