"""Import Milan open data (CKAN portal dati.comune.milano.it) into the `places` table.

    python -m app.opendata            # import every dataset below
    python -m app.opendata pharmacy   # just one category

Add a dataset: find its id on dati.comune.milano.it, add a Dataset(...) entry,
map its columns. CSV URLs are resolved at import time because they change.
"""
import asyncio
import csv
import io
import sys
from dataclasses import dataclass

import httpx
from sqlalchemy import delete

from .db import SessionLocal, init_db
from .models import Place

CKAN = "https://dati.comune.milano.it/api/3/action"


@dataclass(frozen=True)
class Dataset:
    category: str
    ckan_id: str
    name: str | tuple[str, ...]  # column(s) joined to build the display name
    lat: str
    lon: str
    address: str | None = None
    label: str = ""  # human description, shown to the agents


DATASETS = [
    Dataset("pharmacy", "ds501_farmacie-nel-comune-di-milano", "DESCRIZIONE_FARMACIA",
            "LATITUDINE", "LONGITUDINE", "INDIRIZZO", "pharmacies"),
    Dataset("metro_stop", "ds535_atm-fermate-linee-metropolitane", "nome",
            "LAT_Y_4326", "LONG_X_4326", None, "metro stations (data.linee = lines)"),
    Dataset("bus_tram_stop", "ds534-atm-fermate-linee-di-superficie-urbane", "ubicazione",
            "LAT_Y_4326", "LONG_X_4326", None, "bus/tram stops (data.linee = lines)"),
    Dataset("recycling_center", "ds692-riciclerie", "Ricicleria",
            "LAT_WGS84", "LONG_WGS84", "Indirizzo", "AMSA recycling centres (riciclerie)"),
    Dataset("water_house", "ds625-case-dell-acqua-nel-comune-di-milano", "NIL",
            "LAT_Y_4326", "LONG_X_4326", None, "free public water dispensers (case dell'acqua)"),
    Dataset("street_market", "ds291-economia-mercati-settimanali-scoperti", "MERCATO",
            "LAT_Y_4326", "LONG_X_4326", None, "weekly street markets (data.giorno, data.orari)"),
    Dataset("mm_housing_office", "ds1546-sportelli-di-quartiere-sportelli-mm", "TIPOLOGIA",
            "LAT_Y_4326", "LONG_X_4326", "INDIRIZZO", "MM public-housing help desks"),
]
CATEGORIES = {d.category: d.label for d in DATASETS}


def _float(v: str | None) -> float | None:
    try:
        return float(str(v).replace(",", ".")) if v not in (None, "") else None
    except ValueError:
        return None


def parse_csv(ds: Dataset, text: str) -> list[Place]:
    text = text.lstrip("﻿")
    delim = csv.Sniffer().sniff(text.splitlines()[0], delimiters=";,").delimiter
    places = []
    for row in csv.DictReader(io.StringIO(text), delimiter=delim):
        cols = ds.name if isinstance(ds.name, tuple) else (ds.name,)
        name = " ".join((row.get(c) or "").strip() for c in cols).strip()
        if not name:
            continue
        used = {*cols, ds.lat, ds.lon, ds.address, "NIL", "MUNICIPIO", "Location"}
        places.append(Place(
            category=ds.category, name=name,
            address=(row.get(ds.address) or "").strip() or None if ds.address else None,
            nil=(row.get("NIL") or "").strip() or None,
            municipio=(row.get("MUNICIPIO") or "").strip() or None,
            lat=_float(row.get(ds.lat)), lon=_float(row.get(ds.lon)),
            data={k: v for k, v in row.items() if k and k not in used and v not in (None, "")},
            source=f"dati.comune.milano.it/{ds.ckan_id}",
        ))
    return places


async def fetch(client: httpx.AsyncClient, ds: Dataset) -> str:
    pkg = (await client.get(f"{CKAN}/package_show", params={"id": ds.ckan_id})).json()["result"]
    url = next(r["url"] for r in pkg["resources"] if (r.get("format") or "").upper() == "CSV")
    resp = await client.get(url, follow_redirects=True)
    resp.raise_for_status()
    raw = resp.content
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


async def main(only: list[str]) -> None:
    await init_db()
    async with httpx.AsyncClient(timeout=60) as client, SessionLocal() as db:
        for ds in DATASETS:
            if only and ds.category not in only:
                continue
            places = parse_csv(ds, await fetch(client, ds))
            await db.execute(delete(Place).where(Place.category == ds.category))
            db.add_all(places)
            await db.commit()
            print(f"{ds.category:18} {len(places):5} rows  ({ds.ckan_id})")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
