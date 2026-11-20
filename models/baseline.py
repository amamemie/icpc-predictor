"""Baselines heurísticos (sin entrenamiento). Puntaje más bajo = mejor.

Sin integrantes no existe el baseline "rating máximo de CF del equipo" de CLAUDE.md; su sustituto
más cercano es el rating de los mejores usuarios de CF de la universidad.
"""

import numpy as np
import pandas as pd

SIN_DATO = 1.0  # sin historial se asume el peor percentil


def _primero_disponible(test: pd.DataFrame, columnas: list[str], defecto: float) -> np.ndarray:
    valores = pd.Series(np.nan, index=test.index)
    for c in columnas:
        valores = valores.fillna(test[c].astype(float))
    return valores.fillna(defecto).to_numpy()


def azar(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    return np.random.default_rng(0).random(len(test))


def historial_universidad(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Percentil medio de la universidad en los últimos 3 años (mismo tipo primero)."""
    puntajes = np.empty(len(test))
    for i, (_, e) in enumerate(test.iterrows()):
        otro = "regional" if e["tipo"] == "nacional" else "nacional"
        orden = [f"uni_media_pct_3a_{e['tipo']}", f"uni_media_pct_3a_{otro}"]
        valor = next((e[c] for c in orden if pd.notna(e[c])), SIN_DATO)
        puntajes[i] = valor
    return puntajes


def equipo_previo(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Último percentil del mismo equipo; si no hay, el historial de la universidad."""
    base = historial_universidad(train, test)
    previo = test["eq_pct_previo"].astype(float).to_numpy()
    return np.where(np.isnan(previo), base, previo)


def rating_cf_universidad(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Media de los 3 mejores ratings de CF de la universidad (a la fecha)."""
    return -_primero_disponible(test, ["uni_cf_top3_rating"], defecto=0.0)


MODELOS_BASE = {
    "azar": azar,
    "historial_universidad": historial_universidad,
    "equipo_previo": equipo_previo,
    "rating_cf_universidad": rating_cf_universidad,
}
