"""Hand-off to a human attendant.

The agent cannot resolve everything (complaints, cases the manual leaves open).
This records the case so a person can pick it up, and gives the customer a
ticket number and the manual's promised response time (section 7.3: 24 business
hours). Tickets are appended to a JSON Lines file; a real deployment would post
to the helpdesk instead.
"""

import json
from datetime import datetime
from pathlib import Path

from emporio import clock

REASONS = ("complaint", "order_issue", "return_review", "purchase_help", "other")


def create_ticket(directory: Path, reason: str, summary: str, session_id: str,
                  customer_contact: str | None = None) -> dict:
    if reason not in REASONS:
        reason = "other"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "handoffs.jsonl"
    number = sum(1 for _ in path.open(encoding="utf-8")) + 1 if path.exists() else 1
    ticket = f"ATD-{number:04d}"
    record = {"ticket": ticket, "created_at": clock.now().isoformat(timespec="seconds"),
              "session": session_id, "reason": reason, "summary": summary,
              "customer_contact": customer_contact}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"ticket": ticket,
            "message": f"Caso registrado com o protocolo {ticket}. Um atendente retorna em até "
                       "24 horas úteis. Informe o protocolo ao cliente."}
