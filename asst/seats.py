"""Fill role/capabilities on the five agent folders and copy our shared brain into each.

Run from asst/ AFTER `city login` and the five `city init agent <name>` commands:

    python seats.py          # patch cards + copy brain/agent.py into every agent
    python seats.py --brain  # only re-copy the brain (after editing brain/agent.py)

The brain is one file for all five seats: it reads its role from card.yaml.
"""
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEATS = {  # folder: (card role, capability)
    "booking_centre": ("booking_centre", "booking_centre"),
    "hospital": ("facility", "hospital.physiatry"),
    "gp": ("gp", "gp"),
    "specialist": ("facility", "specialist_care.cardiology"),
    "family_counseling": ("facility", "family_counseling.gynecology"),
}


def set_seat(card: Path, role: str, capability: str) -> None:
    out, skip = [], False
    for line in card.read_text(encoding="utf-8").splitlines():
        if skip:
            if line.startswith((" ", "\t")):
                continue
            skip = False
        key = line.split(":", 1)[0]
        if key == "role" and not line.startswith((" ", "\t")):
            out.append(f"role: {role}")
        elif key == "capabilities" and not line.startswith((" ", "\t")):
            out += ["capabilities:", f"  - {capability}"]
            skip = True
        else:
            out.append(line)
    card.write_text("\n".join(out) + "\n", encoding="utf-8")


def set_city_role(city_yaml: Path, role: str) -> None:
    text = city_yaml.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^role:.*$", f"role: {role}", text)
    city_yaml.write_text(text, encoding="utf-8")


def main(root: Path = HERE) -> None:
    brain_only = "--brain" in sys.argv
    missing = [f for f in SEATS if not (root / f / "card.yaml").exists()]
    if missing:
        sys.exit(f"missing agent folders {missing}: run `city init agent <name>` for each first")
    for folder, (role, capability) in SEATS.items():
        d = root / folder
        if not brain_only:
            set_seat(d / "card.yaml", role, capability)
            set_city_role(d / "city.yaml", role)
        shutil.copyfile(HERE / "brain" / "agent.py", d / "agent" / "agent.py")
        print(f"{folder:18} role={role:15} capability={capability}")


if __name__ == "__main__":
    main(Path(next((a for a in sys.argv[1:] if not a.startswith("--")), HERE)))
