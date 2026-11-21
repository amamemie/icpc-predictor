"""Descarga de usuarios e historial de rating de Codeforces.

Uso:
    python -m scrapers.codeforces candidatos [--pais Bolivia]
    python -m scrapers.codeforces historiales [--reintentar-fallidos] [--limite N]
"""

import argparse
import logging
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import httpx

from db.crear import RUTA_DB, crear_db
from scrapers.http import ClienteHTTP, ErrorPermanente, ErrorTransitorio

API = "https://codeforces.com/api"
PLATAFORMA = "codeforces"

log = logging.getLogger(__name__)


def _iso(segundos: int | None) -> str | None:
    if segundos is None:
        return None
    return datetime.fromtimestamp(segundos, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ahora() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def validar_respuesta(resp: httpx.Response) -> None:
    """Clasifica los errores de la API de Codeforces."""
    try:
        datos = resp.json()
    except ValueError as e:
        if resp.status_code == 429 or resp.status_code >= 500:
            raise ErrorTransitorio(f"HTTP {resp.status_code}") from e
        raise ErrorPermanente(f"Respuesta no JSON (HTTP {resp.status_code})") from e
    if datos.get("status") == "OK":
        return
    comentario = datos.get("comment", "")
    if "limit exceeded" in comentario.lower() or resp.status_code >= 500:
        raise ErrorTransitorio(comentario or f"HTTP {resp.status_code}")
    raise ErrorPermanente(comentario or f"HTTP {resp.status_code}")


def llamar(cliente: ClienteHTTP, metodo: str, refrescar: bool = False, **params: Any) -> Any:
    body = cliente.get_json(
        f"{API}/{metodo}", params=params or None, validar=validar_respuesta, refrescar=refrescar
    )
    return body["result"]


# --- Candidatos -------------------------------------------------------------------------------


def filtrar_por_pais(usuarios: Iterable[dict], pais: str) -> list[dict]:
    """Convierte los usuarios de `user.ratedList` del país dado en filas de cf_usuarios."""
    filas = []
    for u in usuarios:
        if u.get("country") != pais:
            continue
        filas.append(
            {
                "handle": u["handle"],
                "nombre": u.get("firstName"),
                "apellido": u.get("lastName"),
                "organizacion": u.get("organization"),
                "ciudad": u.get("city"),
                "pais": u.get("country"),
                "rating": u.get("rating"),
                "max_rating": u.get("maxRating"),
                "fecha_registro": _iso(u.get("registrationTimeSeconds")),
            }
        )
    return filas


def guardar_candidatos(conn: sqlite3.Connection, filas: list[dict], fecha_descarga: str) -> int:
    """Inserta o actualiza candidatos sin perder el estado de su historial."""
    conn.executemany(
        """
        INSERT INTO cf_usuarios (handle, nombre, apellido, organizacion, ciudad, pais,
                                 rating, max_rating, fecha_registro, fecha_descarga)
        VALUES (:handle, :nombre, :apellido, :organizacion, :ciudad, :pais,
                :rating, :max_rating, :fecha_registro, :fecha_descarga)
        ON CONFLICT(handle) DO UPDATE SET
            nombre = excluded.nombre, apellido = excluded.apellido,
            organizacion = excluded.organizacion, ciudad = excluded.ciudad,
            pais = excluded.pais, rating = excluded.rating, max_rating = excluded.max_rating,
            fecha_registro = excluded.fecha_registro, fecha_descarga = excluded.fecha_descarga
        """,
        [{**f, "fecha_descarga": fecha_descarga} for f in filas],
    )
    conn.commit()
    return len(filas)


def descargar_candidatos(
    cliente: ClienteHTTP, conn: sqlite3.Connection, pais: str, refrescar: bool = False
) -> int:
    usuarios = llamar(
        cliente, "user.ratedList", refrescar=refrescar, activeOnly="false", includeRetired="true"
    )
    log.info("user.ratedList: %d usuarios en total", len(usuarios))
    filas = filtrar_por_pais(usuarios, pais)
    return guardar_candidatos(conn, filas, _ahora())


# --- Historial de rating ----------------------------------------------------------------------


def parsear_historial(cambios: Iterable[dict], handle: str) -> list[tuple]:
    """Convierte la respuesta de `user.rating` en filas de historial_rating."""
    return [
        (
            PLATAFORMA,
            handle,
            _iso(c["ratingUpdateTimeSeconds"]),
            c["newRating"],
            str(c["contestId"]),
        )
        for c in cambios
    ]


def guardar_historial(conn: sqlite3.Connection, handle: str, filas: list[tuple]) -> None:
    conn.execute(
        "DELETE FROM historial_rating WHERE plataforma = ? AND handle = ?", (PLATAFORMA, handle)
    )
    conn.executemany(
        "INSERT INTO historial_rating (plataforma, handle, fecha, rating, contest_id) "
        "VALUES (?, ?, ?, ?, ?)",
        filas,
    )
    conn.execute(
        "UPDATE cf_usuarios SET estado_historial = 'ok', error_historial = NULL WHERE handle = ?",
        (handle,),
    )
    conn.commit()


def marcar_fallido(conn: sqlite3.Connection, handle: str, error: str) -> None:
    conn.execute(
        "UPDATE cf_usuarios SET estado_historial = 'fallido', error_historial = ? WHERE handle = ?",
        (error[:500], handle),
    )
    conn.commit()


def descargar_historiales(
    cliente: ClienteHTTP,
    conn: sqlite3.Connection,
    reintentar_fallidos: bool = False,
    limite: int | None = None,
    refrescar: bool = False,
) -> dict[str, int]:
    """Descarga historiales pendientes. Con `refrescar`, vuelve a pedir los de TODOS los
    candidatos (para actualizar ratings) guardando una versión nueva en caché."""
    if refrescar:
        estados = ("pendiente", "ok", "fallido")
    elif reintentar_fallidos:
        estados = ("pendiente", "fallido")
    else:
        estados = ("pendiente",)
    marcas = ",".join("?" * len(estados))
    handles = [
        h
        for (h,) in conn.execute(
            f"SELECT handle FROM cf_usuarios WHERE estado_historial IN ({marcas}) ORDER BY handle",
            estados,
        )
    ]
    if limite is not None:
        handles = handles[:limite]

    conteo = {"ok": 0, "fallido": 0}
    for i, handle in enumerate(handles, 1):
        try:
            cambios = llamar(cliente, "user.rating", refrescar=refrescar, handle=handle)
        except (ErrorPermanente, ErrorTransitorio) as e:
            marcar_fallido(conn, handle, str(e))
            conteo["fallido"] += 1
            log.warning("%s: %s", handle, e)
        else:
            guardar_historial(conn, handle, parsear_historial(cambios, handle))
            conteo["ok"] += 1
        if i % 100 == 0 or i == len(handles):
            log.info(
                "%d/%d handles (ok=%d, fallidos=%d, peticiones reales=%d)",
                i,
                len(handles),
                conteo["ok"],
                conteo["fallido"],
                cliente.peticiones_reales,
            )
    return conteo


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)
    p_cand = sub.add_parser("candidatos", help="usuarios con rating de un país")
    p_cand.add_argument("--pais", default="Bolivia")
    p_hist = sub.add_parser("historiales", help="historial de rating de los candidatos")
    p_hist.add_argument("--reintentar-fallidos", action="store_true")
    p_hist.add_argument("--limite", type=int)
    args = parser.parse_args()

    conn = crear_db(RUTA_DB)
    with ClienteHTTP(PLATAFORMA) as cliente:
        if args.comando == "candidatos":
            n = descargar_candidatos(cliente, conn, args.pais)
            log.info("Candidatos de %s guardados: %d", args.pais, n)
        else:
            conteo = descargar_historiales(cliente, conn, args.reintentar_fallidos, args.limite)
            log.info("Historiales: %s", conteo)
    conn.close()


if __name__ == "__main__":
    main()
