-- Esquema de la base (sección 5 de CLAUDE.md + cf_usuarios).
-- Todas las fechas se guardan como texto ISO 8601 en UTC ("2024-05-01T14:35:00Z").

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS personas (
    id                 INTEGER PRIMARY KEY,
    nombre             TEXT NOT NULL,
    nombre_normalizado TEXT NOT NULL,
    universidad        TEXT,
    pais               TEXT
);

CREATE TABLE IF NOT EXISTS cuentas (
    id          INTEGER PRIMARY KEY,
    persona_id  INTEGER NOT NULL REFERENCES personas(id),
    plataforma  TEXT NOT NULL,              -- codeforces | atcoder | codechef
    handle      TEXT NOT NULL,
    confianza   REAL,
    verificado  INTEGER NOT NULL DEFAULT 0, -- 0/1
    fuente      TEXT,
    UNIQUE (plataforma, handle)
);

CREATE TABLE IF NOT EXISTS competencias (
    id          INTEGER PRIMARY KEY,
    nombre      TEXT NOT NULL,
    tipo        TEXT NOT NULL CHECK (tipo IN ('nacional', 'regional', 'wf')),
    fecha       TEXT,
    n_equipos   INTEGER,
    fuente_url  TEXT
);

CREATE TABLE IF NOT EXISTS equipos (
    id              INTEGER PRIMARY KEY,
    competencia_id  INTEGER NOT NULL REFERENCES competencias(id),
    nombre          TEXT NOT NULL,
    universidad     TEXT
);

CREATE TABLE IF NOT EXISTS integrantes (
    equipo_id   INTEGER NOT NULL REFERENCES equipos(id),
    persona_id  INTEGER NOT NULL REFERENCES personas(id),
    PRIMARY KEY (equipo_id, persona_id)
);

CREATE TABLE IF NOT EXISTS resultados (
    equipo_id   INTEGER PRIMARY KEY REFERENCES equipos(id),
    posicion    INTEGER,
    resueltos   INTEGER,
    penalidad   INTEGER
);

CREATE TABLE IF NOT EXISTS historial_rating (
    plataforma  TEXT NOT NULL,
    handle      TEXT NOT NULL,
    fecha       TEXT NOT NULL,              -- momento de la actualización del rating (UTC)
    rating      INTEGER NOT NULL,           -- rating después del contest
    contest_id  TEXT NOT NULL,
    PRIMARY KEY (plataforma, handle, contest_id)
);
CREATE INDEX IF NOT EXISTS idx_historial_handle_fecha
    ON historial_rating (plataforma, handle, fecha);

-- Usuarios de Codeforces candidatos a ser competidores (antes de vincularlos a una persona).
CREATE TABLE IF NOT EXISTS cf_usuarios (
    handle            TEXT PRIMARY KEY,
    nombre            TEXT,
    apellido          TEXT,
    organizacion      TEXT,
    ciudad            TEXT,
    pais              TEXT,
    rating            INTEGER,
    max_rating        INTEGER,
    fecha_registro    TEXT,
    fecha_descarga    TEXT NOT NULL,
    estado_historial  TEXT NOT NULL DEFAULT 'pendiente'
        CHECK (estado_historial IN ('pendiente', 'ok', 'fallido')),
    error_historial   TEXT
);
