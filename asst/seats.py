"""Build the shared brain from brain/parts/, set the five seats, and copy the brain into each agent.

Run from asst/:

    python seats.py          # set role/capabilities on the 5 cards + build + copy the brain
    python seats.py --brain  # build brain/agent.py from brain/parts/ and copy it into the 5 agents
    python seats.py --check  # build in memory and check: it compiles, and every copy is up to date

Edit ONLY the files in brain/parts/ (one per role). brain/agent.py and <agent>/agent/agent.py
are generated: never edit them by hand. The parts are joined in name order (00_, 10_, 20_ ...).
"""
import hashlib
import py_compile
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARTS = HERE / "brain" / "parts"
BRAIN = HERE / "brain" / "agent.py"
SEATS = {  # folder: (card role, capability)
    "booking_centre": ("booking_centre", "booking_centre"),
    "hospital": ("facility", "hospital.physiatry"),
    "gp": ("gp", "gp"),
    "specialist": ("facility", "specialist_care.cardiology"),
    "family_counseling": ("facility", "family_counseling.gynecology"),
}
# The first two lines of every part are a label for humans; they are not part of the brain.
_LABEL = ("# PART:", "# Non è un modulo a sé:")
_BUILD_LINE = '_BUILD = "dev"\n'


def build() -> str:
    parts = sorted(PARTS.glob("*.py"))
    if not parts:
        sys.exit(f"no parts in {PARTS}")
    out = []
    for part in parts:
        lines = part.read_text(encoding="utf-8").splitlines(keepends=True)
        out += [line for line in lines if not line.startswith(_LABEL)]
    source = "".join(out)
    # OPS-14: the build id is the digest of the joined parts, written into the brain itself, so it
    # travels inside the image with agent.py (not with the local card, which the CLI bumps).
    if source.count(_BUILD_LINE) != 1:
        sys.exit(f"brain/parts must hold exactly one line {_BUILD_LINE.strip()!r}")
    build = "b-" + hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
    return source.replace(_BUILD_LINE, f'_BUILD = "{build}"\n')


def build_id() -> str:
    """The id `seats.py --brain` stamps for the parts as they are now (`python seats.py --build-id`)."""
    return re.search(r'^_BUILD = "(b-[0-9a-f]{12})"$', build(), re.M).group(1)


def compiles(source: str) -> str | None:
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
        tmp.write(source)
    try:
        py_compile.compile(tmp.name, doraise=True)
    except py_compile.PyCompileError as err:
        return str(err)
    finally:
        Path(tmp.name).unlink(missing_ok=True)
    return None


def check(root: Path) -> None:
    source = build()
    problems = []
    error = compiles(source)
    if error:
        problems.append(f"the built brain does not compile:\n{error}")
    targets = [BRAIN] + [root / f / "agent" / "agent.py" for f in SEATS]
    for target in targets:
        if not target.exists() or target.read_text(encoding="utf-8") != source:
            problems.append(f"out of date: {target.relative_to(root)} (run: python seats.py --brain)")
    if problems:
        sys.exit("CHECK FAILED\n- " + "\n- ".join(problems))
    print(f"CHECK OK: brain compiles, {len(targets)} copies match brain/parts/")


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
    if "--build-id" in sys.argv:
        print(build_id())
        return
    if "--check" in sys.argv:
        check(root)
        return
    brain_only = "--brain" in sys.argv
    missing = [f for f in SEATS if not (root / f / "card.yaml").exists()]
    if missing:
        sys.exit(f"missing agent folders {missing}: run `city init agent <name>` for each first")
    source = build()
    error = compiles(source)
    if error:
        sys.exit(f"the built brain does not compile, nothing copied:\n{error}")
    BRAIN.write_text(source, encoding="utf-8")
    for folder, (role, capability) in SEATS.items():
        d = root / folder
        if not brain_only:
            set_seat(d / "card.yaml", role, capability)
            set_city_role(d / "city.yaml", role)
        shutil.copyfile(BRAIN, d / "agent" / "agent.py")
        print(f"{folder:18} role={role:15} capability={capability}")


if __name__ == "__main__":
    main(Path(next((a for a in sys.argv[1:] if not a.startswith("--")), HERE)))
