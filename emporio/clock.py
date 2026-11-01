"""The agent's notion of 'now', in the store's time zone.

Mato Grosso do Sul runs one hour behind Brasília time, so store hours are
evaluated in America/Campo_Grande. EMPORIO_NOW (ISO date-time, read as store
local time) pins the clock: the sample data stops in March 2026, so a real
clock would make every delivered order look old, and pinning keeps the example
conversations reproducible. Without it, the real time is used.
"""

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

STORE_TZ = ZoneInfo("America/Campo_Grande")


def now() -> datetime:
    pinned = os.environ.get("EMPORIO_NOW")
    if pinned:
        return datetime.fromisoformat(pinned).replace(tzinfo=STORE_TZ)
    return datetime.now(STORE_TZ)


def today() -> date:
    return now().date()
