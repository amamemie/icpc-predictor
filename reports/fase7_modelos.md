# Fase 7 — Comparación de modelos y modelo elegido

Fecha: 2026-11-21. Datos: equipos **bolivianos**, sin integrantes (ver la decisión en la sección 14 de
CLAUDE.md). Las tablas completas se regeneran con `python -m models.evaluate`
(`reports/fase6_baseline.md`) y la importancia de features con `python -m models.explicar`
(`reports/fase7_shap.md`).

## Resumen

Spearman entre el orden predicho y el real (1 = perfecto, 0 = azar).

| Modelo | Test 2026 nacional | Test 2026 regional | Backtest nacional | Backtest regional |
|---|---|---|---|---|
| **Ridge (elegido)** | 0.482 | 0.672 | 0.504 | 0.626 |
| LightGBM LambdaRank | 0.462 | 0.662 | 0.492 | 0.583 |
| Ensamble de heurísticas | 0.468 | 0.673 | 0.509 | 0.599 |
| Historial de la universidad | 0.489 | 0.542 | 0.516 | 0.462 |
| Resultado previo del equipo | 0.460 | 0.687 | 0.470 | 0.672 |
| Rating CF de la universidad | 0.453 | 0.509 | 0.444 | 0.430 |
| Elo de la universidad | 0.330 | 0.552 | 0.370 | 0.467 |
| Azar | 0.006 | 0.029 | 0.023 | 0.002 |

Backtest = media de 2023, 2024, 2025 y 2026, entrenando cada año solo con los anteriores.

## ¿Supera al baseline?

El baseline de CLAUDE.md (rating máximo de CF del equipo) no se puede calcular sin integrantes. Contra
los baselines sustitutos:

- **No hay un ganador claro.** Ridge no supera a la mejor heurística de cada tipo: en el nacional
  gana "historial de la universidad" (0.516 vs 0.504) y en la regional "resultado previo del equipo"
  (0.672 vs 0.626). Las diferencias en el nacional están dentro de la variación entre años.
- La información útil está concentrada en 2–3 variables (SHAP: resultado previo del equipo y talento
  CF de la universidad), así que un modelo más flexible no tiene de dónde sacar más.

## Modelo elegido: Ridge

Se elige Ridge aunque no gane en cada tipo por separado, porque:

1. Es el único que queda cerca del mejor **en ambos** tipos (las heurísticas buenas en uno son malas
   en el otro: historial de universidad 0.46 en la regional, equipo previo 0.47 en el nacional).
2. Es explicable: la predicción de cada equipo se descompone en contribuciones por feature, que la
   demo muestra como "por qué".
3. Usará los ratings de los integrantes sin cambiar nada si algún día se cargan.

## Modelo "guardado"

No se guarda un artefacto fijo en `models/artifacts/`: `models/predict.py` reentrena Ridge en cada
predicción con las competencias **anteriores a la fecha** pedida. Así una misma herramienta sirve para
predecir la próxima competencia y para re-jugar las pasadas sin fuga de información, y el modelo se
actualiza solo cuando entran resultados nuevos. Reentrenar tarda menos de un segundo.

## Limitaciones

- Nacional: ~2/3 de los equipos no tienen historial con el mismo nombre; para ellos el modelo solo
  ve a su universidad. Acierta 2 del top 10 real en 2026.
- Pocos años de nacional (2022–2026): las métricas varían ±0.05 entre años.
- Hiperparámetros fijos (sin Optuna): con estos datos el tuning sobreajustaría el backtest.
