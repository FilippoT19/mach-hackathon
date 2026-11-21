"""Rigenera docs/PASSAGGIO-indici.md: indice delle funzioni del brain e indice dei casi.

    python asst/tools/indici.py        (dalla radice del repo)

Legge solo asst/brain/parts/*.py e CASI.md. Non tocca il brain.
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PARTS = sorted((ROOT / "asst" / "brain" / "parts").glob("*.py"))
CASE = re.compile(r"\b((?:BK|GP|FA|SP|CO|X|OPS|G)-\d+[a-z]?|MACH-\d+(?:\.\d+)?|P-[a-z]+-\d+)\b")
TITLES = {"00_core": "Avvio e smistamento", "10_shared": "Funzioni comuni", "15_voice": "AI (city.llm) e frasi",
          "20_gp": "Medico di base", "25_streets": "Tabella delle vie di Milano", "30_booking": "Centro prenotazioni",
          "40_facility": "Strutture (ospedale, specialista, consultorio)"}


def clean(text: str) -> str:
    return " ".join(text.replace("|", "/").split())


def functions() -> list[str]:
    out = ["## A. Indice delle funzioni", "",
           "Per ogni funzione: riga, prima frase della docstring (se c'è) e gli ID dei casi citati nel suo codice.",
           "Gli ID si cercano in `CASI.md` (indice B qui sotto) o in `proposte/<nome>.md` (ID `P-…`).", ""]
    for path in PARTS:
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        tree = ast.parse(source)
        defs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        out += [f"### `{path.name}` — {TITLES.get(path.stem, '')} ({len(lines)} righe, {len(defs)} funzioni)", ""]
        if path.stem == "25_streets":
            out += ["Solo dati: via → coordinate, per calcolare la distanza dal cittadino (X-54). "
                    + ", ".join(f"`{n.name}`" for n in defs), ""]
            continue
        out += ["| Funzione | Riga | Cosa fa (docstring) | Casi citati |", "|---|---|---|---|"]
        for node in defs:
            doc = ast.get_docstring(node) or ""
            body = "\n".join(lines[node.lineno - 1:node.end_lineno])
            first = clean(doc.split("\n\n")[0])[:230]
            if not first:  # no docstring: the first comment inside the function, else the one above it
                inside = re.search(r"^\s*#\s*(.+(?:\n\s*#\s*.+)*)", body, re.M)
                above = lines[node.lineno - 2].strip() if node.lineno >= 2 else ""
                note = inside.group(1) if inside else (above[1:] if above.startswith("#") else "")
                first = clean(re.sub(r"\n\s*#", " ", note))[:230]
                first = f"(commento) {first}" if first else ""
            ids = sorted(set(CASE.findall(body)), key=lambda s: (s.split("-")[0], s))
            kind = "async " if isinstance(node, ast.AsyncFunctionDef) else ("class " if isinstance(node, ast.ClassDef) else "")
            out.append(f"| `{kind}{node.name}` | {node.lineno} | {first or '—'} | {', '.join(ids) or '—'} |")
        out.append("")
        consts = [(n.lineno, t.id) for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign))
                  for t in ([n.target] if isinstance(n, ast.AnnAssign) else n.targets) if isinstance(t, ast.Name)]
        out += ["Costanti e memorie di modulo: " + ", ".join(f"`{name}` (r. {line})" for line, name in consts), ""]
    return out


def cases() -> list[str]:
    out = ["## B. Indice dei casi (da CASI.md)", "",
           "Una riga per caso: ID, di cosa parla (inizio della riga), stato scritto nel registro. La riga completa "
           "(rischio, soluzione, logica, test) è in `CASI.md`.", "", "| ID | Caso (inizio) | Stato |", "|---|---|---|"]
    for line in (ROOT / "CASI.md").read_text(encoding="utf-8").splitlines():
        if not re.match(r"^\| [A-Z]+-[0-9a-z.]+ \|", line):
            continue
        cells = [clean(c) for c in line.strip().strip("|").split("|")]
        about = cells[1] if len(cells[1]) > 45 else f"{cells[1]} — {cells[2]}"
        out.append(f"| {cells[0]} | {about[:170]} | {cells[-1][:110]} |")
    return out + [""]


def main() -> None:
    text = ["# PASSAGGIO — indici generati dal codice", "",
            "Generato da `asst/tools/indici.py`. Non modificare a mano: rilanciare lo script.", ""]
    text += functions() + cases()
    target = ROOT / "docs" / "PASSAGGIO-indici.md"
    target.write_text("\n".join(text), encoding="utf-8")
    print(f"{target.relative_to(ROOT)}: {len(text)} righe")


if __name__ == "__main__":
    main()
