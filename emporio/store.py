"""Store facts that are rules, not prose: opening hours and contact details."""

from datetime import date, datetime, time, timedelta

from emporio import clock

# Section 2 of the manual. Weekday numbers follow datetime: Monday = 0.
HOURS = {**{d: (time(9), time(18)) for d in range(5)}, 5: (time(9), time(13))}  # Sunday absent = closed

# Section 2 says "Domingo e Feriados: Fechado" but lists no holidays.
# ASSUMPTION: Brazilian national holidays for 2026. Municipal holidays are not
# covered, and the manual says hours may be extended on special dates, so the
# agent is told to treat holiday answers as likely rather than certain.
NATIONAL_HOLIDAYS_2026 = {
    date(2026, 1, 1): "Confraternização Universal", date(2026, 2, 17): "Carnaval",
    date(2026, 4, 3): "Sexta-feira Santa", date(2026, 4, 21): "Tiradentes",
    date(2026, 5, 1): "Dia do Trabalho", date(2026, 6, 4): "Corpus Christi",
    date(2026, 9, 7): "Independência", date(2026, 10, 12): "Nossa Senhora Aparecida",
    date(2026, 11, 2): "Finados", date(2026, 11, 15): "Proclamação da República",
    date(2026, 11, 20): "Consciência Negra", date(2026, 12, 25): "Natal",
}

WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
            "sexta-feira", "sábado", "domingo"]

CONTACT = {
    "name": "Empório da Música",
    "address": "Rua 14 de Maio, 3200 - Centro, Campo Grande - MS, CEP 79202-333",
    "phone_whatsapp": "(67) 3341-4444",
    "email": "contato@emporiodamusica.com.br",
    "hours_text": "Segunda a sexta, 09:00 às 18:00. Sábado, 09:00 às 13:00. Domingos e feriados fechado.",
}


def _opening(day: date):
    if day in NATIONAL_HOLIDAYS_2026 or day.weekday() not in HOURS:
        return None
    return HOURS[day.weekday()]


def _label(day: date, at: time) -> str:
    return f"{WEEKDAYS[day.weekday()]}, {day:%d/%m} às {at:%H:%M}"


def open_status(at: datetime | None = None) -> dict:
    at = at or clock.now()
    hours = _opening(at.date())
    is_open = bool(hours and hours[0] <= at.time() < hours[1])
    holiday = NATIONAL_HOLIDAYS_2026.get(at.date())
    out = {
        "now_text": f"{WEEKDAYS[at.weekday()]}, {at:%d/%m/%Y}, {at:%H:%M} (horário de Campo Grande)",
        "open": is_open,
    }
    if holiday:
        out["holiday"] = holiday
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
        "Em Black Friday, Aniversário da Loja e Natal o horário pode ser estendido; "
        "feriados municipais não estão na lista da loja. Em dúvida, diga que vai confirmar.",
    ]
    return info
