"""Normalización de nombres y alta/deduplicación de personas.

Regla de deduplicación (Fase 3, aprobada):
1. Si la fila trae handle de Codeforces y ese handle ya está vinculado a una persona, es esa.
2. Si no, misma persona = mismo `nombre_normalizado` + misma universidad normalizada.
La coincidencia aproximada (apellidos invertidos, un solo apellido, typos) es de la Fase 4.
"""

import re
import sqlite3

from unidecode import unidecode


def normalizar_nombre(nombre: str | None) -> str:
    """'  José  PÉREZ-Quispe ' -> 'jose perez quispe'.

    Sin tildes, minúsculas, solo letras/dígitos separados por un espacio.
    """
    if not isinstance(nombre, str) or not nombre:
        return ""
    texto = unidecode(nombre).lower()
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return " ".join(texto.split())


def normalizar_universidad(universidad: str | None) -> str:
    return normalizar_nombre(universidad)


def buscar_por_handle(conn: sqlite3.Connection, plataforma: str, handle: str) -> int | None:
    fila = conn.execute(
        "SELECT persona_id FROM cuentas WHERE plataforma = ? AND handle = ? COLLATE NOCASE",
        (plataforma, handle),
    ).fetchone()
    return fila[0] if fila else None


def buscar_por_nombre(conn: sqlite3.Connection, nombre: str, universidad: str | None) -> int | None:
    clave = normalizar_nombre(nombre)
    if not clave:
        return None
    uni = normalizar_universidad(universidad)
    for persona_id, uni_persona in conn.execute(
        "SELECT id, universidad FROM personas WHERE nombre_normalizado = ?", (clave,)
    ):
        if normalizar_universidad(uni_persona) == uni:
            return persona_id
    return None


def obtener_o_crear_persona(
    conn: sqlite3.Connection,
    nombre: str | None,
    universidad: str | None,
    pais: str | None,
    cf_handle: str | None = None,
    fuente: str = "manual",
) -> int:
    """Devuelve el id de la persona, creándola si no existe.

    Si se da `cf_handle`, queda vinculado en `cuentas` como verificado (lo dio una fuente que
    conoce al equipo). Si la persona solo tiene handle, su nombre provisional es el handle.
    """
    nombre = (nombre or "").strip()
    cf_handle = (cf_handle or "").strip() or None
    if not nombre and not cf_handle:
        raise ValueError("Hace falta nombre o handle")

    persona_id = buscar_por_handle(conn, "codeforces", cf_handle) if cf_handle else None
    if persona_id is None and nombre:
        persona_id = buscar_por_nombre(conn, nombre, universidad)

    if persona_id is None:
        visible = nombre or cf_handle
        persona_id = conn.execute(
            "INSERT INTO personas (nombre, nombre_normalizado, universidad, pais)"
            " VALUES (?, ?, ?, ?)",
            (visible, normalizar_nombre(visible), universidad, pais),
        ).lastrowid
    elif nombre:
        # Si la persona se creó solo con su handle, completar el nombre real.
        conn.execute(
            "UPDATE personas SET nombre = ?, nombre_normalizado = ?"
            " WHERE id = ? AND nombre_normalizado = ?",
            (nombre, normalizar_nombre(nombre), persona_id, normalizar_nombre(cf_handle or "")),
        )

    if cf_handle and buscar_por_handle(conn, "codeforces", cf_handle) is None:
        conn.execute(
            "INSERT INTO cuentas (persona_id, plataforma, handle, confianza, verificado, fuente)"
            " VALUES (?, 'codeforces', ?, 1.0, 1, ?)",
            (persona_id, cf_handle, fuente),
        )
    return persona_id
