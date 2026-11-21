"""Predice el ranking de una lista de equipos inscritos (Fase 8).

Uso:
    python -m models.predict inscritos.csv --tipo nacional --fecha 2027-08-28 --nombre nac-2027

CSV de entrada (UTF-8): columnas `equipo` y `universidad` (obligatorias) y `pais` (opcional, por
defecto BO). Columnas extra (integrantes, handles…) se ignoran por ahora: el modelo actual no usa
integrantes.

Modelo: Ridge sobre pct_bo (ver reports/fase6_baseline.md), entrenado SOLO con competencias de
fecha anterior a --fecha, así que también sirve para "re-jugar" competencias pasadas sin fuga.
La predicción se guarda en data/predicciones/<fecha>_<nombre>.csv.
"""

import argparse
from datetime import date

import numpy as np
import pandas as pd

from db.crear import RAIZ, RUTA_DB, conectar
from features.build_dataset import RUTA_DATASET
from features.elo import elo_a_la_fecha
from features.universidad import cargar_resultados, construir_features, normalizar_universidad
from features.universidad_cf import cargar_historial_por_universidad, features_cf_universidad
from matching.personas import normalizar_nombre
from models.modelos import preparar_ridge

DIR_PREDICCIONES = RAIZ / "data" / "predicciones"

ETIQUETAS = {
    "eq_pct_previo": "resultado previo del equipo",
    "eq_previo_nacional": "su último resultado fue en el nacional",
    "eq_apariciones_previas": "veces que el equipo compitió antes",
    "uni_cf_usuarios_12m": "usuarios activos en CF de la universidad",
    "uni_cf_top3_rating": "rating CF de los 3 mejores de la universidad",
    "uni_cf_max_rating": "mejor rating CF de la universidad",
    "uni_media_pct_3a_nacional": "historial de la universidad en el nacional",
    "uni_mejor_pct_3a_nacional": "mejor resultado de la universidad en el nacional (3 años)",
    "uni_mejor_pct_ultima_nacional": "resultado de la universidad en el último nacional",
    "uni_comps_previas_nacional": "nacionales jugados por la universidad",
    "uni_media_pct_3a_regional": "historial de la universidad en la regional",
    "uni_mejor_pct_3a_regional": "mejor resultado de la universidad en la regional (3 años)",
    "uni_mejor_pct_ultima_regional": "resultado de la universidad en la última regional",
    "uni_comps_previas_regional": "regionales jugadas por la universidad",
    "uni_equipos_en_comp": "equipos de la universidad inscritos",
    "uni_elo": "Elo de la universidad",
    "uni_elo_partidas": "competencias con Elo de la universidad",
    "es_regional": "tipo de competencia",
}


def leer_inscritos(ruta) -> pd.DataFrame:
    df = pd.read_csv(ruta, dtype=str).fillna("")
    faltan = {"equipo", "universidad"} - set(df.columns)
    if faltan:
        raise ValueError(f"Faltan columnas en el CSV: {sorted(faltan)}")
    if "pais" not in df:
        df["pais"] = "BO"
    df["pais"] = df["pais"].replace("", "BO").str.upper()
    return df[["equipo", "universidad", "pais"]]


def features_inscritos(conn, inscritos: pd.DataFrame, tipo: str, fecha: date) -> pd.DataFrame:
    """Features "a la fecha" de los equipos inscritos, igual que en el dataset de entrenamiento."""
    historico = cargar_resultados(conn)
    nuevos = pd.DataFrame(
        {
            "equipo_id": -np.arange(1, len(inscritos) + 1),
            "competencia_id": -1,
            "slug": "prediccion",
            "tipo": tipo,
            "fecha": fecha,
            "n_equipos": len(inscritos),
            "pais": inscritos["pais"].to_numpy(),
            "universidad": inscritos["universidad"].replace("", None).to_numpy(),
            "nombre": inscritos["equipo"].to_numpy(),
            "posicion": np.nan,
            "pct": np.nan,
        }
    )
    nuevos["uni"] = nuevos["universidad"].map(normalizar_universidad)
    nuevos["nombre_norm"] = nuevos["nombre"].map(normalizar_nombre)
    todo = pd.concat([historico, nuevos], ignore_index=True)

    feats = construir_features(todo).drop(columns="competencia_id")
    elo = elo_a_la_fecha(todo)
    out = nuevos.merge(feats, on="equipo_id").merge(elo, on="equipo_id")
    hist = cargar_historial_por_universidad(conn)
    cf = [
        features_cf_universidad(hist, u, fecha)
        if isinstance(u, str)
        else {"uni_cf_usuarios_12m": None, "uni_cf_max_rating": None, "uni_cf_top3_rating": None}
        for u in out["uni"]
    ]
    return pd.concat([out.reset_index(drop=True), pd.DataFrame(cf)], axis=1)


def explicar(modelo, x: pd.DataFrame, n: int = 3) -> list[str]:
    """Las n contribuciones más grandes (coeficiente × valor estandarizado) de cada equipo."""
    escalador, ridge = modelo[0], modelo[-1]
    contrib = pd.DataFrame(escalador.transform(x) * ridge.coef_, columns=x.columns)
    contrib = contrib.T.groupby(lambda c: c.removesuffix("_falta")).sum().T
    textos = []
    for _, fila in contrib.iterrows():
        top = fila.reindex(fila.abs().sort_values(ascending=False).index)[:n]
        partes = [f"{'↑' if v < 0 else '↓'} {ETIQUETAS.get(f, f)}" for f, v in top.items()]
        textos.append("; ".join(partes))
    return textos


def predecir(
    conn, inscritos: pd.DataFrame, tipo: str, fecha: date, dataset: pd.DataFrame | None = None
) -> pd.DataFrame:
    if dataset is None:
        dataset = pd.read_parquet(RUTA_DATASET)
    dataset = dataset[dataset["pais"] == "BO"]
    train = dataset[pd.to_datetime(dataset["fecha"]) < pd.Timestamp(fecha)]
    if train.empty:
        raise ValueError(f"No hay competencias anteriores a {fecha} para entrenar")
    feats = features_inscritos(conn, inscritos, tipo, fecha)
    modelo, x = preparar_ridge(train, feats)
    feats["puntaje"] = modelo.predict(x)
    feats["explicacion"] = explicar(modelo, x)
    feats["posicion_predicha"] = feats["puntaje"].rank(method="first").astype(int)
    columnas = [
        "posicion_predicha",
        "nombre",
        "universidad",
        "pais",
        "puntaje",
        "explicacion",
        "eq_pct_previo",
        "uni_media_pct_3a_nacional",
        "uni_cf_top3_rating",
    ]
    return (
        feats[columnas]
        .rename(columns={"nombre": "equipo"})
        .sort_values("posicion_predicha")
        .reset_index(drop=True)
    )


def guardar(pred: pd.DataFrame, fecha: date, nombre: str):
    DIR_PREDICCIONES.mkdir(parents=True, exist_ok=True)
    ruta = DIR_PREDICCIONES / f"{fecha.isoformat()}_{nombre}.csv"
    pred.to_csv(ruta, index=False)
    return ruta


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("inscritos")
    parser.add_argument("--tipo", choices=["nacional", "regional"], required=True)
    parser.add_argument("--fecha", required=True, type=date.fromisoformat)
    parser.add_argument("--nombre", default="prediccion")
    args = parser.parse_args()

    conn = conectar(RUTA_DB)
    pred = predecir(conn, leer_inscritos(args.inscritos), args.tipo, args.fecha)
    ruta = guardar(pred, args.fecha, args.nombre)
    with pd.option_context("display.max_colwidth", 70, "display.width", 200):
        print(
            pred[["posicion_predicha", "equipo", "universidad", "explicacion"]]
            .head(25)
            .to_string(index=False)
        )
    print(f"\n{len(pred)} equipos. Guardado en {ruta.relative_to(RAIZ)}")
    conn.close()


if __name__ == "__main__":
    main()
