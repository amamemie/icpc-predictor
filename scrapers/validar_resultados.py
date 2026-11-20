"""Valida los resultados cargados contra el HTML original.

Uso: python -m scrapers.validar_resultados

Para cada competencia comprueba:
- nº de equipos y top 3 (logins) iguales a un conteo independiente sobre el HTML (regex, sin
  reutilizar el parser);
- posiciones 1..n sin huecos;
- orden coherente: resueltos no crecen al bajar y, a igual resueltos, la penalidad no baja;
- suma de celdas resueltas == resueltos de cada equipo;
- solo MOJ: para el regional, nº de equipos == "Teams N" de la página menos los guest, y la
  posición coincide con data-place.
Sale con código 1 si alguna comprobación falla.
"""

import json
import re
import sqlite3
import sys

from db.crear import RUTA_DB, conectar
from scrapers.scorelatam import detectar_formato, leer_competencias, ruta_html, vista_para


def _referencia_boca(html: str, vista: str) -> list[str]:
    """Logins de la vista en orden, por regex sobre el HTML crudo."""
    grupo = None
    for m in re.finditer(r"<a[^>]*toggleGroup\((\d+)\)[^>]*>(.*?)</a>", html, re.S):
        texto = re.sub(r"<[^>]+>", "", m.group(2))
        if texto.strip().strip("().").lower() == vista.lower():
            grupo = m.group(1)
            break
    if grupo is None:
        raise ValueError(f"vista {vista} no encontrada")
    logins = []
    patron = rf'<tr class="sitegroup{grupo}">(.*?)</tr>'
    for fila in re.findall(patron, html, re.S):
        celdas = re.findall(r"<td[^>]*>(.*?)</td>", fila, re.S)
        usuario = re.sub(r"<[^>]+>", "", celdas[1]).strip()
        nombre = re.sub(r"<[^>]+>", "", celdas[2]).strip()
        login = usuario.split("/")[0].strip()
        if "ccl" in login.lower() or nombre.upper().startswith("[CCL]"):
            continue
        logins.append(login)
    return logins


def _referencia_moj(html: str, vista: str) -> list[str]:
    filas = re.findall(r"<tr([^>]*data-login=\"[^\"]*\"[^>]*)>", html)
    logins = []
    filtro = None
    if vista.lower() != "global":
        arbol = json.loads(re.search(r"var RTREE=(\[.*?\]);", html, re.S).group(1))
        filtro = re.compile(next(x["r"] for x in arbol if x["d"] == 0 and x["n"] == vista))
    for atributos in filas:
        if "guest-row" in atributos:
            continue
        login = re.search(r'data-login="([^"]*)"', atributos).group(1)
        if "ccl" in login.lower() or (filtro and not filtro.match(login)):
            continue
        logins.append(login)
    return logins


def validar(conn: sqlite3.Connection, comp: dict) -> list[str]:
    errores = []
    slug, vista = comp["slug"], vista_para(comp["tipo"])
    html = ruta_html(slug).read_text(encoding="utf-8")
    formato = detectar_formato(html)
    filas = conn.execute(
        """
        SELECT e.id, e.login, r.posicion, r.resueltos, r.penalidad,
               (SELECT COALESCE(SUM(resuelto), 0) FROM celdas c WHERE c.equipo_id = e.id)
        FROM competencias co
        JOIN equipos e ON e.competencia_id = co.id
        JOIN resultados r ON r.equipo_id = e.id
        WHERE co.slug = ?
        ORDER BY r.posicion
        """,
        (slug,),
    ).fetchall()
    if not filas:
        return [f"{slug}: no está cargada"]

    ref = _referencia_moj(html, vista) if formato == "moj" else _referencia_boca(html, vista)
    logins = [f[1] for f in filas]
    if len(logins) != len(ref):
        errores.append(f"nº de equipos: base={len(logins)} html={len(ref)}")
    if logins[:3] != ref[:3]:
        errores.append(f"top 3: base={logins[:3]} html={ref[:3]}")
    if logins != ref:
        errores.append("el orden completo de logins no coincide con el HTML")
    if [f[2] for f in filas] != list(range(1, len(filas) + 1)):
        errores.append("posiciones no van de 1 a n")
    for a, b in zip(filas, filas[1:], strict=False):
        if b[3] > a[3] or (b[3] == a[3] and b[4] < a[4]):
            errores.append(f"orden incoherente entre {a[1]} y {b[1]}")
            break
    malas = [f[1] for f in filas if f[5] != f[3]]
    if malas:
        errores.append(f"celdas resueltas != resueltos en {len(malas)} equipos, ej. {malas[:3]}")

    if formato == "moj" and vista.lower() == "global":
        m = re.search(r"Teams\s+(\d+)", re.sub(r"<[^>]+>", " ", html))
        total = int(m.group(1)) if m else None
        guests = html.count('class="guest-row"')
        if total is not None and len(filas) != total - guests:
            errores.append(f"Teams {total} - {guests} guest != {len(filas)}")
        lugares = re.findall(r'data-login="([^"]*)"[^>]*data-place="(\d+)"', html)
        lugares = {login: int(p) for login, p in lugares}
        # MOJ da el mismo data-place a los empatados; nuestra posición (1..n en el orden de la
        # página) debe ser data-place para el primero de cada bloque de empate.
        primera_pos: dict[int, int] = {}
        for f in filas:
            primera_pos.setdefault(lugares[f[1]], f[2])
        distintos = [p for p, pos in primera_pos.items() if p != pos]
        if distintos:
            errores.append(f"data-place no cuadra con la posición en {len(distintos)} bloques")
    return [f"{slug}: {e}" for e in errores]


def main() -> int:
    conn = conectar(RUTA_DB)
    errores_totales = 0
    for comp in leer_competencias():
        if not ruta_html(comp["slug"]).exists():
            print(f"-- {comp['slug']}: sin HTML, se omite")
            continue
        errores = validar(conn, comp)
        errores_totales += len(errores)
        n = conn.execute(
            "SELECT n_equipos FROM competencias WHERE slug = ?", (comp["slug"],)
        ).fetchone()
        estado = "OK " if not errores else "ERR"
        vista = vista_para(comp["tipo"])
        print(f"{estado} {comp['slug']:<12} {vista:<8} equipos={n[0] if n else '-'}")
        for e in errores:
            print(f"     {e}")
    print(f"\n{'Todo OK' if not errores_totales else f'{errores_totales} errores'}")
    return 1 if errores_totales else 0


if __name__ == "__main__":
    sys.exit(main())
