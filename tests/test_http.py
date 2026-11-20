import httpx
import pytest

from scrapers.http import ClienteHTTP, ErrorPermanente, ErrorTransitorio


def _cliente(tmp_path, responder, **kw):
    return ClienteHTTP(
        "prueba",
        intervalo=0,
        dir_raw=tmp_path,
        transporte=httpx.MockTransport(responder),
        espera_reintento_min=0,
        **kw,
    )


def test_cache_evita_segunda_peticion(tmp_path):
    llamadas = []

    def responder(request):
        llamadas.append(request.url)
        return httpx.Response(200, json={"x": 1})

    c = _cliente(tmp_path, responder)
    assert c.get_json("https://ejemplo.org/a", {"p": 1}) == {"x": 1}
    assert c.get_json("https://ejemplo.org/a", {"p": 1}) == {"x": 1}
    assert len(llamadas) == 1 and c.peticiones_reales == 1
    assert c.ruta_cache("https://ejemplo.org/a", {"p": 1}).exists()
    # Otro cliente lee el mismo caché del disco.
    c2 = _cliente(tmp_path, responder)
    assert c2.get_json("https://ejemplo.org/a", {"p": 1}) == {"x": 1}
    assert len(llamadas) == 1


def test_reintenta_errores_transitorios(tmp_path):
    respuestas = iter([httpx.Response(503), httpx.Response(429), httpx.Response(200, json=[1])])
    c = _cliente(tmp_path, lambda r: next(respuestas))
    assert c.get_json("https://ejemplo.org/b") == [1]
    assert c.peticiones_reales == 3


def test_se_rinde_tras_n_intentos(tmp_path):
    c = _cliente(tmp_path, lambda r: httpx.Response(503), intentos=3)
    with pytest.raises(ErrorTransitorio):
        c.get_json("https://ejemplo.org/c")
    assert c.peticiones_reales == 3


def test_error_permanente_no_se_reintenta_ni_cachea(tmp_path):
    c = _cliente(tmp_path, lambda r: httpx.Response(404))
    with pytest.raises(ErrorPermanente):
        c.get_json("https://ejemplo.org/d")
    assert c.peticiones_reales == 1
    assert not c.ruta_cache("https://ejemplo.org/d").exists()


def test_descargar_archivo_no_repite(tmp_path):
    llamadas = []

    def responder(request):
        llamadas.append(1)
        return httpx.Response(200, text="<html>ok</html>")

    c = _cliente(tmp_path, responder)
    destino = tmp_path / "x" / "p.html"
    c.descargar_archivo("https://ejemplo.org/p", destino)
    c.descargar_archivo("https://ejemplo.org/p", destino)
    assert destino.read_text() == "<html>ok</html>"
    assert len(llamadas) == 1
