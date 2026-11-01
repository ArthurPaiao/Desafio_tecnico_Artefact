"""The agent's notion of 'today'.

The sample data stops in March 2026, so a real clock would make every delivered
order look old. EMPORIO_TODAY (YYYY-MM-DD) pins the date, which keeps the
example conversations reproducible. Without it, the real date is used.
"""

import os
from datetime import date


def today() -> date:
    pinned = os.environ.get("EMPORIO_TODAY")
    return date.fromisoformat(pinned) if pinned else date.today()
