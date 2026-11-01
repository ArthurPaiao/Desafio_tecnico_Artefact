"""Convert data/store_policies.pdf into data/store_policies.md.

Dev-time only (needs `pdftotext`, from poppler). The generated Markdown is
committed, so running the agent needs no PDF tooling. Re-run after changing
the PDF:  python scripts/extract_policies.py

The text is kept faithful to the PDF except for the CORRECTIONS below, each of
which fixes a contradiction inside the manual. They are listed in the README.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "data" / "store_policies.pdf"
OUT = ROOT / "data" / "store_policies.md"

# (wrong text, replacement, why)
CORRECTIONS = [
    ("(67) 3321-4500", "(67) 3341-4444",
     "Section 7 gives a different WhatsApp number from the company data table and the cover."),
    ("contato@empóriodamusica.com.br", "contato@emporiodamusica.com.br",
     "The e-mail in section 1.2 has an accent, which is not valid in a domain; the cover has none."),
]

H1 = re.compile(r"^(\d+)\.\s+(\S.*)$")
H2 = re.compile(r"^(\d+\.\d+)\s+(\S.*)$")
BULLET = re.compile(r"^[•▸]​?\s*(.*)$")
NUMBERED = re.compile(r"^(\d)\.​?\s+(\S.*)$")
NOISE = re.compile(r"^(Empório da Música Manual de Políticas e Procedimentos|Página \d+)$")


LABEL = re.compile(r"(?<=[.!?]) (?=(?!Prazo de retorno)[A-ZÀ-Ý][^.:\n|]{2,35}: )")


def split_labelled(line: str) -> str:
    """'Tom de voz: ... Escopo: ...' fused in one paragraph -> one bullet each."""
    if line.startswith(("#", "|", "- ")) or not LABEL.search(line):
        return line
    return "\n".join("- " + part for part in LABEL.split(line))


def extract() -> str:
    raw = subprocess.run(["pdftotext", "-layout", str(PDF), "-"], check=True,
                         capture_output=True, text=True).stdout
    raw = raw.replace("\f", "\n")
    lines = [l.rstrip() for l in raw.splitlines()]
    start = next(i for i, l in enumerate(lines) if H1.match(l.strip()) and "Sobre a" in l)
    out, block = [], []   # block: list of ("p"|"b"|"t", text)

    def flush():
        for kind, text in block:
            out.append(("- " if kind == "b" else "") + text)
        if block:
            out.append("")
        block.clear()

    for line in lines[start:]:
        s = line.strip()
        if NOISE.match(s) or s.startswith("Empório da Música — Sua música") or s.startswith("Última atualização"):
            continue
        if not s:
            flush()
            continue
        m2, m1 = H2.match(s), H1.match(s)
        if m2 and len(s) < 70:
            flush(); out += [f"### {m2.group(1)} {m2.group(2)}", ""]; continue
        if m1 and len(s) < 70:
            flush(); out += [f"## {m1.group(1)}. {m1.group(2)}", ""]; continue
        b = BULLET.match(s) or NUMBERED.match(s)
        if b:
            block.append(("b", b.group(b.lastindex)))
        elif re.search(r"\s{2,}", s) and block and block[-1][0] in ("t",) or \
                re.search(r"\s{2,}", s) and (not block or block[-1][0] != "b"):
            cells = re.split(r"\s{2,}", s)
            if len(cells) >= 2:
                block.append(("t", "| " + " | ".join(cells) + " |"))
            elif block and block[-1][0] == "t":   # wrapped cell text
                block[-1] = ("t", block[-1][1][:-2] + " " + cells[0] + " |")
            else:
                block.append(("p", s))
        elif block and block[-1][0] in ("b", "p"):
            block[-1] = (block[-1][0], block[-1][1] + " " + s)
        elif block and block[-1][0] == "t":
            block[-1] = ("t", block[-1][1][:-2] + " " + s + " |")
        else:
            block.append(("p", s))
    flush()
    text = "\n".join(out).strip() + "\n"
    text = re.sub(r"\|\n\n(?=\|)", "|\n", text)  # keep table rows together
    text = "\n".join(split_labelled(line) for line in text.split("\n"))
    text = text.replace("​", "")
    for wrong, right, _ in CORRECTIONS:
        text = text.replace(wrong, right)
    return text


if __name__ == "__main__":
    OUT.write_text(extract(), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)", file=sys.stderr)
