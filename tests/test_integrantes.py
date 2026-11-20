import csv

from matching.integrantes import (
    cargar_integrantes,
    cobertura,
    generar_plantilla,
    leer_plantilla,
)
from scrapers.scorelatam import Equipo, cargar_competencia


def _poblar(conn):
    reg = {
        "slug": "latam-2025",
        "nombre": "Regional",
        "tipo": "regional",
        "año": "2025",
        "fecha": "2025-11-06",
        "formato": "boca",
        "url_scoreboard": "u",
    }
    nac = {**reg, "slug": "subbr-2025", "nombre": "Nacional", "tipo": "nacional"}
    cargar_competencia(
        conn,
        reg,
        [
            Equipo(1, "teambrbr01", "BR", "USP", "Time", 9, 900),
            Equipo(2, "teamsobo078", "BO", "UMSS", "Wasos del valle", 6, 625),
            Equipo(3, "teamsobo069", "BO", "UMSA", "Duck Duck Gauss", 4, 468),
        ],
    )
    cargar_competencia(conn, nac, [Equipo(1, "teamsoboch026", "BO", "UMSS", "Que ganó", 7, 930)])


def test_plantilla_solo_bolivianos_de_la_regional(conn, tmp_path):
    _poblar(conn)
    ruta = tmp_path / "integrantes.csv"
    assert generar_plantilla(conn, ruta) == 2
    filas = leer_plantilla(ruta)
    assert len(filas) == 8  # 2 equipos x (3 concursantes + 1 coach)
    assert {f["login"] for f in filas} == {"teamsobo078", "teamsobo069"}
    assert [f["rol"] for f in filas[:4]] == ["concursante"] * 3 + ["coach"]


def test_plantilla_no_reescribe_lo_llenado(conn, tmp_path):
    _poblar(conn)
    ruta = tmp_path / "integrantes.csv"
    generar_plantilla(conn, ruta)
    filas = leer_plantilla(ruta)
    filas[0]["nombre"] = "Juan Pérez"
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(filas)
    assert generar_plantilla(conn, ruta) == 0  # no hay equipos nuevos
    assert generar_plantilla(conn, ruta, incluir_nacional=True) == 1  # agrega el del nacional
    filas = leer_plantilla(ruta)
    assert filas[0]["nombre"] == "Juan Pérez" and len(filas) == 12


def test_cargar_y_cobertura(conn, tmp_path):
    _poblar(conn)
    ruta = tmp_path / "integrantes.csv"
    generar_plantilla(conn, ruta, incluir_nacional=True)
    filas = leer_plantilla(ruta)
    wasos = [f for f in filas if f["login"] == "teamsobo078"]
    for f, nombre in zip(wasos, ["Ana", "Beto", "Carla", "Coach X"], strict=True):
        f["nombre"] = nombre
    duck = [f for f in filas if f["login"] == "teamsobo069"]
    duck[0]["cf_handle"] = "duck1"
    nac = [f for f in filas if f["login"] == "teamsoboch026"]
    nac[0]["nombre"] = "ana"  # misma persona que en la regional (mismo nombre y universidad)

    conteo = cargar_integrantes(conn, filas)
    assert conteo == {"filas": 6, "filas_sin_equipo": 0}
    assert conn.execute("SELECT COUNT(*) FROM personas").fetchone()[0] == 5
    por_slug = {c["slug"]: c for c in cobertura(conn)}
    assert por_slug["latam-2025"] == {
        "slug": "latam-2025",
        "tipo": "regional",
        "equipos": 2,
        "completos": 1,
        "parciales": 1,
        "con_coach": 1,
    }
    # Recargar es idempotente, y borrar un nombre del CSV lo quita de la base.
    cargar_integrantes(conn, filas)
    assert conn.execute("SELECT COUNT(*) FROM integrantes").fetchone()[0] == 6
    wasos[2]["nombre"] = ""
    cargar_integrantes(conn, filas)
    assert conn.execute("SELECT COUNT(*) FROM integrantes").fetchone()[0] == 5


def test_equipo_inexistente(conn):
    filas = [{"slug": "latam-1999", "login": "x", "nombre": "A", "rol": "concursante"}]
    assert cargar_integrantes(conn, filas) == {"filas": 0, "filas_sin_equipo": 1}
