"""Elo de universidades a partir de los resultados ICPC (feature "a la fecha").

Cada competencia, en orden cronológico, se trata como un torneo todos-contra-todos entre las
universidades que participaron: cada universidad juega contra cada otra, gana la que tuvo el
mejor equipo (menor percentil). Las actualizaciones se hacen después de procesar la competencia,
así que el Elo que recibe un equipo en la competencia C es el de ANTES de C.

- K se divide por (n_universidades - 1) para que una competencia grande no pese más que una chica.
- Universidad nueva: ELO_INICIAL.
- Competencias de la misma fecha se procesan juntas (ninguna ve el resultado de la otra).
"""

import numpy as np
import pandas as pd

ELO_INICIAL = 1500.0
K = 64.0


def _actualizar(elos: dict[str, float], ranking: pd.Series) -> dict[str, float]:
    """ranking: percentil del mejor equipo por universidad (más bajo = mejor)."""
    unis = list(ranking.index)
    n = len(unis)
    if n < 2:
        return {}
    r = np.array([elos.get(u, ELO_INICIAL) for u in unis])
    p = ranking.to_numpy()
    esperado = 1.0 / (1.0 + 10 ** ((r[None, :] - r[:, None]) / 400.0))  # P(i gana a j)
    real = (p[:, None] < p[None, :]).astype(float) + 0.5 * (p[:, None] == p[None, :])
    np.fill_diagonal(esperado, 0.0)
    np.fill_diagonal(real, 0.0)
    delta = (K / (n - 1)) * (real - esperado).sum(axis=1)
    return {u: r[i] + delta[i] for i, u in enumerate(unis)}


def elo_a_la_fecha(df: pd.DataFrame) -> pd.DataFrame:
    """Devuelve (equipo_id, uni_elo, uni_elo_partidas) con el Elo previo a cada competencia.

    `df` necesita: equipo_id, competencia_id, fecha, uni, pct.
    """
    elos: dict[str, float] = {}
    partidas: dict[str, int] = {}
    filas = []
    for _, mismo_dia in df.groupby("fecha", sort=True):
        for _, e in mismo_dia.iterrows():
            uni = e["uni"]
            sin_uni = not isinstance(uni, str)
            filas.append({
                "equipo_id": e["equipo_id"],
                "uni_elo": None if sin_uni else elos.get(uni, ELO_INICIAL),
                "uni_elo_partidas": None if sin_uni else partidas.get(uni, 0),
            })
        nuevos: dict[str, float] = {}
        # Solo competencias con resultados (una predicción todavía no tiene pct).
        for _, comp in mismo_dia.dropna(subset=["uni", "pct"]).groupby("competencia_id"):
            mejor = comp.groupby("uni")["pct"].min()
            for u, v in _actualizar(elos, mejor).items():
                # Si una universidad juega dos competencias el mismo día, se suman los cambios.
                nuevos[u] = nuevos.get(u, elos.get(u, ELO_INICIAL)) + (v - elos.get(u, ELO_INICIAL))
            for u in mejor.index:
                partidas[u] = partidas.get(u, 0) + 1
        elos.update(nuevos)
    return pd.DataFrame(filas)
