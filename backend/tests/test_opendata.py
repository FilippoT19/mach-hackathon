import asyncio

from app.agents.tools import _find_places
from app.db import SessionLocal, init_db
from app.opendata import DATASETS, parse_csv

PHARMACY = next(d for d in DATASETS if d.category == "pharmacy")
METRO = next(d for d in DATASETS if d.category == "metro_stop")

PHARMA_CSV = """﻿CODICE_FARMACIA;DESCRIZIONE_FARMACIA;INDIRIZZO;MUNICIPIO;NIL;LONGITUDINE;LATITUDINE
MI1;NEAR DUOMO;VIA OREFICI, 2;1;DUOMO;9.18807;45.46406
MI2;FAR AWAY;VIA LONTANA, 1;9;AFFORI;9.17;45.52
"""
METRO_CSV = """id_amat;nome;linee;LONG_X_4326;LAT_Y_4326;Location
1;DUOMO M1;"1";9.18951;45.46420;"(x)"
"""


def test_parse_and_search():
    rows = parse_csv(PHARMACY, PHARMA_CSV)
    assert [r.name for r in rows] == ["NEAR DUOMO", "FAR AWAY"]
    assert rows[0].lat == 45.46406 and rows[0].data == {"CODICE_FARMACIA": "MI1"}

    async def go():
        await init_db()
        async with SessionLocal() as db:
            db.add_all(rows + parse_csv(METRO, METRO_CSV))
            await db.commit()
            tool = _find_places(db, "u", "test")
            out = await tool.call({"category": "pharmacy", "near": "duomo", "limit": 1})
            assert "NEAR DUOMO" in out and "FAR AWAY" not in out
            assert "error" in await tool.call({"category": "nope"})

    asyncio.run(go())
