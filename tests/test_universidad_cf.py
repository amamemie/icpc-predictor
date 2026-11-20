from datetime import date

import pandas as pd

from features.universidad_cf import features_cf_universidad, universidad_de_organizacion


def test_universidad_de_organizacion():
    assert universidad_de_organizacion("Universidad Mayor de San Andrés") == "UMSA"
    assert universidad_de_organizacion("Universidad mayor de San Simon") == "UMSS"
    assert universidad_de_organizacion("UMSS.") == "UMSS"
    assert universidad_de_organizacion("Universidad Privada Boliviana (UPB)") == "UPB"
    assert universidad_de_organizacion("Facultad Nacional de Ingeniería") == "UTO"
    assert universidad_de_organizacion("UPDS Tarija") == "UPDS"
    assert universidad_de_organizacion("Pollos Primo") is None
    assert universidad_de_organizacion(None) is None
    assert universidad_de_organizacion(float("nan")) is None


def test_features_cf_universidad_a_la_fecha():
    hist = pd.DataFrame(
        {
            "handle": ["a", "a", "b", "c", "d"],
            "uni": ["UMSS"] * 4 + ["UMSA"],
            "fecha": pd.to_datetime(
                ["2024-01-10", "2025-06-01", "2025-03-01", "2022-01-01", "2025-05-01"], utc=True
            ),
            "rating": [1500, 1700, 1400, 2400, 2000],
        }
    )
    f = features_cf_universidad(hist, "UMSS", date(2025, 9, 1))
    # 'c' lleva más de 24 meses inactivo; 'a' vale 1700 a la fecha.
    assert f == {
        "uni_cf_usuarios_12m": 2,
        "uni_cf_max_rating": 1700.0,
        "uni_cf_top3_rating": 1550.0,
    }
    # Antes del 2025-06-01, 'a' aún valía 1500 (estrictamente anterior).
    f = features_cf_universidad(hist, "UMSS", date(2025, 6, 1))
    assert f["uni_cf_max_rating"] == 1500.0
    assert features_cf_universidad(hist, "UATF", date(2025, 9, 1))["uni_cf_usuarios_12m"] == 0
