import httpx
import pytest

from scrapers.codeforces import (
    descargar_historiales,
    filtrar_por_pais,
    guardar_candidatos,
    parsear_historial,
    validar_respuesta,
)
from scrapers.http import ClienteHTTP, ErrorPermanente, ErrorTransitorio
from tests.conftest import cargar_fixture


def test_filtrar_por_pais():
    usuarios = cargar_fixture("codeforces/user_ratedList.json")["result"]
    filas = filtrar_por_pais(usuarios, "Bolivia")
    assert [f["handle"] for f in filas] == ["jperez", "ana_q"]
    jp = filas[0]
    assert jp["nombre"] == "Juan" and jp["apellido"] == "Pérez"
    assert jp["organizacion"] == "UMSS" and jp["ciudad"] == "Cochabamba"
    assert jp["rating"] == 1650 and jp["max_rating"] == 1802
    assert jp["fecha_registro"] == "2019-01-01T00:00:00Z"
    assert filas[1]["organizacion"] is None


def test_parsear_historial():
    cambios = cargar_fixture("codeforces/user_rating_jperez.json")["result"]
    filas = parsear_historial(cambios, "jperez")
    assert filas[0] == ("codeforces", "jperez", "2021-01-01T00:00:00Z", 1400, "1100")
    assert len(filas) == 3


def test_guardar_candidatos_conserva_estado(conn):
    usuarios = cargar_fixture("codeforces/user_ratedList.json")["result"]
    filas = filtrar_por_pais(usuarios, "Bolivia")
    guardar_candidatos(conn, filas, "2026-11-20T00:00:00Z")
    conn.execute("UPDATE cf_usuarios SET estado_historial='ok' WHERE handle='jperez'")
    filas[0]["rating"] = 1700
    guardar_candidatos(conn, filas, "2026-11-21T00:00:00Z")
    fila = conn.execute(
        "SELECT rating, estado_historial FROM cf_usuarios WHERE handle='jperez'"
    ).fetchone()
    assert fila == (1700, "ok")


def _resp(status, json):
    return httpx.Response(status, json=json)


def test_validar_respuesta():
    validar_respuesta(_resp(200, {"status": "OK", "result": []}))
    with pytest.raises(ErrorPermanente):
        validar_respuesta(
            _resp(400, {"status": "FAILED", "comment": "handle: User with handle x not found"})
        )
    with pytest.raises(ErrorTransitorio):
        validar_respuesta(_resp(400, {"status": "FAILED", "comment": "Call limit exceeded"}))
    with pytest.raises(ErrorTransitorio):
        validar_respuesta(httpx.Response(503, text="<html>"))


def test_descargar_historiales_ok_y_fallido(conn, tmp_path):
    rating = cargar_fixture("codeforces/user_rating_jperez.json")

    def responder(request: httpx.Request) -> httpx.Response:
        if request.url.params["handle"] == "jperez":
            return _resp(200, rating)
        return _resp(400, {"status": "FAILED", "comment": "handle: User not found"})

    for h in ("jperez", "borrado"):
        conn.execute(
            "INSERT INTO cf_usuarios (handle, fecha_descarga) VALUES (?, '2026-11-20T00:00:00Z')",
            (h,),
        )
    cliente = ClienteHTTP(
        "codeforces", intervalo=0, dir_raw=tmp_path, transporte=httpx.MockTransport(responder)
    )
    conteo = descargar_historiales(cliente, conn)
    assert conteo == {"ok": 1, "fallido": 1}
    estados = dict(conn.execute("SELECT handle, estado_historial FROM cf_usuarios"))
    assert estados == {"jperez": "ok", "borrado": "fallido"}
    n = conn.execute("SELECT COUNT(*) FROM historial_rating WHERE handle='jperez'").fetchone()[0]
    assert n == 3
    # Segunda corrida: no quedan pendientes.
    assert descargar_historiales(cliente, conn) == {"ok": 0, "fallido": 0}
