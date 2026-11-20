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


def _columnas(conn: sqlite3.Connection, tabla: str) -> set[str]:
    return {fila[1] for fila in conn.execute(f"PRAGMA table_info({tabla})")}


def _migrar_fase2(conn: sqlite3.Connection) -> None:
    """Rehace las tablas de resultados con el esquema de la Fase 2 si siguen con el antiguo.

    Solo lo hace si están vacías (antes de la Fase 2 nunca se cargaron); si tuvieran datos,
    falla en vez de borrarlos.
    """
    if "slug" in _columnas(conn, "competencias") or not _columnas(conn, "competencias"):
        return
    tablas = ["integrantes", "resultados", "equipos", "competencias"]
    for t in tablas:
        if conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]:
            raise RuntimeError(f"La tabla {t} tiene datos con el esquema antiguo; migrar a mano.")
    for t in tablas:
        conn.execute(f"DROP TABLE {t}")


def _migrar_integrantes(conn: sqlite3.Connection) -> None:
    """Rehace `integrantes` con rol y fuente (Fase 3) si sigue con el esquema antiguo y vacía."""
    columnas = _columnas(conn, "integrantes")
    if not columnas or "rol" in columnas:
        return
    if conn.execute("SELECT COUNT(*) FROM integrantes").fetchone()[0]:
        raise RuntimeError("integrantes tiene datos con el esquema antiguo; migrar a mano.")
    conn.execute("DROP TABLE integrantes")


def crear_db(ruta: Path | str = RUTA_DB) -> sqlite3.Connection:
    """Aplica el esquema (idempotente) y devuelve la conexión."""
    if str(ruta) != ":memory:":
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    conn = conectar(ruta)
    _migrar_fase2(conn)
    _migrar_integrantes(conn)
    conn.executescript(RUTA_ESQUEMA.read_text(encoding="utf-8"))
    conn.commit()
    return conn


if __name__ == "__main__":
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else RUTA_DB
    crear_db(ruta).close()
    print(f"Base creada en {ruta}")
