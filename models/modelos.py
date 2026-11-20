"""Modelos entrenados: Ridge sobre el percentil y LightGBM LambdaRank. Puntaje más bajo = mejor.

Con tan pocos datos se usan hiperparámetros fijos y conservadores (sin Optuna todavía).
"""

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = [
    "es_regional",
    "uni_equipos_en_comp",
    "uni_comps_previas_nacional",
    "uni_mejor_pct_ultima_nacional",
    "uni_mejor_pct_3a_nacional",
    "uni_media_pct_3a_nacional",
    "uni_comps_previas_regional",
    "uni_mejor_pct_ultima_regional",
    "uni_mejor_pct_3a_regional",
    "uni_media_pct_3a_regional",
    "eq_pct_previo",
    "eq_previo_nacional",
    "eq_apariciones_previas",
    "uni_cf_usuarios_12m",
    "uni_cf_max_rating",
    "uni_cf_top3_rating",
]


def matriz(df: pd.DataFrame) -> pd.DataFrame:
    x = pd.DataFrame(index=df.index)
    x["es_regional"] = (df["tipo"] == "regional").astype(float)
    x["eq_previo_nacional"] = (df["eq_tipo_previo"] == "nacional").astype(float)
    for c in FEATURES:
        if c not in x:
            x[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return x[FEATURES]


def ridge(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Ridge sobre pct_bo; faltantes = mediana del train + indicador de faltante."""
    xtr, xte = matriz(train), matriz(test)
    medianas = xtr.median()
    for x in (xtr, xte):
        for c in FEATURES:
            x[f"{c}_falta"] = x[c].isna().astype(float)
        x.fillna(medianas, inplace=True)
        x.fillna(0.0, inplace=True)  # columnas sin ningún dato en el train
    modelo = make_pipeline(StandardScaler(), Ridge(alpha=10.0))
    modelo.fit(xtr, train["pct_bo"])
    return modelo.predict(xte[xtr.columns])


def _etiquetas_relevancia(df: pd.DataFrame, niveles: int = 10) -> np.ndarray:
    """Relevancia entera para LambdaRank: 0 (peor) … niveles-1 (mejor)."""
    return np.floor((1 - df["pct_bo"].to_numpy()) * (niveles - 1e-9)).astype(int)


def lgbm_rank(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    train = train.sort_values("competencia_id")
    grupos = train.groupby("competencia_id", sort=True).size().to_numpy()
    modelo = lgb.LGBMRanker(
        objective="lambdarank",
        n_estimators=200,
        learning_rate=0.05,
        num_leaves=7,
        min_child_samples=20,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        random_state=0,
        verbose=-1,
    )
    modelo.fit(matriz(train), _etiquetas_relevancia(train), group=grupos)
    return -modelo.predict(matriz(test))


MODELOS_ML = {"ridge": ridge, "lgbm_lambdarank": lgbm_rank}
