"""Features de historial de universidad y de equipo (Fase 5, adelantado en la Fase 3).

Regla "a la fecha": las features de un equipo en una competencia con fecha D se calculan solo con
competencias de fecha estrictamente anterior a D.

Features (por equipo-competencia), para T en {nacional, regional}:
- uni_equipos_en_comp:     equipos de la misma universidad en esta competencia (se sabe al
                           inscribirse, no es fuga).
- uni_comps_previas_T:     competencias previas de tipo T en las que participó la universidad.
- uni_mejor_pct_ultima_T:  mejor percentil de la universidad en la última competencia previa de T.
- uni_mejor_pct_3a_T:      mejor percentil de la universidad en competencias de T de los últimos
                           3 años.
- uni_media_pct_3a_T:      percentil medio de todos sus equipos en T en los últimos 3 años.
- eq_pct_previo:           percentil de la última aparición previa de un equipo con el mismo
                           nombre y universidad (cualquier tipo). Los equipos suelen conservar el
                           nombre entre el nacional y la regional y entre años.
- eq_tipo_previo:          tipo de esa aparición (nacional/regional).
- eq_apariciones_previas:  cuántas veces apareció antes ese mismo equipo.

Percentil = posición / n_equipos (0 = primero, 1 = último). Más bajo es mejor.

Uso: python -m features.universidad   # resumen y correlación con el percentil real
"""

import re
import sqlite3
from datetime import date, timedelta

import pandas as pd

from db.crear import RUTA_DB, conectar
from matching.personas import normalizar_nombre

TIPOS = ("nacional", "regional")
VENTANA = timedelta(days=3 * 365)

# Sigla base -> sigla canónica cuando una universidad aparece con nombres distintos.
EQUIVALENCIAS = {
    "UPBLP": "UPB",
    "UV": "UNIVALLE",
    "UNIVERSIDAD TECNICA DE ORURO": "UTO",
    "UNIVERSIDAD MAYOR DE SAN SIMON": "UMSS",
    "UNIVERSIDAD MAYOR DE SAN ANDRES": "UMSA",
}


def normalizar_universidad(universidad: str | None) -> str | None:
    """'UCB-Cochabamba' -> 'UCB', 'UPB - Cbba' -> 'UPB', 'UV-La Paz' -> 'UNIVALLE'.

    Junta las sedes de una misma universidad (más historial por universidad, a costa de no
    distinguir sedes).
    """
    if not isinstance(universidad, str) or not universidad.strip():
        return None
    texto = normalizar_nombre(universidad).upper()
    for nombre_largo, sigla in EQUIVALENCIAS.items():
        if " " in nombre_largo and texto.startswith(nombre_largo):
            return sigla
    base = re.split(r"[\s\-_/]+", texto)[0]
    return EQUIVALENCIAS.get(base, base)


def cargar_resultados(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        """
        SELECT e.id AS equipo_id, co.id AS competencia_id, co.slug, co.tipo, co.fecha,
               co.n_equipos, e.pais, e.universidad, e.nombre, r.posicion
        FROM equipos e
        JOIN competencias co ON co.id = e.competencia_id
        JOIN resultados r ON r.equipo_id = e.id
        """,
        conn,
    )
    if df["fecha"].isna().any():
        faltan = sorted(df.loc[df["fecha"].isna(), "slug"].unique())
        raise ValueError(f"Competencias sin fecha (necesaria para no filtrar): {faltan}")
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.date
    df["pct"] = df["posicion"] / df["n_equipos"]
    df["uni"] = df["universidad"].map(normalizar_universidad)
    df["nombre_norm"] = df["nombre"].map(normalizar_nombre)
    return df


def _features_universidad(previas: pd.DataFrame, uni: str, fecha: date) -> dict:
    f: dict = {}
    de_uni = previas[previas["uni"] == uni]
    for tipo in TIPOS:
        t = de_uni[de_uni["tipo"] == tipo]
        f[f"uni_comps_previas_{tipo}"] = t["competencia_id"].nunique()
        if t.empty:
            f[f"uni_mejor_pct_ultima_{tipo}"] = None
            f[f"uni_mejor_pct_3a_{tipo}"] = None
            f[f"uni_media_pct_3a_{tipo}"] = None
            continue
        ultima = t["fecha"].max()
        f[f"uni_mejor_pct_ultima_{tipo}"] = t.loc[t["fecha"] == ultima, "pct"].min()
        recientes = t[t["fecha"] >= fecha - VENTANA]
        f[f"uni_mejor_pct_3a_{tipo}"] = recientes["pct"].min() if len(recientes) else None
        f[f"uni_media_pct_3a_{tipo}"] = recientes["pct"].mean() if len(recientes) else None
    return f


def _features_equipo(previas: pd.DataFrame, uni: str | None, nombre: str) -> dict:
    vacio = {"eq_pct_previo": None, "eq_tipo_previo": None, "eq_apariciones_previas": 0}
    if not isinstance(nombre, str) or not nombre or pd.isna(uni):
        return vacio
    mismo = previas[(previas["nombre_norm"] == nombre) & (previas["uni"] == uni)]
    if mismo.empty:
        return vacio
    ultima = mismo.sort_values("fecha").iloc[-1]
    return {
        "eq_pct_previo": ultima["pct"],
        "eq_tipo_previo": ultima["tipo"],
        "eq_apariciones_previas": len(mismo),
    }


def construir_features(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por equipo-competencia con las features de universidad y de equipo."""
    filas = []
    for (comp_id, fecha), equipos in df.groupby(["competencia_id", "fecha"]):
        previas = df[df["fecha"] < fecha]
        n_por_uni = equipos["uni"].value_counts()
        cache_uni: dict[str, dict] = {}
        for _, e in equipos.iterrows():
            fila = {"equipo_id": e["equipo_id"], "competencia_id": comp_id}
            if pd.isna(e["uni"]):
                fila["uni_equipos_en_comp"] = None
            else:
                fila["uni_equipos_en_comp"] = int(n_por_uni[e["uni"]])
                if e["uni"] not in cache_uni:
                    cache_uni[e["uni"]] = _features_universidad(previas, e["uni"], fecha)
                fila.update(cache_uni[e["uni"]])
            fila.update(_features_equipo(previas, e["uni"], e["nombre_norm"]))
            filas.append(fila)
    return pd.DataFrame(filas)


def main() -> None:
    conn = conectar(RUTA_DB)
    df = cargar_resultados(conn)
    feats = construir_features(df)
    datos = df[["equipo_id", "slug", "tipo", "pais", "pct"]].merge(feats, on="equipo_id")
    bo = datos[datos["pais"] == "BO"]
    excluir = ("equipo_id", "competencia_id", "eq_tipo_previo")
    columnas = [c for c in feats.columns if c not in excluir]
    print(f"Equipos: {len(datos)} (bolivianos: {len(bo)})\n")
    print("Cobertura y correlación de Spearman con el percentil real (equipos bolivianos):")
    print(f"{'feature':<32} {'% con dato':>10} {'nacional':>9} {'regional':>9}")
    for c in columnas:
        cobertura = bo[c].notna().mean() * 100
        corrs = []
        for tipo in TIPOS:
            sub = bo[(bo["tipo"] == tipo) & bo[c].notna()]
            corr = None
            if len(sub) > 10:
                corr = sub[c].astype(float).corr(sub["pct"], method="spearman")
            corrs.append(f"{corr:+.2f}" if corr is not None and pd.notna(corr) else "   -")
        print(f"{c:<32} {cobertura:>9.0f}% {corrs[0]:>9} {corrs[1]:>9}")
    conn.close()


if __name__ == "__main__":
    main()
