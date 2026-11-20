"""Consultas sobre la base."""

import sqlite3
from datetime import UTC, date, datetime


def a_iso_utc(momento: date | datetime) -> str:
    """Convierte a texto ISO UTC comparable con las fechas guardadas.

    Una `date` se interpreta como las 00:00 UTC de ese día. Un `datetime` sin zona
    horaria se asume en UTC.
    """
    if not isinstance(momento, datetime):
        momento = datetime(momento.year, momento.month, momento.day, tzinfo=UTC)
    elif momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return momento.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def rating_a_la_fecha(
    conn: sqlite3.Connection, plataforma: str, handle: str, fecha: date | datetime
) -> int | None:
    """Rating del handle justo antes de `fecha` (estrictamente anterior).

    Devuelve None si el handle no tiene ninguna actualización de rating antes de esa fecha.
    """
    fila = conn.execute(
        """
        SELECT rating FROM historial_rating
        WHERE plataforma = ? AND handle = ? AND fecha < ?
        ORDER BY fecha DESC
        LIMIT 1
        """,
        (plataforma, handle, a_iso_utc(fecha)),
    ).fetchone()
    return fila[0] if fila else None
