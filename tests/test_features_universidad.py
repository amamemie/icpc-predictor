from datetime import date

import pandas as pd
import pytest

from features.universidad import construir_features, normalizar_universidad
from matching.personas import normalizar_nombre


def test_normalizar_universidad():
    assert normalizar_universidad("UCB-Cochabamba") == "UCB"
    assert normalizar_universidad("UCB - Tarija") == "UCB"
    assert normalizar_universidad("UPB - Cbba") == "UPB"
    assert normalizar_universidad("UPBLP") == "UPB"
    assert normalizar_universidad("UV-La Paz") == "UNIVALLE"
    assert normalizar_universidad("Univalle Scz") == "UNIVALLE"
    assert normalizar_universidad("UNSXX- II") == "UNSXX"
    assert normalizar_universidad("Universidad Tecnica de Oruro - Ingenieria") == "UTO"
    assert normalizar_universidad(None) is None
    assert normalizar_universidad(float("nan")) is None
    assert normalizar_universidad("  ") is None


def _df(filas):
    """filas: (equipo_id, comp_id, tipo, fecha, n_equipos, universidad, nombre, posicion)."""
    df = pd.DataFrame(
        filas,
        columns=[
            "equipo_id",
            "competencia_id",
            "tipo",
            "fecha",
            "n_equipos",
            "universidad",
            "nombre",
            "posicion",
        ],
    )
    df["pct"] = df["posicion"] / df["n_equipos"]
    df["uni"] = df["universidad"].map(normalizar_universidad)
    df["nombre_norm"] = df["nombre"].map(normalizar_nombre)
    return df


FILAS = [
    # nacional 2024 (4 equipos)
    (1, 10, "nacional", date(2024, 8, 30), 4, "UMSS", "Wasos", 1),
    (2, 10, "nacional", date(2024, 8, 30), 4, "UMSA", "Duck", 2),
    (3, 10, "nacional", date(2024, 8, 30), 4, "UMSS", "Otro", 3),
    (4, 10, "nacional", date(2024, 8, 30), 4, None, "Sin uni", 4),
    # regional 2024 (10 equipos, 2 bolivianos)
    (5, 20, "regional", date(2024, 11, 7), 10, "UMSS", "Wasos", 5),
    (6, 20, "regional", date(2024, 11, 7), 10, "UMSA", "Duck", 8),
    # nacional 2025
    (7, 30, "nacional", date(2025, 9, 12), 2, "UCB-Cochabamba", "Nuevos", 1),
    (8, 30, "nacional", date(2025, 9, 12), 2, "UMSS", "wasos", 2),
]


def _por_equipo(feats):
    return feats.set_index("equipo_id")


def test_primera_competencia_sin_historial():
    f = _por_equipo(construir_features(_df(FILAS)))
    assert f.loc[1, "uni_comps_previas_nacional"] == 0
    assert pd.isna(f.loc[1, "uni_mejor_pct_ultima_nacional"])
    assert f.loc[1, "eq_apariciones_previas"] == 0
    assert f.loc[1, "uni_equipos_en_comp"] == 2  # dos equipos de UMSS en el nacional 2024
    assert pd.isna(f.loc[4, "uni_equipos_en_comp"])  # sin universidad


def test_regional_usa_el_nacional_previo():
    f = _por_equipo(construir_features(_df(FILAS)))
    assert f.loc[5, "uni_comps_previas_nacional"] == 1
    assert f.loc[5, "uni_mejor_pct_ultima_nacional"] == pytest.approx(0.25)  # UMSS 1.º de 4
    assert f.loc[5, "uni_media_pct_3a_nacional"] == pytest.approx((0.25 + 0.75) / 2)
    assert f.loc[5, "eq_pct_previo"] == pytest.approx(0.25)  # "Wasos" en el nacional
    assert f.loc[5, "eq_tipo_previo"] == "nacional"
    assert f.loc[5, "uni_comps_previas_regional"] == 0


def test_mismo_equipo_con_nombre_en_otra_capitalizacion():
    f = _por_equipo(construir_features(_df(FILAS)))
    assert f.loc[8, "eq_apariciones_previas"] == 2  # nacional y regional 2024
    assert f.loc[8, "eq_tipo_previo"] == "regional"
    assert f.loc[8, "eq_pct_previo"] == pytest.approx(0.5)
    # UCB sin historial previo.
    assert f.loc[7, "uni_comps_previas_nacional"] == 0


def test_sin_fuga_de_informacion():
    """Cambiar resultados futuros no altera las features de competencias anteriores."""
    base = construir_features(_df(FILAS)).set_index("equipo_id")
    alterado = [list(f) for f in FILAS]
    for f in alterado:
        if f[1] == 30:  # nacional 2025 (la última)
            f[7] = 3 - f[7]
    alterado[4][7] = 1  # regional 2024: Wasos pasa a 1.º
    nuevo = construir_features(_df([tuple(f) for f in alterado])).set_index("equipo_id")
    previas = [1, 2, 3, 4]  # nacional 2024: anterior a todo lo alterado
    pd.testing.assert_frame_equal(base.loc[previas], nuevo.loc[previas])
    regional = [5, 6]  # regional 2024: solo se alteró su propio resultado, no su historial
    pd.testing.assert_frame_equal(base.loc[regional], nuevo.loc[regional])


def test_elo_a_la_fecha_ganador_sube_y_sin_fuga():
    from features.elo import ELO_INICIAL, elo_a_la_fecha

    df = _df(FILAS)
    elo = elo_a_la_fecha(df).set_index("equipo_id")
    # Primera competencia: todos con Elo inicial.
    assert elo.loc[1, "uni_elo"] == ELO_INICIAL and elo.loc[2, "uni_elo"] == ELO_INICIAL
    # En la regional 2024, UMSS (ganó el nacional) ya está por encima de UMSA.
    assert elo.loc[5, "uni_elo"] > elo.loc[6, "uni_elo"]
    assert elo.loc[5, "uni_elo_partidas"] == 1
    assert pd.isna(elo.loc[4, "uni_elo"])  # sin universidad
