"""Crea (o actualiza) la base SQLite con el esquema de db/schema.sql.

Uso: python -m db.crear [ruta]
"""

import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
RUTA_DB = RAIZ / "data" / "db.sqlite"
RUTA_ESQUEMA = Path(__file__).resolve().parent / "schema.sql"


def conectar(ruta: Path | str = RUTA_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(ruta)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def crear_db(ruta: Path | str = RUTA_DB) -> sqlite3.Connection:
    """Aplica el esquema (idempotente) y devuelve la conexión."""
    if str(ruta) != ":memory:":
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    conn = conectar(ruta)
    conn.executescript(RUTA_ESQUEMA.read_text(encoding="utf-8"))
    conn.commit()
    return conn


if __name__ == "__main__":
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else RUTA_DB
    crear_db(ruta).close()
    print(f"Base creada en {ruta}")
