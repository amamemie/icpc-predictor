from matching.personas import normalizar_nombre, obtener_o_crear_persona


def test_normalizar_nombre():
    assert normalizar_nombre("  José  PÉREZ-Quispe ") == "jose perez quispe"
    assert normalizar_nombre("María Ñusta  Mamani") == "maria nusta mamani"
    assert normalizar_nombre("O'Brien, Juan") == "o brien juan"
    assert normalizar_nombre(None) == ""
    assert normalizar_nombre("") == ""


def _n_personas(conn):
    return conn.execute("SELECT COUNT(*) FROM personas").fetchone()[0]


def test_misma_persona_mismo_nombre_y_universidad(conn):
    a = obtener_o_crear_persona(conn, "José Pérez", "UMSS", "BO")
    b = obtener_o_crear_persona(conn, "jose  perez", "umss", "BO")
    assert a == b and _n_personas(conn) == 1


def test_mismo_nombre_otra_universidad_es_otra_persona(conn):
    a = obtener_o_crear_persona(conn, "José Pérez", "UMSS", "BO")
    b = obtener_o_crear_persona(conn, "José Pérez", "UMSA", "BO")
    assert a != b


def test_handle_une_personas_y_completa_nombre(conn):
    a = obtener_o_crear_persona(conn, None, "UMSS", "BO", cf_handle="MickyOr")
    assert conn.execute("SELECT nombre FROM personas WHERE id=?", (a,)).fetchone()[0] == "MickyOr"
    # Otro año aparece con nombre real y el mismo handle (distinta capitalización).
    b = obtener_o_crear_persona(conn, "Miguel Ortiz", "UMSS", "BO", cf_handle="mickyor")
    assert a == b
    nombre, norm = conn.execute(
        "SELECT nombre, nombre_normalizado FROM personas WHERE id=?", (a,)
    ).fetchone()
    assert (nombre, norm) == ("Miguel Ortiz", "miguel ortiz")
    cuentas = conn.execute("SELECT handle, verificado, fuente FROM cuentas").fetchall()
    assert cuentas == [("MickyOr", 1, "manual")]


def test_nombre_existente_recibe_handle(conn):
    a = obtener_o_crear_persona(conn, "Ana Quispe", "UMSA", "BO")
    b = obtener_o_crear_persona(conn, "Ana Quispe", "UMSA", "BO", cf_handle="ana_q")
    assert a == b
    assert conn.execute("SELECT persona_id FROM cuentas").fetchone()[0] == a
