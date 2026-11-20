# Fase 6 — Baselines y modelos sin integrantes

Generado por `python -m models.evaluate`. Orden de los equipos **bolivianos**; puntaje más bajo = mejor. Spearman/Kendall: correlación entre el orden predicho y el real (1 = perfecto, 0 = azar). top10: fracción del top 10 real acertada. topk (nacional): fracción acertada de los k equipos que fueron a la regional.

## Test 2026 — nacional

| modelo | n | spearman | kendall | ndcg@10 | top10 | k | topk |
|---|---|---|---|---|---|---|---|
| historial_universidad | 227 | 0.489 | 0.355 | 0.827 | 0.600 | 80 | 0.525 |
| ridge | 227 | 0.466 | 0.338 | 0.843 | 0.300 | 80 | 0.613 |
| equipo_previo | 227 | 0.460 | 0.333 | 0.838 | 0.400 | 80 | 0.525 |
| lgbm_lambdarank | 227 | 0.453 | 0.323 | 0.871 | 0.200 | 80 | 0.525 |
| rating_cf_universidad | 227 | 0.453 | 0.345 | 0.650 | 0.400 | 80 | 0.562 |
| azar | 227 | 0.006 | 0.006 | 0.601 | 0.100 | 80 | 0.388 |

## Test 2026 — regional

| modelo | n | spearman | kendall | ndcg@10 | top10 |
|---|---|---|---|---|---|
| equipo_previo | 80 | 0.687 | 0.524 | 0.976 | 0.800 |
| ridge | 80 | 0.669 | 0.498 | 0.954 | 0.800 |
| lgbm_lambdarank | 80 | 0.660 | 0.505 | 0.980 | 0.900 |
| historial_universidad | 80 | 0.542 | 0.395 | 0.817 | 0.600 |
| rating_cf_universidad | 80 | 0.509 | 0.374 | 0.851 | 0.600 |
| azar | 80 | 0.029 | 0.020 | 0.346 | 0.100 |

## Backtest 2023–2026 (Spearman medio por tipo)

| modelo | nacional | regional |
|---|---|---|
| historial_universidad | 0.516 | 0.462 |
| lgbm_lambdarank | 0.512 | 0.604 |
| ridge | 0.507 | 0.615 |
| equipo_previo | 0.470 | 0.672 |
| rating_cf_universidad | 0.444 | 0.430 |
| azar | 0.023 | 0.002 |

## Spearman por año

| modelo | nacional 2023 | nacional 2024 | nacional 2025 | nacional 2026 | regional 2023 | regional 2024 | regional 2025 | regional 2026 |
|---|---|---|---|---|---|---|---|---|
| azar | 0.005 | 0.053 | 0.028 | 0.006 | -0.116 | 0.087 | 0.008 | 0.029 |
| equipo_previo | 0.511 | 0.455 | 0.453 | 0.460 | 0.644 | 0.734 | 0.621 | 0.687 |
| historial_universidad | 0.567 | 0.508 | 0.501 | 0.489 | 0.266 | 0.487 | 0.554 | 0.542 |
| lgbm_lambdarank | 0.485 | 0.572 | 0.536 | 0.453 | 0.503 | 0.627 | 0.625 | 0.660 |
| rating_cf_universidad | 0.462 | 0.427 | 0.436 | 0.453 | 0.343 | 0.364 | 0.505 | 0.509 |
| ridge | 0.441 | 0.574 | 0.545 | 0.466 | 0.513 | 0.630 | 0.647 | 0.669 |

