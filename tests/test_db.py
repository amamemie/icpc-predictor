from datetime import UTC, date, datetime, timedelta, timezone

from db.consultas import a_iso_utc, rating_a_la_fecha
from scrapers.codeforces import guardar_historial, parsear_historial
from tests.conftest import cargar_fixture


def _cargar_jperez(conn):
    conn.execute(
        "INSERT INTO cf_usuarios (handle, fecha_descarga) VALUES ('jperez', '2026-11-20T00:00:00Z')"
    )
    cambios = cargar_fixture("codeforces/user_rating_jperez.json")["result"]
    guardar_historial(conn, "jperez", parsear_historial(cambios, "jperez"))


def test_esquema_crea_todas_las_tablas(conn):
    tablas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "personas",
        "cuentas",
        "competencias",
        "equipos",
        "integrantes",
        "resultados",
        "historial_rating",
        "cf_usuarios",
    } <= tablas


def test_crear_db_es_idempotente(tmp_path):
    from db.crear import crear_db

    ruta = tmp_path / "x.sqlite"
    crear_db(ruta).close()
    crear_db(ruta).close()


def test_a_iso_utc():
    assert a_iso_utc(date(2025, 9, 1)) == "2025-09-01T00:00:00Z"
    assert a_iso_utc(datetime(2025, 9, 1, 10, 0)) == "2025-09-01T10:00:00Z"
    bolivia = timezone(timedelta(hours=-4))
    assert a_iso_utc(datetime(2025, 9, 1, 22, 0, tzinfo=bolivia)) == "2025-09-02T02:00:00Z"


def test_rating_a_la_fecha_entre_contests(conn):
    _cargar_jperez(conn)
    # Contests: 2021-01-01 -> 1400, 2021-06-01 -> 1550, 2022-01-01 -> 1650 (todos 00:00 UTC)
    assert rating_a_la_fecha(conn, "codeforces", "jperez", date(2021, 3, 15)) == 1400
    assert rating_a_la_fecha(conn, "codeforces", "jperez", date(2021, 12, 31)) == 1550
    assert rating_a_la_fecha(conn, "codeforces", "jperez", date(2030, 1, 1)) == 1650


def test_rating_a_la_fecha_es_estrictamente_anterior(conn):
    _cargar_jperez(conn)
    # El 2021-06-01 a las 00:00 UTC se actualizó a 1550: en ese mismo instante aún vale 1400.
    assert rating_a_la_fecha(conn, "codeforces", "jperez", date(2021, 6, 1)) == 1400
    momento = datetime(2021, 6, 1, 0, 0, 1, tzinfo=UTC)
    assert rating_a_la_fecha(conn, "codeforces", "jperez", momento) == 1550


def test_rating_a_la_fecha_sin_datos(conn):
    _cargar_jperez(conn)
    assert rating_a_la_fecha(conn, "codeforces", "jperez", date(2020, 12, 31)) is None
    assert rating_a_la_fecha(conn, "codeforces", "nadie", date(2025, 1, 1)) is None
    assert rating_a_la_fecha(conn, "atcoder", "jperez", date(2025, 1, 1)) is None
