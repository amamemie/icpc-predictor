# ICPC Predictor

Proyecto personal de machine learning para **predecir el ranking de equipos en la próxima competencia oficial ICPC** (nacional/regional), usando los ratings de los integrantes en Codeforces, AtCoder y CodeChef y sus resultados en competencias ICPC anteriores.

Idioma del proyecto: español (código y nombres de variables pueden ir en inglés).

---

## 1. Planteamiento del problema

- En ICPC compiten **equipos de 3**, así que la unidad de predicción es el **equipo**, no la persona.
- **Entrada:** los 3 integrantes de cada equipo inscrito.
- **Salida:** ranking predicho de equipos.
- Target sugerido: **percentil** = posición / n_equipos (permite comparar competencias de distinto tamaño). Alternativas: posición, problemas resueltos.
- Es un problema de **learning to rank**.

## 2. Alcance

**MVP (hacer primero):**
- ICPC Bolivia (nacional) + regional Latinoamérica.
- Últimos 3–5 años.
- **Solo Codeforces** como fuente de rating.
- Emparejamiento persona→handle semimanual.
- Baseline + un modelo simple, evaluado temporalmente.

**Después:** AtCoder, CodeChef, matching más automático, más países, demo pública.

> Regla: no ampliar el alcance hasta que el MVP funcione de punta a punta.

## 3. Fuentes de datos

| Necesito | Fuente | Notas |
|---|---|---|
| Resultados de competencias | Scoreboards de icpc.global, del regional (muchos en BOCA), del nacional; cphof.org | cphof guarda resultados de finales mundiales y algunos regionales con integrantes |
| Integrantes de equipos | Páginas de equipo en icpc.global, cphof.org, contests en Codeforces/Gym con equipos registrados, publicaciones de universidades/clubes, preguntar a coaches | Si el contest se jugó con handles (Codeforces/Gym), ya no hay que resolver identidad |
| Handles | CF API `user.ratedList?includeRetired=true` (filtrar por país/organización), `user.info` (nombre si es público); afiliación en perfil de AtCoder; institución en perfil de CodeChef; clist.by; formulario público de registro | |
| Historial de rating | **Codeforces:** API oficial `user.rating`. **AtCoder:** sin API oficial; `https://atcoder.jp/users/<handle>/history/json`. AtCoder Problems (kenkoooo) es alternativa pero tuvo periodos sin actualizarse. **CodeChef:** sin API pública estable → scraping de `codechef.com/users/<handle>` | |

### Fuente principal de resultados: scorelatam (BOCA)

`https://scorelatam.naquadah.com.br/` es un índice de scoreboards BOCA históricos. Competencias disponibles (slug → URL `https://scorelatam.naquadah.com.br/<slug>/`):

| Competencia | Slugs |
|---|---|
| Regional ICPC Latinoamérica | `latam-2019` … `latam-2026` (la de 2020 se jugó remota en 2021) |
| Programadores de América (PdA) | `pda24`, `pda25`, `pda26` (año a 2 dígitos) |
| Primera fase Brasil (**= nacional de Bolivia desde 2022**) | `subbr-2020` … `subbr-2026` (+ `subbr-2022-extravitoria`) |
| Torneo Chileno de Programación | `subch-2024` … `subch-2026` |
| Fase Zero Maratona SBC | `fzero-2025` |

**Ojo: 2026 usa otro sistema (MOJ), no BOCA** — ver sección 14. Formato BOCA observado en `latam-2025` (válido para 2019–2025, verificar en cada año):
- HTML de BOCA (sin JSON visible). Pestañas SCORE, RUNS, TASKS, CLARIFICATIONS, STATISTICS y "Final Scoreboard".
- Columnas: `#`, `User/Site Name`, problemas `A`…`L`, `Total`.
- Celda de problema: `intentos/minuto` (ej. `2/58` = resuelto en el min 58 al 2º intento; `3/-` = 3 intentos sin resolver). Los problemas no intentados son un `<td>` vacío (verificado en 2019 y 2025: todas las filas tienen el mismo nº de celdas) → **alinear por índice de `<td>`, no por orden de texto**.
- Total: `resueltos (penalidad)`.
- Nombre de equipo: `login/PAÍS [Universidad] Nombre del equipo`, ej. `teamsobo078/BO`, `[UMSS]`, `Wasos del valle`. Algunos traen la etiqueta "Qualified for Programadores de America".
- Hay varias vistas (Global, Global+CCL, Female_Teams, Brasil, Caribbean, CentroAmerica, Mexico, North, **South** —incluye Bolivia, Argentina, Chile, Perú— y CCL). **El mismo equipo aparece repetido en varias vistas → parsear solo la vista Global y deduplicar por login.** Ojo: la columna `#` se recalcula en cada vista (ej. Wasos del valle es 23 en Global y 31 en Global+CCL), así que la posición se toma de la vista Global.
- **No lista integrantes** → los integrantes siguen siendo un problema de la Fase 3.
- Los equipos marcados como CCL (ej. `cclbrbr005`) parecen ser una categoría aparte; decidir si incluirlos o excluirlos del ranking (anotar en la sección 14).
- El login (`teamsobo078`) es un buen identificador de equipo dentro de una competencia, pero **no** entre años.
- **Nacional de Bolivia:** Bolivia juega la Primera Fase de Brasil (mismo contest). En `subbr-*` el ranking nacional es la vista "Bolivia" (su `#` ya es la posición nacional). Cubre 2022 en adelante; en `subbr-2020` y `subbr-2021` no hay equipos bolivianos → los nacionales 2019–2021 siguen sin fuente.

### Reglas al descargar
- Respetar límites: Codeforces ~1 petición cada 2 s; AtCoder y CodeChef aún más espaciado (≥ 2–10 s).
- **Cachear siempre la respuesta cruda** en `data/raw/` (JSON/HTML con fecha) y no volver a pedir lo ya descargado.
- Reintentos con backoff (`tenacity`).
- Respetar términos de uso de cada sitio.

## 4. Resolución de identidad (persona ↔ handle)

Es el problema más difícil del proyecto. Separar siempre **persona** de **cuenta**.

1. **Generar candidatos**
   - CF `user.ratedList` filtrado por país (ej. Bolivia) → pocos miles de candidatos.
   - Mismo string de handle probado en las otras plataformas.
   - clist.by para cuentas ya vinculadas.
2. **Puntuar cada par (persona, handle)**
   - Similitud de nombre normalizado (sin tildes, minúsculas, apellidos invertidos, un solo apellido) con `rapidfuzz`.
   - Coincidencia de organización/universidad.
   - Coincidencia de país.
   - Coherencia temporal (handle activo en los años en que la persona compitió).
   - Parecido del handle con el nombre (`jperez`, `juanp`).
3. **Decidir**
   - Puntaje alto → aceptar automáticamente (`verificado=false`, `confianza` alta).
   - Puntaje medio → revisión manual en una mini app Streamlit (sí/no).
   - Sin candidato → persona sin handle (es información útil: cold start).
4. **Atajo:** formulario público para que los competidores registren sus handles.

## 5. Modelo de datos (SQLite)

```
personas         (id, nombre, nombre_normalizado, universidad, pais)
cuentas          (id, persona_id, plataforma, handle, confianza, verificado, fuente)
competencias     (id, nombre, tipo[nacional|regional|wf], fecha, n_equipos, fuente_url)
equipos          (id, competencia_id, nombre, universidad)
integrantes      (equipo_id, persona_id)
resultados       (equipo_id, posicion, resueltos, penalidad)
historial_rating (plataforma, handle, fecha, rating, contest_id)
```

## 6. Estructura del repositorio

```
icpc-predictor/
├── CLAUDE.md
├── pyproject.toml
├── data/
│   ├── raw/            # respuestas crudas cacheadas (no editar a mano)
│   ├── manual/         # CSVs curados a mano (integrantes, identidades verificadas)
│   └── db.sqlite
├── scrapers/           # codeforces.py, atcoder.py, codechef.py, icpc.py
├── matching/           # candidatos.py, scoring.py, revision_app.py
├── features/           # build_features.py
├── models/             # baseline.py, lgbm_rank.py, evaluate.py
├── app/                # demo Streamlit
└── notebooks/
```

Pipeline por etapas, cada una independiente y re-ejecutable:

```
descargar → parsear → resolver identidades → features → entrenar → evaluar → predecir
```

## 7. Features

**Regla crítica: todas las features se calculan con datos ANTERIORES a la fecha de la competencia** (rating "a la fecha" desde `historial_rating`). Nada de usar el rating actual para competencias pasadas.

Por persona:
- Rating a la fecha y rating máximo a la fecha (CF; luego AtCoder, CodeChef).
- Tendencia: pendiente del rating en los últimos 6–12 meses.
- Nº de contests jugados, días desde el último contest.
- Años en ICPC, mejores posiciones previas.
- Flag `sin_rating` para cold start.

Por equipo (agregando 3 integrantes):
- Máximo, promedio, mínimo, desviación de rating.
- Si el equipo ya compitió junto antes.
- Historial de la universidad en esa competencia.

Normalización: ratings de distintas plataformas no son comparables → percentiles dentro de cada plataforma; considerar normalizar por año (inflación/deflación de rating en CF).

## 8. Modelos

1. **Baseline:** ordenar por rating máximo (o promedio) de CF del equipo. Todo modelo debe superarlo.
2. Regresión lineal/ridge sobre el percentil.
3. **LightGBM con `LambdaRank`** (grupo = competencia).
4. Extra: TrueSkill / Bradley-Terry.

Pocos datos (cientos–miles de filas) → no usar deep learning.

## 9. Evaluación

- **Split temporal:** entrenar con ≤ 2025 y probar con 2026 (el nacional y la regional de 2026 ya se jugaron). Nunca split aleatorio.
- Métricas: Spearman, Kendall tau, NDCG@10, acierto top-k (quién clasifica).
- Interpretabilidad con SHAP.

## 10. Stack

Python · httpx/requests · BeautifulSoup · Playwright (solo si hace falta JS) · tenacity · SQLite · pandas/polars · rapidfuzz · unidecode · scikit-learn · lightgbm · optuna · shap · Streamlit · Jupyter · cron/GitHub Actions para actualizar ratings.

## 11. Fases del proyecto

> **Fase actual: FASE 2** (actualizar esta línea al cerrar cada fase).
>
> Reglas: no empezar una fase sin cumplir el "Listo cuando" de la anterior (salvo donde se indique que pueden ir en paralelo). Al cerrar una fase, marcar sus casillas y anotar decisiones/aprendizajes en la sección 14.

### FASE 0 — Preparación y definición del alcance
**Objetivo:** tener el entorno listo y saber exactamente qué datos se van a recolectar.
- [x] Crear repo con la estructura de la sección 6, `git init`, `.gitignore` (excluir `data/db.sqlite` y `data/raw/` si pesan mucho).
- [x] `pyproject.toml` con dependencias base, entorno virtual, `pytest` y `ruff` configurados.
- [x] Decidir competencias objetivo (ej. nacional Bolivia + regional Latinoamérica) y años (3–5).
- [x] Inventario manual de fuentes: `data/manual/competencias.csv` con `nombre, tipo, año, fecha, url_scoreboard, url_equipos, formato (html/pdf/boca/cf_gym)`. *(Regional 2019–2026 cargado; fila del nacional de Bolivia vacía, sin fuente aún.)*
- [x] Verificar a mano 1–2 URLs de cada fuente para saber si se puede scrapear o habrá que cargar CSV a mano.

**Entregable:** repo funcionando + `competencias.csv`.
**Listo cuando:** `pytest` corre (aunque sin tests reales) y cada competencia objetivo tiene al menos una URL de resultados identificada.

### FASE 1 — Base de datos y datos de Codeforces
**Objetivo:** tener ratings históricos de los competidores de la región.
- [x] Esquema SQLite de la sección 5 (`db/schema.sql` + script de creación). *(+ tabla `cf_usuarios` para candidatos sin persona, con `estado_historial` pendiente/ok/fallido para reanudar.)*
- [x] Cliente HTTP común: caché en `data/raw/`, rate limit configurable por plataforma, reintentos con backoff.
- [x] `scrapers/codeforces.py`: `user.ratedList?includeRetired=true` → filtrar por país (Bolivia) y guardar candidatos (handle, nombre si público, organización, país).
- [x] `user.rating` para cada candidato → `historial_rating`.
- [x] Tests de parseo con respuestas guardadas (sin red).

**Entregable:** `db.sqlite` con usuarios CF de Bolivia y su historial.
**Listo cuando:** se puede consultar "rating de handle X en la fecha D" con una función `rating_a_la_fecha(plataforma, handle, fecha)` probada con tests.

### FASE 2 — Resultados de competencias ICPC
**Objetivo:** tener posiciones históricas de cada equipo. *(Puede ir en paralelo con la Fase 1.)*
- [ ] `scrapers/scorelatam.py`: parser BOCA para `latam-2019` … `latam-2026` (vista Global) y `subbr-2022` … `subbr-2026` (vista Bolivia = nacional), ver sección 3; vista elegida por `toggleGroup(N)`, deduplicado por login, extracción de país, universidad, nombre de equipo, resueltos, penalidad y celdas por problema. Guardar el HTML crudo en `data/raw/scorelatam/<slug>.html`.
- [ ] Parser para otras fuentes (nacional de Bolivia, icpc.global, CF Gym, etc.); si una fuente no se puede parsear, CSV manual en `data/manual/resultados/`.
- [ ] Cargar `competencias`, `equipos` y `resultados` (posición, resueltos, penalidad, universidad).
- [ ] Script de validación: nº de equipos y top 3 coinciden con la fuente.

**Entregable:** todas las competencias de `competencias.csv` cargadas.
**Listo cuando:** la validación pasa para el 100 % de las competencias objetivo.

### FASE 3 — Integrantes de los equipos
**Objetivo:** saber qué personas formaban cada equipo.
- [ ] Extraer integrantes de páginas de equipo (icpc.global), cphof.org, contests jugados con handles (CF/Gym).
- [ ] Completar faltantes con fuentes locales (universidades, clubes, coaches) en `data/manual/integrantes.csv`.
- [ ] Crear `personas` con `nombre_normalizado` (unidecode, minúsculas, sin dobles espacios) y deduplicar personas que aparecen en varios años.
- [ ] Tests de normalización de nombres.

**Entregable:** tabla `integrantes` poblada.
**Listo cuando:** ≥ 80 % de los equipos tienen sus 3 integrantes identificados (registrar el % real).

### FASE 4 — Resolución de identidad (persona → handle)
**Objetivo:** vincular cada persona con sus cuentas.
- [ ] `matching/candidatos.py`: candidatos desde los usuarios CF de la Fase 1 (+ mismo handle en otras plataformas, clist.by).
- [ ] `matching/scoring.py`: puntaje por nombre (rapidfuzz), universidad, país, coherencia temporal, parecido handle-nombre.
- [ ] Umbrales: aceptar automático / revisión manual / sin handle.
- [ ] `matching/revision_app.py` (Streamlit) para confirmar o rechazar pares dudosos; guardar decisiones en `data/manual/identidades.csv`.
- [ ] (Opcional) formulario público para que los competidores registren sus handles.
- [ ] Revisar a mano una muestra aleatoria de 50 vínculos automáticos.

**Entregable:** tabla `cuentas` poblada.
**Listo cuando:** precisión ≥ 95 % en la muestra revisada y se reporta el % de personas con handle CF.

### FASE 5 — Features y dataset de entrenamiento
**Objetivo:** una tabla lista para ML, sin fuga de información.
- [ ] `features/build_features.py`: features por persona y por equipo de la sección 7, **calculadas a la fecha de cada competencia**.
- [ ] Manejo de cold start (`sin_rating`, valores por defecto).
- [ ] Target: percentil = posición / n_equipos.
- [ ] Test anti-fuga: ninguna feature usa datos con fecha ≥ fecha de la competencia.
- [ ] Notebook de exploración (distribuciones, correlación rating vs posición).

**Entregable:** `data/dataset.parquet` (una fila por equipo-competencia).
**Listo cuando:** el test anti-fuga pasa y el dataset se regenera con un solo comando.

### FASE 6 — Baseline y marco de evaluación
**Objetivo:** saber qué tan bien se puede predecir sin ML.
- [ ] `models/evaluate.py`: split temporal (train ≤ 2025, test 2026), métricas Spearman, Kendall tau, NDCG@10, acierto top-k.
- [ ] `models/baseline.py`: ranking por rating máximo CF del equipo (y variante por promedio).
- [ ] Reporte de resultados en `reports/fase6_baseline.md`.

**Entregable:** métricas del baseline.
**Listo cuando:** existe un comando único que evalúa cualquier modelo con el mismo split y métricas.

### FASE 7 — Modelos de ML
**Objetivo:** superar al baseline.
- [ ] Ridge sobre el percentil.
- [ ] LightGBM `LambdaRank` (grupo = competencia); tuning con Optuna usando validación temporal (sin tocar el test).
- [ ] (Opcional) TrueSkill / Bradley-Terry.
- [ ] SHAP para entender qué features pesan.
- [ ] Reporte comparativo en `reports/fase7_modelos.md`.

**Entregable:** modelo final guardado (`models/artifacts/`).
**Listo cuando:** el mejor modelo supera al baseline en el test temporal, o se documenta por qué no y se elige el baseline.

### FASE 8 — Predicción de la próxima competencia y demo
**Objetivo:** usar el sistema de verdad. *(Al 2026-11-20 la única competencia de 2026 que falta es Programadores de América `pda26`; las siguientes del alcance del MVP son el nacional y la regional de 2027.)*
- [ ] Script `predict.py` que recibe la lista de equipos inscritos (CSV: equipo, universidad, integrantes/handles) y devuelve el ranking predicho.
- [ ] Actualizar ratings justo antes de la competencia.
- [ ] Demo Streamlit (`app/`): cargar equipos, ver ranking predicho y explicación por equipo.
- [ ] Guardar la predicción con fecha para compararla después.

**Entregable:** predicción publicada antes de la competencia.
**Listo cuando:** existe la predicción guardada y, tras la competencia, un reporte predicción vs resultado real.

### FASE 9 — Expansión (opcional, iterativa)
- [ ] Agregar AtCoder (`history/json`) y CodeChef (scraping) como features.
- [ ] Más países/regionales.
- [ ] Automatizar actualización de ratings (cron / GitHub Actions).
- [ ] Reentrenar con cada nueva competencia y seguir midiendo.

## 12. Limitaciones conocidas

- Competidores nuevos sin rating (cold start).
- El rating no captura química de equipo, estrategia, nervios ni el set de problemas.
- Identidades mal resueltas contaminan todo → priorizar calidad sobre cantidad en el matching.
- Datos escasos → resultados con alta varianza; reportar incertidumbre.

## 13. Convenciones para Claude

- Antes de escribir un scraper nuevo, revisar que exista caché y rate limit.
- No borrar ni sobrescribir `data/raw/` ni `data/manual/`.
- Toda feature nueva debe respetar la regla "a la fecha" (sin fuga de información).
- Agregar tests pequeños para parsers y para la normalización de nombres.
- Trabajar **solo en la fase actual** (sección 11); si una tarea pertenece a otra fase, avisar antes de hacerla.
- Al terminar una tarea, marcar su casilla `[x]` en la sección 11.

## 14. Registro de decisiones

(Anotar aquí decisiones y aprendizajes: fecha — fase — decisión/hallazgo.)

- 2026-11-20 — Fase 0 — Alcance inicial: ICPC Bolivia + regional Latinoamérica, solo Codeforces en el MVP.
- 2026-11-20 — Fase 0 — Fuente encontrada: scorelatam.naquadah.com.br (BOCA, LATAM 2019–2026, PdA, Brasil, Chile). Cubre resultados del regional; no trae integrantes. Pendiente: fuente del nacional de Bolivia y de integrantes.
- 2026-11-20 — Fase 0 — Entorno: `python -m venv .venv` + `pip install -e ".[dev]"` (no hay `uv` instalado). `pytest` y `ruff` configurados en `pyproject.toml`.
- 2026-11-20 — Fase 0 — Competencias objetivo: regional Latinoamérica 2019–2026 (scorelatam) + nacional de Bolivia (sin fuente todavía). `latam-2020` se registra con año 2020 aunque se jugó en 2021. Fechas exactas pendientes: el HTML de scorelatam no trae la fecha del contest.
- 2026-11-20 — Fase 0 — Formato scorelatam, comparando `latam-2019` y `latam-2025`:
  - Ambos: BOCA, página "Final Scoreboard" con **una sola tabla** `table#myscoretable` que contiene todas las vistas a la vez. Cada `<tr>` tiene clase `sitegroupN`, y el enlace de la vista en "Available scores" llama a `toggleGroup(N)`. En latam la vista Global es `sitegroup1` (2019: 343 equipos; 2025: 558), pero en `subbr` no (ver la entrada siguiente).
  - Columnas iguales: `#`, `User/Site` (login/PAÍS, con `<img alt="bo">`), `Name` (`[Universidad] Nombre`), problemas, `Total` = `resueltos (penalidad)`. Cambia el nº de problemas: 2019 A–M (13), 2025 A–L (12) → leer la cabecera, no fijar el número.
  - Todas las filas tienen todas las celdas; sin empates en `#` y sin logins repetidos dentro de la vista Global.
  - Nombre: en 2025 puede traer texto extra tras un `<br>` (44 equipos, ej. "🎖️ Qualified for Programadores de America in Chile"); quedarse con el texto antes del `<br>`. Hay emojis y texto libre dentro del propio nombre. La universidad puede venir vacía (`[]`).
  - **El prefijo del login cambia entre años para el mismo país** (Bolivia: `teamsobv` en 2019, `teamsobo` en 2025) y no siempre coincide con el país (`teamsoar` agrupa más equipos que `/AR`). Usar el sufijo `/PAÍS` como país, nunca el prefijo.
  - Vistas: 2019 tiene 22 con slugs cortos (`global`, `sobv`, `south`, `cclglobal`…); 2025 tiene 34 con nombres largos (`Global`, `Global+CCL`, `Female_Teams`, `Bolivia`…). Mapear vista → grupo leyendo el número de `toggleGroup(N)` del enlace, nunca por posición ni asumiendo `sitegroup1`.
  - CCL: en ningún año aparece en la vista Global (cero logins `ccl*`); van solo en `Global+CCL`/`cclglobal`. Decisión: excluirlos (no son equipos ICPC del regional).
  - Bolivia en la vista Global: 26 equipos en 2019 y 76 en 2025.
  - Equipos con 0 resueltos sí aparecen (28 en 2019, 9 en 2025) → incluirlos en `n_equipos`.
  - La cabecera de 2025 enlaza a Score/Runs/Tasks/Clarifications/Statistics y a los PDF del problem set; 2019 solo a Statistics/Clarifications/Run List.
- 2026-11-20 — Fase 0 — **Nacional de Bolivia = Primera Fase de Brasil** (`subbr-*`), confirmado por el usuario y verificado descargando `subbr-2020` a `subbr-2025`:
  - Equipos bolivianos por año: 2020 = 0, 2021 = 0, 2022 = 100, 2023 = 153, 2024 = 189, 2025 = 197 (vista "Bolivia", sin CCL). Los nacionales 2019–2021 necesitan otra fuente; en `competencias.csv` solo se cargan 2022–2026.
  - La vista "Bolivia" recalcula `#` de 1 a n → es directamente la posición nacional. Tiene subvistas por ciudad (`Cochabamba`, `La_Paz`, `Santa_Cruz`…) y existe aparte una vista `Bolivia-CCL`.
  - **El número de grupo de cada vista no es su posición en la lista**: los enlaces anidados saltan números (`subbr-2025`: Bolivia = `sitegroup67`, Global = `sitegroup164`; `subbr-2024`: Bolivia = 64, Global = 163). `subbr-2023` ni siquiera tiene vista Global. Buscar la vista por el texto del enlace (`Bolivia`, `Bolivia(`) y tomar el N de `toggleGroup(N)`.
  - Nombres de vista con paréntesis (`Bolivia(`, `Tupiza)`) porque el HTML anida la lista de subvistas.
  - Logins CCL con prefijo variable: `cclsobo…` (2024), `teamcclsobo…` (2025). Para detectar CCL usar "contiene `ccl`", no "empieza con `ccl`".
  - Prefijos de login bolivianos por año distintos (`teamsobolp`, `teamsoboch`, `teamsobo…23014` en 2023) → no sirven como identificador entre años.
  - Nº de problemas por año: 2020 = 15, 2021 = 14, 2022 = 14, 2023 = 13, 2024 = 12, 2025 = 13.
- 2026-11-20 — Fase 0 — **`latam-2026` y `subbr-2026` no son BOCA sino reportes MOJ** → necesitan un parser distinto:
  - Fechas visibles en la página: `latam-2026` el 2026-11-07 (563 equipos), `subbr-2026` el 2026-08-29 (2009 filas). Cargadas en `competencias.csv` con `formato=moj`.
  - Una sola tabla `table.score`; cada `<tr>` trae atributos `data-login`, `data-country`, `data-cname`, `data-univ` (sigla), `data-ufull` (nombre completo de la universidad), `data-region` (ciudad/sede), `data-place`, `data-tie` (`resueltos|penalidad|último minuto`). Mucho más fácil que BOCA: no hay que parsear el texto del nombre para sacar país o universidad.
  - `data-place` es la posición **en la tabla completa**; las vistas se filtran en el navegador con regex sobre el login (`var RTREE=[{n, d, r}]`, `d` = profundidad). La posición nacional de Bolivia hay que **recalcularla** filtrando la vista `Bolivia` de nivel 0 (en 2026: 227 equipos, `teambo…`; ojo, también hay vistas `Bolivia` anidadas bajo "Times femininos").
  - CCL: fila `guest-row`, `data-place` vacío, `#` = `–`, nombre con "guest". Login `ccl…` (en `subbr-2026` la vista `CCL Bolivia` usa `cclbo…`, 11 equipos).
  - `qual-row` marca a los clasificados. Celdas: `intentos/minuto` en `span.pv`, `★` = primer equipo en resolver, `data-sec` = segundo exacto de la aceptación.
  - Hay vista de scoreboard congelado (`score-frozen.html`) aparte.
  - Bolivia en `latam-2026`: 80 equipos.

- 2026-11-20 — Fase 0 — **Fase 0 cerrada.** `pytest` corre y todas las competencias objetivo tienen URL de resultados: regional 2019–2026 y nacional de Bolivia 2022–2026 (8 + 5 filas en `competencias.csv`; formato `boca` hasta 2025 y `moj` en 2026). Pendiente sin bloquear: fuente para los nacionales 2019–2021 y fechas exactas de 2019–2025.
- 2026-11-20 — Fase 0 — Calendario: de 2026 ya se jugaron el nacional de Bolivia (Primera Fase, 2026-08-29) y la regional (2026-11-07); solo falta Programadores de América (`pda26`). Por eso el test temporal pasa a ser 2026 (train ≤ 2025). `pda26` no está en el alcance del MVP; queda como candidata a primera predicción real si se agrega antes de jugarse.
- 2026-11-20 — Fase 1 — Datos de Codeforces descargados (`python -m scrapers.codeforces candidatos` y `historiales`):
  - `user.ratedList?includeRetired=true` devuelve 995.511 usuarios (≈47 MB comprimido en caché). **Solo 366 tienen `country = Bolivia`**; 152 sin organización. Buscar por universidad boliviana en otros países solo suma ~10 cuentas, casi todas falsos positivos (EMI, USB son siglas ambiguas) → no se agregan.
  - `user.rating` de los 366: 0 fallos, 9.300 cambios de rating (2010-03 a 2026-11). El último rating del historial coincide con el de `ratedList` en el 100 % de los casos.
  - Bolivianos con al menos un contest en el año: 2019 = 76, 2020 = 73, 2021 = 58, 2022 = 60, 2023 = 103, 2024 = 113, 2025 = 113, 2026 = 88. Frente a ~600 competidores por nacional, **el cold start será la norma**: pesarán más las features de universidad e historial ICPC, y en la Fase 4 habrá que buscar cuentas por nombre/handle (`user.info`), no solo por país.
  - Fechas del historial = `ratingUpdateTimeSeconds` (cuando CF aplica el rating, minutos u horas después del contest), en UTC. `rating_a_la_fecha` con una `date` corta a las 00:00 UTC; Bolivia es UTC−4.
- 2026-11-20 — Fase 1 — **Fase 1 cerrada.** `rating_a_la_fecha` probada con tests y con datos reales de los 366 candidatos bolivianos.
