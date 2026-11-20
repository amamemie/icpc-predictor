"""Integrantes de los equipos: plantilla manual, carga y reporte de cobertura.

Uso:
    python -m matching.integrantes plantilla [--nacional]   # agrega equipos faltantes al CSV
    python -m matching.integrantes cargar                   # CSV -> personas/integrantes/cuentas
    python -m matching.integrantes cobertura                # % de equipos con integrantes

La plantilla (data/manual/integrantes.csv) tiene 4 filas por equipo: 3 concursantes y 1 coach.
Se llena a mano con `nombre` y/o `cf_handle`. Nunca se reescribe: `plantilla` solo agrega al
final los equipos que todavía no están.
"""

import argparse
import csv
import sqlite3
from pathlib import Path

from db.crear import RAIZ, RUTA_DB, crear_db
from matching.personas import obtener_o_crear_persona

RUTA_PLANTILLA = RAIZ / "data" / "manual" / "integrantes.csv"
COLUMNAS = [
    "slug",
    "año",
    "login",
    "posicion",
    "universidad",
    "equipo",
    "rol",
    "orden",
    "nombre",
    "cf_handle",
    "fuente",
    "notas",
]
ROLES = [("concursante", "1"), ("concursante", "2"), ("concursante", "3"), ("coach", "1")]


def equipos_bolivianos(conn: sqlite3.Connection, incluir_nacional: bool) -> list[tuple]:
    """Equipos con país BO: los de la regional (prioridad 1) y opcionalmente los del nacional."""
    tipos = ("regional", "nacional") if incluir_nacional else ("regional",)
    marcas = ",".join("?" * len(tipos))
    return conn.execute(
        f"""
        SELECT co.slug, co.año, e.login, r.posicion, e.universidad, e.nombre
        FROM equipos e
        JOIN competencias co ON co.id = e.competencia_id
        JOIN resultados r ON r.equipo_id = e.id
        WHERE e.pais = 'BO' AND co.tipo IN ({marcas})
        ORDER BY co.tipo DESC, co.año, r.posicion
        """,
        tipos,
    ).fetchall()


def leer_plantilla(ruta: Path = RUTA_PLANTILLA) -> list[dict]:
    if not ruta.exists():
        return []
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def generar_plantilla(
    conn: sqlite3.Connection, ruta: Path = RUTA_PLANTILLA, incluir_nacional: bool = False
) -> int:
    """Agrega al CSV los equipos que faltan (sin tocar las filas existentes). Devuelve cuántos."""
    presentes = {(f["slug"], f["login"]) for f in leer_plantilla(ruta)}
    equipos = equipos_bolivianos(conn, incluir_nacional)
    nuevos = [e for e in equipos if (e[0], e[2]) not in presentes]
    if not nuevos:
        return 0
    escribir_cabecera = not ruta.exists()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        if escribir_cabecera:
            w.writerow(COLUMNAS)
        for slug, año, login, posicion, universidad, equipo in nuevos:
            for rol, orden in ROLES:
                w.writerow(
                    [
                        slug,
                        año,
                        login,
                        posicion,
                        universidad or "",
                        equipo,
                        rol,
                        orden,
                        "",
                        "",
                        "",
                        "",
                    ]
                )
    return len(nuevos)


def cargar_integrantes(conn: sqlite3.Connection, filas: list[dict]) -> dict[str, int]:
    """Carga las filas con nombre o handle.

    Los integrantes de todo equipo que aparece en el CSV se reemplazan por lo que dice el CSV
    (si se borra un nombre del CSV, desaparece de la base al recargar).
    """
    conteo = {"filas": 0, "filas_sin_equipo": 0}
    equipos_tocados: dict[tuple, int] = {}
    pendientes = []
    for f in filas:
        nombre, handle = (f.get("nombre") or "").strip(), (f.get("cf_handle") or "").strip()
        clave = (f["slug"], f["login"])
        if clave not in equipos_tocados:
            fila = conn.execute(
                "SELECT e.id FROM equipos e JOIN competencias co ON co.id = e.competencia_id"
                " WHERE co.slug = ? AND e.login = ?",
                clave,
            ).fetchone()
            if fila is None:
                conteo["filas_sin_equipo"] += 1
                continue
            equipos_tocados[clave] = fila[0]
        if nombre or handle:
            pendientes.append((equipos_tocados[clave], f, nombre, handle))

    for equipo_id in equipos_tocados.values():
        conn.execute("DELETE FROM integrantes WHERE equipo_id = ?", (equipo_id,))
    for equipo_id, f, nombre, handle in pendientes:
        pais = conn.execute("SELECT pais FROM equipos WHERE id = ?", (equipo_id,)).fetchone()[0]
        fuente = (f.get("fuente") or "").strip() or "manual"
        persona_id = obtener_o_crear_persona(
            conn, nombre, f.get("universidad") or None, pais, handle or None, fuente
        )
        conn.execute(
            "INSERT OR IGNORE INTO integrantes (equipo_id, persona_id, rol, fuente)"
            " VALUES (?, ?, ?, ?)",
            (equipo_id, persona_id, f.get("rol") or "concursante", fuente),
        )
        conteo["filas"] += 1
    conn.commit()
    return conteo


def cobertura(conn: sqlite3.Connection) -> list[dict]:
    """Por competencia: equipos bolivianos y cuántos tienen 3, 1–2 o 0 concursantes conocidos."""
    filas = conn.execute(
        """
        SELECT co.slug, co.tipo,
               (SELECT COUNT(*) FROM integrantes i
                WHERE i.equipo_id = e.id AND i.rol = 'concursante') AS n,
               (SELECT COUNT(*) FROM integrantes i
                WHERE i.equipo_id = e.id AND i.rol = 'coach') AS coach
        FROM equipos e JOIN competencias co ON co.id = e.competencia_id
        WHERE e.pais = 'BO'
        """
    ).fetchall()
    por_comp: dict[str, dict] = {}
    for slug, tipo, n, coach in filas:
        c = por_comp.setdefault(
            slug,
            {
                "slug": slug,
                "tipo": tipo,
                "equipos": 0,
                "completos": 0,
                "parciales": 0,
                "con_coach": 0,
            },
        )
        c["equipos"] += 1
        c["completos"] += n >= 3
        c["parciales"] += 0 < n < 3
        c["con_coach"] += coach > 0
    return sorted(por_comp.values(), key=lambda c: (c["tipo"] != "regional", c["slug"]))


def imprimir_cobertura(conn: sqlite3.Connection) -> None:
    print(
        f"{'competencia':<12} {'tipo':<9} {'equipos':>7} {'3 integ.':>8} {'1-2':>5} "
        f"{'coach':>6} {'% completos':>11}"
    )
    totales: dict[str, list[int]] = {}
    for c in cobertura(conn):
        pct = 100 * c["completos"] / c["equipos"]
        print(
            f"{c['slug']:<12} {c['tipo']:<9} {c['equipos']:>7} {c['completos']:>8} "
            f"{c['parciales']:>5} {c['con_coach']:>6} {pct:>10.1f}%"
        )
        t = totales.setdefault(c["tipo"], [0, 0])
        t[0] += c["equipos"]
        t[1] += c["completos"]
    for tipo, (n, completos) in totales.items():
        print(f"TOTAL {tipo}: {completos}/{n} equipos completos ({100 * completos / n:.1f} %)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("plantilla")
    p.add_argument("--nacional", action="store_true", help="incluir equipos del nacional")
    sub.add_parser("cargar")
    sub.add_parser("cobertura")
    args = parser.parse_args()

    conn = crear_db(RUTA_DB)
    if args.comando == "plantilla":
        n = generar_plantilla(conn, incluir_nacional=args.nacional)
        print(f"Equipos agregados a {RUTA_PLANTILLA.relative_to(RAIZ)}: {n}")
    elif args.comando == "cargar":
        print(cargar_integrantes(conn, leer_plantilla()))
        imprimir_cobertura(conn)
    else:
        imprimir_cobertura(conn)
    conn.close()


if __name__ == "__main__":
    main()
