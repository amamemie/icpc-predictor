from datetime import date

import pandas as pd

from features.build_dataset import construir_dataset
from models.predict import leer_inscritos, predecir
from scrapers.scorelatam import Equipo, cargar_competencia


def _comp(slug, tipo, año, fecha):
    return {"slug": slug, "nombre": slug, "tipo": tipo, "año": str(año), "fecha": fecha,
            "formato": "boca", "url_scoreboard": "u"}


def _poblar(conn):
    for año, fecha in [(2023, "2023-09-01"), (2024, "2024-08-30")]:
        equipos = [
            Equipo(1, f"a{año}", "BO", "UMSS", "Fuertes", 8, 800),
            Equipo(2, f"b{año}", "BO", "UMSA", "Medios", 5, 500),
            Equipo(3, f"c{año}", "BO", "UCB", "Flojos", 2, 200),
            Equipo(4, f"d{año}", "BO", "UPDS", "Nuevos", 0, 0),
        ]
        cargar_competencia(conn, _comp(f"subbr-{año}", "nacional", año, fecha), equipos)


def test_leer_inscritos_pais_por_defecto(tmp_path):
    ruta = tmp_path / "i.csv"
    ruta.write_text("equipo,universidad,integrante1\nFuertes,UMSS,x\nOtros,,y\n", encoding="utf-8")
    df = leer_inscritos(ruta)
    assert list(df.columns) == ["equipo", "universidad", "pais"]
    assert df["pais"].tolist() == ["BO", "BO"]


def test_predecir_usa_historial_y_no_entrena_con_el_futuro(conn):
    _poblar(conn)
    dataset = construir_dataset(conn)
    inscritos = pd.DataFrame({
        "equipo": ["Flojos", "Fuertes", "Medios", "Desconocido"],
        "universidad": ["UCB", "UMSS", "UMSA", "UNIVALLE"],
        "pais": ["BO"] * 4,
    })
    pred = predecir(conn, inscritos, "nacional", date(2025, 9, 1), dataset=dataset)
    orden = pred.sort_values("posicion_predicha")["equipo"].tolist()
    assert orden.index("Fuertes") < orden.index("Medios") < orden.index("Flojos")
    assert pred["explicacion"].str.len().gt(0).all()
    # Con fecha anterior a todo el historial no hay con qué entrenar.
    try:
        predecir(conn, inscritos, "nacional", date(2023, 1, 1), dataset=dataset)
    except ValueError as e:
        assert "No hay competencias" in str(e)
    else:
        raise AssertionError("debió fallar sin datos de entrenamiento")
