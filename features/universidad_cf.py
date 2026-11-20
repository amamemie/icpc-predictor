"""Fuerza en Codeforces de cada universidad, a la fecha (sustituto del rating del equipo).

Sin integrantes no se sabe el rating de cada equipo, pero sí cuánto talento activo en Codeforces
tiene su universidad. Se usan los usuarios bolivianos de `cf_usuarios` cuya organización se
reconoce como una universidad, y su historial de rating anterior a la fecha de la competencia.

Features para una universidad U en la fecha D:
- uni_cf_usuarios_12m:   usuarios de U con al menos un contest con rating en [D-365d, D).
- uni_cf_max_rating:     rating más alto (a la fecha) entre los usuarios de U activos en 24 meses.
- uni_cf_top3_rating:    media de los 3 mejores ratings (a la fecha) entre esos usuarios.

Riesgo conocido de fuga leve: la organización es la que el usuario tiene HOY en su perfil, no la
que tenía en D. El rating sí es estrictamente anterior a D.
"""

import re
import sqlite3
from datetime import date, timedelta

import pandas as pd

from matching.personas import normalizar_nombre

# (patrón sobre la organización normalizada, sigla). Se prueban en orden.
PATRONES_ORGANIZACION = [
    (r"\bsan andres\b|\bumsa\b", "UMSA"),
    (r"\bsan sim|\bumss\b", "UMSS"),
    (r"catolica boliviana|\bucb\b", "UCB"),
    (r"privada boliviana|\bupb\b", "UPB"),
    (r"facultad nacional de ingenieria|tecnica de oruro|\buto\b", "UTO"),
    (r"\bupsa\b", "UPSA"),
    (r"gabriel rene moreno|\buagrm\b", "UAGRM"),
    (r"domingo savio|\bupds\b", "UPDS"),
    (r"tomas frias|\buatf\b", "UATF"),
    (r"\buajms\b|juan misael saracho", "UAJMS"),
    (r"escuela militar de ingenieria|\bemi\b", "EMI"),
    (r"san francisco xavier|\busfx\b", "USFX"),
    (r"\budabol\b", "UDABOL"),
    (r"tecnologica boliviana", "UTB"),
    (r"salesiana", "USB"),
    (r"\bnur\b", "NUR"),
]


def universidad_de_organizacion(organizacion: str | None) -> str | None:
    texto = normalizar_nombre(organizacion)
    if not texto:
        return None
    for patron, sigla in PATRONES_ORGANIZACION:
        if re.search(patron, texto):
            return sigla
    return None


def cargar_historial_por_universidad(conn: sqlite3.Connection) -> pd.DataFrame:
    """Historial de rating de los usuarios con universidad reconocida (columnas uni, handle,
    fecha, rating)."""
    usuarios = pd.read_sql_query("SELECT handle, organizacion FROM cf_usuarios", conn)
    usuarios["uni"] = usuarios["organizacion"].map(universidad_de_organizacion)
    usuarios = usuarios.dropna(subset=["uni"])
    hist = pd.read_sql_query(
        "SELECT handle, fecha, rating FROM historial_rating WHERE plataforma = 'codeforces'", conn
    )
    hist["fecha"] = pd.to_datetime(hist["fecha"], utc=True)
    return hist.merge(usuarios[["handle", "uni"]], on="handle")


def features_cf_universidad(hist: pd.DataFrame, uni: str, fecha: date) -> dict:
    vacio = {"uni_cf_usuarios_12m": 0, "uni_cf_max_rating": None, "uni_cf_top3_rating": None}
    corte = pd.Timestamp(fecha, tz="UTC")
    h = hist[(hist["uni"] == uni) & (hist["fecha"] < corte)]
    if h.empty:
        return vacio
    ultimo = h.sort_values("fecha").groupby("handle").tail(1)  # rating a la fecha por usuario
    activos_12 = ultimo[ultimo["fecha"] >= corte - timedelta(days=365)]
    activos_24 = ultimo[ultimo["fecha"] >= corte - timedelta(days=730)]
    if activos_24.empty:
        return {**vacio, "uni_cf_usuarios_12m": len(activos_12)}
    top = activos_24["rating"].sort_values(ascending=False)
    return {
        "uni_cf_usuarios_12m": len(activos_12),
        "uni_cf_max_rating": float(top.iloc[0]),
        "uni_cf_top3_rating": float(top.head(3).mean()),
    }
