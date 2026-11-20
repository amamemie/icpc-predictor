from pathlib import Path

import pytest

from scrapers.scorelatam import (
    Celda,
    cargar_competencia,
    detectar_formato,
    parsear,
    parsear_celda,
    separar_universidad,
    slug_de_url,
    vista_para,
)

FIX = Path(__file__).parent / "fixtures" / "scorelatam"
BOCA = (FIX / "boca.html").read_text(encoding="utf-8")
MOJ = (FIX / "moj.html").read_text(encoding="utf-8")


def test_parsear_celda():
    assert parsear_celda("A", "2/58") == Celda("A", 2, 58)
    assert parsear_celda("B", "3/-") == Celda("B", 3, None)
    assert parsear_celda("C", "★ 1/20") == Celda("C", 1, 20)
    assert parsear_celda("D", "") is None


def test_separar_universidad():
    assert separar_universidad("[UMSS]  Wasos del valle") == ("UMSS", "Wasos del valle")
    assert separar_universidad("[] !LoCTuDime") == (None, "!LoCTuDime")
    assert separar_universidad("Sin corchetes") == (None, "Sin corchetes")


def test_detectar_formato():
    assert detectar_formato(BOCA) == "boca"
    assert detectar_formato(MOJ) == "moj"


def test_boca_vista_por_toggle_group_no_por_posicion():
    # "Bolivia(" es el 3.er enlace pero llama a toggleGroup(5).
    equipos = parsear(BOCA, "Bolivia")
    assert [e.login for e in equipos] == ["teamsobo078", "teamsobo003", "teamsoar007"]
    assert [e.posicion for e in equipos] == [1, 2, 3]


def test_boca_campos_del_equipo():
    wasos = parsear(BOCA, "Bolivia")[0]
    assert wasos.nombre == "Wasos del valle"  # sin el texto tras <br>
    assert wasos.universidad == "UMSS"
    assert (wasos.resueltos, wasos.penalidad) == (1, 300)
    assert wasos.celdas == [Celda("A", 10, None), Celda("B", 2, 280)]


def test_boca_pais_desde_la_bandera():
    equipos = {e.login: e for e in parsear(BOCA, "Bolivia")}
    assert equipos["teamsobo003"].pais == "BO"  # sufijo /SO es la subregión
    assert equipos["teamsoar007"].pais == "UY"  # bandera "ur" de BOCA -> ISO UY
    assert equipos["teamsobo003"].universidad is None


def test_boca_global_y_posicion_de_la_vista():
    equipos = parsear(BOCA, "Global")
    assert [(e.posicion, e.login) for e in equipos] == [(1, "teambrsp01"), (2, "teamsobo078")]


def test_boca_excluye_ccl():
    with pytest.raises(ValueError):
        parsear(BOCA, "Inexistente")
    # La vista Bolivia-CCL solo tiene un equipo CCL -> queda vacía.
    assert parsear(BOCA, "Bolivia-CCL") == []


def test_moj_global_excluye_guest_y_mantiene_orden():
    equipos = parsear(MOJ, "Global")
    assert [e.login for e in equipos] == [
        "teambrspsp001",
        "teambolapa004",
        "teambolapa009",
        "teambococh029",
    ]
    # Empate en data-place=3: se numera 1..n en el orden de la página.
    assert [e.posicion for e in equipos] == [1, 2, 3, 4]


def test_moj_vista_bolivia_de_nivel_0_recalcula_posicion():
    equipos = parsear(MOJ, "Bolivia")
    assert [(e.posicion, e.login) for e in equipos] == [
        (1, "teambolapa004"),
        (2, "teambolapa009"),
        (3, "teambococh029"),
    ]


def test_moj_campos_del_equipo():
    maq = parsear(MOJ, "Bolivia")[0]
    assert maq.nombre == "Los Maquinolas"  # sin insignias de clasificado
    assert maq.universidad == "UMSA" and maq.pais == "BO"
    assert (maq.resueltos, maq.penalidad) == (1, 30)
    assert maq.celdas == [Celda("A", 2, None), Celda("B", 3, 10)]


def test_slug_y_vista():
    assert slug_de_url("https://scorelatam.naquadah.com.br/latam-2025/") == "latam-2025"
    assert vista_para("nacional") == "Bolivia"
    assert vista_para("regional") == "Global"


def test_cargar_competencia_reemplaza(conn):
    comp = {
        "slug": "subbr-2026",
        "nombre": "Nacional",
        "tipo": "nacional",
        "año": "2026",
        "fecha": "2026-08-29",
        "formato": "moj",
        "url_scoreboard": "https://x/subbr-2026/",
    }
    equipos = parsear(MOJ, "Bolivia")
    cargar_competencia(conn, comp, equipos)
    cargar_competencia(conn, comp, equipos)  # segunda vez no duplica
    assert conn.execute("SELECT COUNT(*), MAX(n_equipos) FROM competencias").fetchone() == (1, 3)
    assert conn.execute("SELECT COUNT(*) FROM equipos").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM resultados").fetchone()[0] == 3
    assert conn.execute("SELECT SUM(resuelto), COUNT(*) FROM celdas").fetchone() == (1, 3)
