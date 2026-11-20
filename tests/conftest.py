import json
from pathlib import Path

import pytest

from db.crear import crear_db

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def conn():
    c = crear_db(":memory:")
    yield c
    c.close()


def cargar_fixture(ruta: str) -> dict:
    return json.loads((FIXTURES / ruta).read_text(encoding="utf-8"))
