"""Store facts that are rules, not prose: opening hours and contact details."""

from datetime import date, datetime, time, timedelta
from functools import lru_cache

from emporio import clock

# Section 2 of the manual. Weekday numbers follow datetime: Monday = 0.
HOURS = {**{d: (time(9), time(18)) for d in range(5)}, 5: (time(9), time(13))}  # Sunday absent = closed

# Section 2 says "Domingo e Feriados: Fechado" but lists no holidays.
# ASSUMPTION: holidays that apply in Campo Grande, MS (checked against public
# calendars for 2026; 2027 follows the same rules, movable dates computed from
# Easter). Two tiers:
#   closed   national + state + municipal holidays: the store is closed.
#   optional "ponto facultativo" days: open at normal hours unless the store
#            decides otherwise, so the agent is told to confirm instead of
#            promising.
# Fixed municipal/state dates are assumed not to move between years, and the
# manual also says hours may change on special dates (Black Friday, Natal).
FIXED_HOLIDAYS = {
    (1, 1): "Confraternização Universal", (4, 21): "Tiradentes", (5, 1): "Dia do Trabalho",
    (6, 13): "Dia de Santo Antônio (municipal, Campo Grande)",
    (8, 26): "Aniversário de Campo Grande (municipal)",
    (9, 7): "Independência", (10, 11): "Criação do Estado de Mato Grosso do Sul (estadual)",
    (10, 12): "Nossa Senhora Aparecida", (11, 2): "Finados",
    (11, 15): "Proclamação da República", (11, 20): "Consciência Negra", (12, 25): "Natal",
}


def easter(year: int) -> date:
    """Gregorian Easter (anonymous algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = divmod(b, 4)
    g = (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


@lru_cache(maxsize=None)
def holidays(year: int) -> tuple[dict, dict]:
    """(closed, optional) holidays for a year, as {date: name}."""
    closed = {date(year, m, d): name for (m, d), name in FIXED_HOLIDAYS.items()}
    paste = easter(year)
    closed[paste - timedelta(days=2)] = "Sexta-feira Santa"
    optional = {
        paste - timedelta(days=48): "Carnaval (ponto facultativo)",
        paste - timedelta(days=47): "Carnaval (ponto facultativo)",
        paste - timedelta(days=46): "Quarta-feira de Cinzas (ponto facultativo, até as 14h)",
        paste + timedelta(days=60): "Corpus Christi (ponto facultativo)",
        date(year, 12, 24): "Véspera de Natal (ponto facultativo, após as 14h)",
        date(year, 12, 31): "Véspera de Ano Novo (ponto facultativo, após as 14h)",
    }
    return closed, optional


WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
            "sexta-feira", "sábado", "domingo"]

CONTACT = {
    "name": "Empório da Música",
    "address": "Rua 14 de Maio, 3200 - Centro, Campo Grande - MS, CEP 79202-333",
    # The manual prints two numbers: (67) 3341-4444 as the company phone (cover and
    # company data) and (67) 3321-4500 as the WhatsApp channel (section 7). Both are kept.
    "phone": "(67) 3341-4444",
    "whatsapp": "(67) 3321-4500",
    "email": "contato@emporiodamusica.com.br",
    "hours_text": "Segunda a sexta, 09:00 às 18:00. Sábado, 09:00 às 13:00. Domingos e feriados fechado.",
}


def _opening(day: date):
    if day in holidays(day.year)[0] or day.weekday() not in HOURS:
        return None
    return HOURS[day.weekday()]


def _label(day: date, at: time) -> str:
    return f"{WEEKDAYS[day.weekday()]}, {day:%d/%m} às {at:%H:%M}"


def open_status(at: datetime | None = None) -> dict:
    at = at or clock.now()
    hours = _opening(at.date())
    is_open = bool(hours and hours[0] <= at.time() < hours[1])
    closed, optional = holidays(at.year)
    holiday = closed.get(at.date())
    out = {
        "now_text": f"{WEEKDAYS[at.weekday()]}, {at:%d/%m/%Y}, {at:%H:%M} (horário de Campo Grande)",
        "open": is_open,
    }
    if holiday:
        out["holiday"] = holiday
    if at.date() in optional:
        out["optional_holiday"] = optional[at.date()]
        out["warning"] = "Ponto facultativo: o horário pode mudar. Diga que vai confirmar com a equipe."
    if is_open:
        out["closes_at"] = f"{hours[1]:%H:%M}"
        return out
    for offset in range(0, 10):
        day = at.date() + timedelta(days=offset)
        h = _opening(day)
        if h and (offset > 0 or at.time() < h[0]):
            out["next_opening"] = _label(day, h[0])
            break
    return out


def store_info(at: datetime | None = None) -> dict:
    status = open_status(at)
    info = {**CONTACT, "status_now": status}
    info["notes"] = [
        "Fora do expediente, informe o horário de retorno (next_opening).",
        "Em Black Friday, Aniversário da Loja e Natal o horário pode ser estendido. "
        "Em dúvida sobre uma data especial, diga que vai confirmar.",
    ]
    return info
