"""Marco de evaluación común: split temporal y métricas de ranking.

Uso: python -m models.evaluate   # evalúa todos los modelos y escribe reports/fase6_baseline.md

Alcance del MVP: se evalúa el orden de los equipos BOLIVIANOS en cada competencia (nacional y
regional; en la regional se re-rankean solo los bolivianos). Target = pct_bo (más bajo = mejor).

- Test principal: entrenar con año ≤ 2025, probar con 2026.
- Backtest: para cada año Y de 2023 a 2026, entrenar con años < Y y probar con Y.

Un modelo es una función (train: DataFrame, test: DataFrame) -> array de puntajes para test,
donde un puntaje MÁS BAJO significa MEJOR posición predicha.
"""

from collections.abc import Callable

import numpy as np
import pandas as pd
from scipy.stats import kendalltau, spearmanr
from sklearn.metrics import ndcg_score

from db.crear import RAIZ
from features.build_dataset import RUTA_DATASET

Modelo = Callable[[pd.DataFrame, pd.DataFrame], np.ndarray]
RUTA_REPORTE = RAIZ / "reports" / "fase6_baseline.md"
AÑO_TEST = 2026
AÑOS_BACKTEST = [2023, 2024, 2025, 2026]


def cargar_dataset() -> pd.DataFrame:
    df = pd.read_parquet(RUTA_DATASET)
    return df[df["pais"] == "BO"].reset_index(drop=True)


def metricas_competencia(real: np.ndarray, puntaje: np.ndarray, k_top: int | None) -> dict:
    """real y puntaje: más bajo = mejor."""
    real, puntaje = np.asarray(real, float), np.asarray(puntaje, float)
    n = len(real)
    rel = (real.max() - real)[None, :]  # relevancia: más alta = mejor
    pred = (-puntaje)[None, :]
    m = {
        "n": n,
        "spearman": spearmanr(real, puntaje).statistic,
        "kendall": kendalltau(real, puntaje).statistic,
        "ndcg@10": ndcg_score(rel, pred, k=10),
    }
    top_real = set(np.argsort(real, kind="stable")[:10])
    top_pred = set(np.argsort(puntaje, kind="stable")[:10])
    m["top10"] = len(top_real & top_pred) / 10
    if k_top:
        k = min(k_top, n)
        m["topk"] = len(set(np.argsort(real)[:k]) & set(np.argsort(puntaje)[:k])) / k
        m["k"] = k
    return m


def k_clasificados(df_completo: pd.DataFrame, slug: str, año: int, tipo: str) -> int | None:
    """Para el nacional: cuántos equipos bolivianos jugaron la regional ese año (≈ clasificados)."""
    if tipo != "nacional":
        return None
    reg = df_completo[(df_completo["tipo"] == "regional") & (df_completo["año"] == año)]
    return len(reg) or None


def evaluar(modelo: Modelo, df: pd.DataFrame, año_test: int) -> list[dict]:
    train = df[df["año"] < año_test]
    test = df[df["año"] == año_test].copy()
    if train.empty or test.empty:
        return []
    test["puntaje"] = modelo(train, test)
    filas = []
    for (slug, tipo), g in test.groupby(["slug", "tipo"]):
        k = k_clasificados(df, slug, año_test, tipo)
        m = metricas_competencia(g["pct_bo"], g["puntaje"], k)
        filas.append({"slug": slug, "tipo": tipo, "año": año_test, **m})
    return filas


def evaluar_todos(modelos: dict[str, Modelo], df: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for nombre, modelo in modelos.items():
        for año in AÑOS_BACKTEST:
            for f in evaluar(modelo, df, año):
                filas.append({"modelo": nombre, **f})
    return pd.DataFrame(filas)


def _tabla_md(df: pd.DataFrame, columnas: list[str]) -> str:
    cab = "| " + " | ".join(columnas) + " |"
    sep = "|" + "|".join("---" for _ in columnas) + "|"
    filas = []
    for _, r in df.iterrows():
        celdas = []
        for c in columnas:
            v = r[c]
            if pd.isna(v):
                celdas.append("–")
            elif isinstance(v, float) and v.is_integer() and c in ("n", "k"):
                celdas.append(str(int(v)))
            elif isinstance(v, float):
                celdas.append(f"{v:.3f}")
            else:
                celdas.append(str(v))
        filas.append("| " + " | ".join(celdas) + " |")
    return "\n".join([cab, sep, *filas])


def reporte(resultados: pd.DataFrame) -> str:
    test = resultados[resultados["año"] == AÑO_TEST]
    partes = [
        "# Fase 6 — Baselines y modelos sin integrantes",
        "",
        "Generado por `python -m models.evaluate`. Orden de los equipos **bolivianos**; "
        "puntaje más bajo = mejor. Spearman/Kendall: correlación entre el orden predicho y "
        "el real (1 = perfecto, 0 = azar). top10: fracción del top 10 real acertada. "
        "topk (nacional): fracción acertada de los k equipos que fueron a la regional.",
        "",
    ]
    for tipo in ("nacional", "regional"):
        t = test[test["tipo"] == tipo].sort_values("spearman", ascending=False)
        cols = ["modelo", "n", "spearman", "kendall", "ndcg@10", "top10"]
        if tipo == "nacional":
            cols += ["k", "topk"]
        partes += [f"## Test {AÑO_TEST} — {tipo}", "", _tabla_md(t, cols), ""]
    bt = (
        resultados.groupby(["modelo", "tipo"])["spearman"]
        .mean()
        .unstack("tipo")
        .sort_values("nacional", ascending=False)
        .reset_index()
    )
    bt.columns.name = None
    partes += [
        "## Backtest 2023–2026 (Spearman medio por tipo)",
        "",
        _tabla_md(bt, ["modelo", "nacional", "regional"]),
        "",
    ]
    por_año = resultados.pivot_table(index="modelo", columns=["tipo", "año"], values="spearman")
    por_año.columns = [f"{t} {a}" for t, a in por_año.columns]
    por_año = por_año.reset_index()
    partes += ["## Spearman por año", "", _tabla_md(por_año, list(por_año.columns)), ""]
    return "\n".join(partes)


def main() -> None:
    from models.baseline import MODELOS_BASE
    from models.modelos import MODELOS_ML

    df = cargar_dataset()
    resultados = evaluar_todos({**MODELOS_BASE, **MODELOS_ML}, df)
    texto = reporte(resultados)
    RUTA_REPORTE.parent.mkdir(parents=True, exist_ok=True)
    RUTA_REPORTE.write_text(texto + "\n", encoding="utf-8")
    print(texto)


if __name__ == "__main__":
    main()
