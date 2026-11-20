"""Cliente HTTP común: caché en disco, límite de velocidad y reintentos.

Cada respuesta exitosa se guarda comprimida en data/raw/<plataforma>/<clave>.json.gz junto con
la URL, los parámetros y la fecha de descarga. Si la respuesta ya está en caché no se vuelve a
pedir (salvo `refrescar=True`).
"""

import gzip
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

RAIZ = Path(__file__).resolve().parent.parent
DIR_RAW = RAIZ / "data" / "raw"
USER_AGENT = "icpc-predictor/0.1 (proyecto personal de investigacion)"

# Segundos mínimos entre dos peticiones reales a la misma plataforma.
INTERVALOS = {
    "codeforces": 2.0,
    "atcoder": 5.0,
    "codechef": 10.0,
    "scorelatam": 3.0,
}


class ErrorTransitorio(Exception):
    """Error que vale la pena reintentar (timeout, 429, 5xx, límite de llamadas)."""


class ErrorPermanente(Exception):
    """Error que no se arregla reintentando (404, handle inexistente, etc.)."""


def clave_cache(url: str, params: dict[str, Any] | None) -> str:
    texto = url + "?" + json.dumps(params or {}, sort_keys=True)
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()


class ClienteHTTP:
    def __init__(
        self,
        plataforma: str,
        intervalo: float | None = None,
        dir_raw: Path = DIR_RAW,
        timeout: float = 60.0,
        transporte: httpx.BaseTransport | None = None,
        intentos: int = 6,
        espera_reintento_min: float = 4.0,
    ):
        self.plataforma = plataforma
        self.intervalo = INTERVALOS.get(plataforma, 2.0) if intervalo is None else intervalo
        self.dir_cache = Path(dir_raw) / plataforma
        self._ultima_peticion = 0.0
        self.peticiones_reales = 0
        self.intentos = intentos
        self.espera_reintento_min = espera_reintento_min
        self._http = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
            transport=transporte,
        )

    # --- caché ---------------------------------------------------------------
    def ruta_cache(self, url: str, params: dict[str, Any] | None = None) -> Path:
        return self.dir_cache / f"{clave_cache(url, params)}.json.gz"

    def leer_cache(self, url: str, params: dict[str, Any] | None = None) -> Any | None:
        ruta = self.ruta_cache(url, params)
        if not ruta.exists():
            return None
        with gzip.open(ruta, "rt", encoding="utf-8") as f:
            return json.load(f)["body"]

    def _guardar_cache(self, url: str, params: dict[str, Any] | None, body: Any) -> None:
        ruta = self.ruta_cache(url, params)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        registro = {
            "url": url,
            "params": params or {},
            "fecha_descarga": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "body": body,
        }
        tmp = ruta.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(registro, f, ensure_ascii=False)
        tmp.replace(ruta)

    # --- red -----------------------------------------------------------------
    def _esperar_turno(self) -> None:
        espera = self.intervalo - (time.monotonic() - self._ultima_peticion)
        if espera > 0:
            time.sleep(espera)
        self._ultima_peticion = time.monotonic()

    def _pedir(self, url: str, params: dict[str, Any] | None) -> httpx.Response:
        self._esperar_turno()
        self.peticiones_reales += 1
        try:
            resp = self._http.get(url, params=params)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            raise ErrorTransitorio(f"{type(e).__name__}: {e}") from e
        if resp.status_code == 429 or resp.status_code >= 500:
            raise ErrorTransitorio(f"HTTP {resp.status_code} en {url}")
        return resp

    def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        refrescar: bool = False,
        validar=None,
    ) -> Any:
        """Devuelve el JSON de la URL, desde caché si existe.

        `validar(resp)` puede lanzar ErrorTransitorio/ErrorPermanente según el contenido; solo
        se cachean las respuestas que pasan la validación.
        """
        if not refrescar:
            en_cache = self.leer_cache(url, params)
            if en_cache is not None:
                return en_cache

        def pedir_y_validar() -> Any:
            resp = self._pedir(url, params)
            if validar is not None:
                validar(resp)
            elif resp.status_code >= 400:
                raise ErrorPermanente(f"HTTP {resp.status_code} en {url}")
            return resp.json()

        reintentos = Retrying(
            retry=retry_if_exception_type(ErrorTransitorio),
            # Espera min, 2·min, 4·min… hasta 120 s (min=4 → 4, 8, 16, 32, 64 s).
            wait=wait_exponential(
                multiplier=self.espera_reintento_min / 2, min=self.espera_reintento_min, max=120
            ),
            stop=stop_after_attempt(self.intentos),
            reraise=True,
        )
        body = reintentos(pedir_y_validar)
        self._guardar_cache(url, params, body)
        return body

    def cerrar(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.cerrar()
