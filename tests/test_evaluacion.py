import numpy as np
import pandas as pd
import pytest

from features.build_dataset import posicion_con_empates
from models.evaluate import evaluar, metricas_competencia


def test_posicion_con_empates_promedia_bloques():
    g = pd.DataFrame(
        {
            "posicion": [1, 2, 3, 4, 5],
            "resueltos": [5, 3, 3, 0, 0],
            "penalidad": [500, 300, 300, 0, 0],
        }
    )
    assert posicion_con_empates(g).tolist() == [1.0, 2.5, 2.5, 4.5, 4.5]


def test_posicion_con_empates_misma_cantidad_distinta_penalidad():
    g = pd.DataFrame({"posicion": [1, 2], "resueltos": [3, 3], "penalidad": [100, 200]})
    assert posicion_con_empates(g).tolist() == [1.0, 2.0]


def test_metricas_orden_perfecto_e_invertido():
    real = np.arange(1, 21) / 20
    m = metricas_competencia(real, real, k_top=5)
    assert m["spearman"] == pytest.approx(1.0)
    assert m["ndcg@10"] == pytest.approx(1.0)
    assert m["top10"] == 1.0 and m["topk"] == 1.0
    inv = metricas_competencia(real, -real, k_top=5)
    assert inv["spearman"] == pytest.approx(-1.0)
    assert inv["top10"] == 0.0


def test_evaluar_usa_split_temporal():
    df = pd.DataFrame(
        {
            "año": [2024, 2024, 2025, 2025, 2025],
            "slug": ["a", "a", "b", "b", "b"],
            "tipo": ["regional"] * 5,
            "pct_bo": [0.5, 1.0, 1 / 3, 2 / 3, 1.0],
        }
    )
    vistos = {}

    def modelo(train, test):
        vistos["train"] = sorted(train["año"].unique())
        vistos["test"] = sorted(test["año"].unique())
        return test["pct_bo"].to_numpy()

    filas = evaluar(modelo, df, 2025)
    assert vistos == {"train": [2024], "test": [2025]}
    assert filas[0]["spearman"] == pytest.approx(1.0)
