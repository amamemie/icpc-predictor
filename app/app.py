"""Demo: ranking predicho de equipos ICPC (Bolivia).

Uso: streamlit run app/app.py

Dos modos:
- Re-jugar una competencia pasada: predice con datos anteriores a su fecha y compara con el real.
- Subir inscritos: CSV con columnas `equipo`, `universidad` (y opcional `pais`).
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.crear import RUTA_DB, conectar  # noqa: E402
from models.predict import guardar, leer_inscritos, predecir  # noqa: E402

st.set_page_config(page_title="ICPC Predictor Bolivia", page_icon="🏆", layout="wide")


@st.cache_data
def competencias() -> pd.DataFrame:
    conn = conectar(RUTA_DB)
    df = pd.read_sql_query(
        "SELECT slug, nombre, tipo, fecha FROM competencias ORDER BY fecha DESC", conn
    )
    conn.close()
    return df


@st.cache_data
def resultados_reales(slug: str) -> pd.DataFrame:
    conn = conectar(RUTA_DB)
    df = pd.read_sql_query(
        """
        SELECT e.nombre AS equipo, COALESCE(e.universidad, '') AS universidad, e.pais,
               r.posicion, r.resueltos
        FROM equipos e JOIN competencias co ON co.id = e.competencia_id
        JOIN resultados r ON r.equipo_id = e.id
        WHERE co.slug = ? AND e.pais = 'BO'
        ORDER BY r.posicion
        """,
        conn,
        params=(slug,),
    )
    conn.close()
    df["posicion_real_bo"] = range(1, len(df) + 1)
    return df


@st.cache_data(show_spinner="Calculando features y entrenando…")
def predecir_cache(inscritos: pd.DataFrame, tipo: str, fecha: date) -> pd.DataFrame:
    conn = conectar(RUTA_DB)
    pred = predecir(conn, inscritos, tipo, fecha)
    conn.close()
    return pred


st.title("🏆 ICPC Predictor — Bolivia")
st.caption(
    "Ranking predicho de equipos bolivianos a partir del historial ICPC de su universidad, "
    "del resultado previo del mismo equipo y del talento en Codeforces de su universidad. "
    "Todavía **no usa los integrantes** de cada equipo. El modelo se entrena solo con "
    "competencias anteriores a la fecha elegida."
)

modo = st.sidebar.radio("Modo", ["Re-jugar competencia pasada", "Subir inscritos (CSV)"])

if modo == "Re-jugar competencia pasada":
    comps = competencias()
    etiqueta = {r.slug: f"{r.nombre} ({r.fecha})" for r in comps.itertuples()}
    slug = st.sidebar.selectbox("Competencia", comps["slug"], format_func=etiqueta.get)
    fila = comps[comps["slug"] == slug].iloc[0]
    real = resultados_reales(slug)
    inscritos = real[["equipo", "universidad", "pais"]]
    try:
        pred = predecir_cache(inscritos, fila["tipo"], date.fromisoformat(fila["fecha"]))
    except ValueError as e:
        st.warning(str(e))
        st.stop()
    tabla = pred.merge(
        real[["equipo", "universidad", "posicion_real_bo", "resueltos"]],
        on=["equipo", "universidad"],
        how="left",
    )
    rho = spearmanr(tabla["posicion_predicha"], tabla["posicion_real_bo"]).statistic
    k = min(10, len(tabla))
    top = len(
        set(tabla.nsmallest(k, "posicion_predicha")["equipo"])
        & set(tabla.nsmallest(k, "posicion_real_bo")["equipo"])
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Equipos bolivianos", len(tabla))
    c2.metric("Spearman (predicho vs real)", f"{rho:.2f}")
    c3.metric(f"Top {k} acertados", f"{top}/{k}")
    st.dataframe(
        tabla[
            [
                "posicion_predicha",
                "posicion_real_bo",
                "equipo",
                "universidad",
                "resueltos",
                "explicacion",
            ]
        ],
        hide_index=True,
        width="stretch",
        column_config={
            "posicion_predicha": st.column_config.NumberColumn("Pred."),
            "posicion_real_bo": st.column_config.NumberColumn("Real"),
            "explicacion": st.column_config.TextColumn("Por qué (↑ ayuda, ↓ perjudica)"),
        },
    )
    st.scatter_chart(tabla, x="posicion_real_bo", y="posicion_predicha", height=320)
else:
    st.sidebar.markdown("CSV con columnas `equipo`, `universidad` y opcional `pais`.")
    archivo = st.sidebar.file_uploader("Inscritos", type="csv")
    tipo = st.sidebar.selectbox("Tipo", ["nacional", "regional"])
    fecha = st.sidebar.date_input("Fecha de la competencia", value=date.today())
    if archivo is None:
        st.info("Sube un CSV de inscritos. Ejemplo: `app/ejemplo_inscritos_nacional_2026.csv`.")
        st.stop()
    try:
        inscritos = leer_inscritos(archivo)
        pred = predecir_cache(inscritos, tipo, fecha)
    except ValueError as e:
        st.error(str(e))
        st.stop()
    st.dataframe(
        pred[["posicion_predicha", "equipo", "universidad", "explicacion"]],
        hide_index=True,
        width="stretch",
    )
    nombre = st.text_input("Nombre para guardar la predicción", value=f"{tipo}-{fecha.year}")
    if st.button("Guardar predicción con fecha"):
        ruta = guardar(pred, fecha, nombre)
        st.success(f"Guardada en {ruta}")
    st.download_button("Descargar CSV", pred.to_csv(index=False), file_name=f"{nombre}.csv")
