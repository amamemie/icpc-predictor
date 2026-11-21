"""Importancia de features con SHAP (Fase 7).

Uso: python -m models.explicar   # escribe reports/fase7_shap.md

Entrena LightGBM LambdaRank y Ridge con los datos de entrenamiento (año ≤ 2025) y mide, sobre el
test 2026, el |SHAP| medio de cada feature. En Ridge el SHAP de una feature es su coeficiente por
el valor estandarizado (contribución lineal).
"""

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap

from db.crear import RAIZ
from models.evaluate import AÑO_TEST, cargar_dataset
from models.modelos import FEATURES, _etiquetas_relevancia, matriz, preparar_ridge

RUTA = RAIZ / "reports" / "fase7_shap.md"


def shap_lgbm(train: pd.DataFrame, test: pd.DataFrame) -> pd.Series:
    train = train.sort_values("competencia_id")
    grupos = train.groupby("competencia_id", sort=True).size().to_numpy()
    modelo = lgb.LGBMRanker(objective="lambdarank", n_estimators=200, learning_rate=0.05,
                            num_leaves=7, min_child_samples=20, subsample=0.8, subsample_freq=1,
                            colsample_bytree=0.8, random_state=0, verbose=-1)
    modelo.fit(matriz(train), _etiquetas_relevancia(train), group=grupos)
    valores = shap.TreeExplainer(modelo).shap_values(matriz(test))
    return pd.Series(np.abs(valores).mean(axis=0), index=FEATURES)


def shap_ridge(train: pd.DataFrame, test: pd.DataFrame) -> pd.Series:
    modelo, xte = preparar_ridge(train, test)
    escalador, ridge = modelo[0], modelo[-1]
    contrib = escalador.transform(xte) * ridge.coef_
    imp = pd.Series(np.abs(contrib).mean(axis=0), index=xte.columns)
    # Se juntan la feature y su indicador de faltante.
    return imp.groupby(lambda c: c.removesuffix("_falta")).sum().reindex(FEATURES)


def main() -> None:
    df = cargar_dataset()
    train, test = df[df["año"] < AÑO_TEST], df[df["año"] == AÑO_TEST]
    tabla = pd.DataFrame({"lgbm": shap_lgbm(train, test), "ridge": shap_ridge(train, test)})
    tabla = (tabla / tabla.sum()).sort_values("lgbm", ascending=False)  # fracción del total
    lineas = ["# Fase 7 — Importancia de features (SHAP)", "",
              f"Modelos entrenados con año < {AÑO_TEST}; |SHAP| medio sobre el test {AÑO_TEST} "
              "(equipos bolivianos), normalizado a fracción del total por modelo.", "",
              "| feature | LightGBM | Ridge |", "|---|---|---|"]
    for f, r in tabla.iterrows():
        lineas.append(f"| {f} | {r['lgbm']:.1%} | {r['ridge']:.1%} |")
    RUTA.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("\n".join(lineas))


if __name__ == "__main__":
    main()
