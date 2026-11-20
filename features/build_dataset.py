"""Construye el dataset de entrenamiento: una fila por equipo-competencia.

Uso: python -m features.build_dataset   # escribe data/dataset.parquet

Targets (más bajo = mejor):
- pct:     posición / n_equipos, tal como la publica la fuente.
- pct_bo:  percentil dentro de los equipos bolivianos de la competencia (en la regional se
           re-rankean solo los bolivianos). Es el target principal del MVP.
Los empates (mismos resueltos y penalidad) reciben la posición media de su bloque, para que el
orden arbitrario entre, p. ej., los equipos con 0 resueltos no sea ruido.

Features: ver features/universidad.py y features/universidad_cf.py. Todas "a la fecha".
"""

import pandas as pd

from db.crear import RAIZ, RUTA_DB, conectar
from features.universidad import cargar_resultados, construir_features
from features.universidad_cf import cargar_historial_por_universidad, features_cf_universidad

RUTA_DATASET = RAIZ / "data" / "dataset.parquet"


def posicion_con_empates(grupo: pd.DataFrame) -> pd.Series:
    """Posición media del bloque de empate (mismos resueltos y penalidad), en orden de la fuente."""
    orden = grupo.sort_values("posicion")
    rango = pd.Series(range(1, len(orden) + 1), index=orden.index, dtype=float)
    clave = orden["resueltos"].astype(str) + "|" + orden["penalidad"].astype(str)
    return rango.groupby(clave).transform("mean").reindex(grupo.index)


def construir_dataset(conn) -> pd.DataFrame:
    df = cargar_resultados(conn)
    extra = pd.read_sql_query(
        "SELECT r.equipo_id, r.resueltos, r.penalidad, co.año"
        " FROM resultados r JOIN equipos e ON e.id = r.equipo_id"
        " JOIN competencias co ON co.id = e.competencia_id",
        conn,
    )
    df = df.merge(extra, on="equipo_id")

    df["pos_empate"] = df.groupby("competencia_id", group_keys=False).apply(
        posicion_con_empates, include_groups=False
    )
    df["pct_empate"] = df["pos_empate"] / df["n_equipos"]

    bo = df[df["pais"] == "BO"].copy()
    bo["pos_bo"] = bo.groupby("competencia_id", group_keys=False).apply(
        posicion_con_empates, include_groups=False
    )
    bo["n_bo"] = bo.groupby("competencia_id")["equipo_id"].transform("size")
    bo["pct_bo"] = bo["pos_bo"] / bo["n_bo"]
    df = df.merge(bo[["equipo_id", "pos_bo", "n_bo", "pct_bo"]], on="equipo_id", how="left")

    df = df.merge(construir_features(df).drop(columns="competencia_id"), on="equipo_id")

    hist = cargar_historial_por_universidad(conn)
    cache: dict = {}
    filas = []
    for _, e in df.iterrows():
        clave = (e["uni"], e["fecha"])
        if pd.isna(e["uni"]):
            filas.append(
                {"uni_cf_usuarios_12m": None, "uni_cf_max_rating": None, "uni_cf_top3_rating": None}
            )
            continue
        if clave not in cache:
            cache[clave] = features_cf_universidad(hist, e["uni"], e["fecha"])
        filas.append(cache[clave])
    df = pd.concat([df.reset_index(drop=True), pd.DataFrame(filas)], axis=1)
    return df.sort_values(["fecha", "competencia_id", "posicion"]).reset_index(drop=True)


def main() -> None:
    conn = conectar(RUTA_DB)
    df = construir_dataset(conn)
    df.to_parquet(RUTA_DATASET, index=False)
    bo = df[df["pais"] == "BO"]
    print(f"Dataset: {len(df)} filas ({len(bo)} bolivianas), {df.shape[1]} columnas")
    print(f"Guardado en {RUTA_DATASET.relative_to(RAIZ)}")
    conn.close()


if __name__ == "__main__":
    main()
