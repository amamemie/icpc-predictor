"""Descarga, parseo y carga de scoreboards de scorelatam (BOCA hasta 2025, MOJ en 2026).

Uso:
    python -m scrapers.scorelatam descargar     # baja los HTML que falten
    python -m scrapers.scorelatam cargar        # parsea y carga en la base

Detalles del formato en la sección 14 de CLAUDE.md.
"""

import argparse
import csv
import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

from db.crear import RAIZ, RUTA_DB, crear_db
from scrapers.http import ClienteHTTP

DIR_HTML = RAIZ / "data" / "raw" / "scorelatam"
RUTA_COMPETENCIAS = RAIZ / "data" / "manual" / "competencias.csv"

log = logging.getLogger(__name__)

RE_CELDA = re.compile(r"(\d+)\s*/\s*(\d+|-)")
RE_TOTAL = re.compile(r"(\d+)\s*\((\d+)\)")
RE_UNIVERSIDAD = re.compile(r"^\[([^\]]*)\]\s*(.*)$", re.S)


@dataclass
class Celda:
    problema: str
    intentos: int
    minuto: int | None

    @property
    def resuelto(self) -> bool:
        return self.minuto is not None


@dataclass
class Equipo:
    posicion: int
    login: str
    pais: str | None
    universidad: str | None
    nombre: str
    resueltos: int
    penalidad: int
    celdas: list[Celda] = field(default_factory=list)


# --- Utilidades comunes -----------------------------------------------------------------------


def parsear_celda(problema: str, texto: str) -> Celda | None:
    """'2/58' -> 2 intentos, resuelto en el min 58; '3/-' -> 3 intentos sin resolver."""
    m = RE_CELDA.search(texto)
    if not m:
        return None
    minuto = None if m.group(2) == "-" else int(m.group(2))
    return Celda(problema, int(m.group(1)), minuto)


def separar_universidad(texto: str) -> tuple[str | None, str]:
    """'[UMSS] Wasos del valle' -> ('UMSS', 'Wasos del valle'). '[]' -> universidad None."""
    texto = " ".join(texto.split())
    m = RE_UNIVERSIDAD.match(texto)
    if not m:
        return None, texto
    return (m.group(1).strip() or None), m.group(2).strip()


def es_ccl(login: str, nombre_completo: str) -> bool:
    return "ccl" in login.lower() or nombre_completo.strip().upper().startswith("[CCL]")


def _normalizar_vista(texto: str) -> str:
    return texto.strip().strip("().").lower()


def detectar_formato(html: str) -> str:
    return "moj" if "var RTREE=" in html or 'class="score m-icpc"' in html else "boca"


# --- BOCA -------------------------------------------------------------------------------------


def vistas_boca(soup: BeautifulSoup) -> list[tuple[str, int]]:
    """Lista (texto del enlace, N) de los enlaces toggleGroup(N), en orden."""
    vistas = []
    for a in soup.find_all("a"):
        m = re.search(r"toggleGroup\((\d+)\)", a.get("onclick") or a.get("href") or "")
        if m:
            vistas.append((a.get_text(strip=True), int(m.group(1))))
    return vistas


def grupo_de_vista(soup: BeautifulSoup, vista: str) -> int:
    buscada = vista.lower()
    for texto, n in vistas_boca(soup):
        if _normalizar_vista(texto) == buscada:
            return n
    raise ValueError(f"No existe la vista {vista!r}")


# Códigos de bandera de BOCA que no son ISO 3166-1 alfa-2.
CODIGOS_BOCA = {"UR": "UY"}


def pais_boca(td: Tag, sufijo: str) -> str | None:
    """País del equipo: la bandera (<img alt="bo">) y, si no hay, el sufijo del login.

    El sufijo no es fiable: en latam-2020 es la subregión (SO, NO, CB, CA) y en 2019 algunos
    equipos llevan el país de su sede.
    """
    img = td.find("img")
    codigo = (img.get("alt") if img else "") or sufijo
    codigo = codigo.strip().upper()
    return CODIGOS_BOCA.get(codigo, codigo) or None


def _texto_antes_de_br(td: Tag) -> str:
    partes = []
    for nodo in td.children:
        if isinstance(nodo, Tag) and nodo.name == "br":
            break
        partes.append(str(nodo) if isinstance(nodo, NavigableString) else nodo.get_text(" "))
    return " ".join(" ".join(partes).split())


def parsear_boca(html: str, vista: str) -> list[Equipo]:
    soup = BeautifulSoup(html, "lxml")
    tabla = soup.find("table", id="myscoretable")
    if tabla is None:
        raise ValueError("No se encontró table#myscoretable")
    grupo = f"sitegroup{grupo_de_vista(soup, vista)}"
    filas = tabla.find_all("tr")
    cabecera = [c.get_text(strip=True) for c in filas[0].find_all(["td", "th"])]
    problemas = cabecera[3:-1]  # '#', 'User/Site', 'Name', A..., 'Total'

    equipos = []
    for tr in filas[1:]:
        if grupo not in (tr.get("class") or []):
            continue
        tds = tr.find_all("td")
        if len(tds) != len(cabecera):
            raise ValueError(f"Fila con {len(tds)} celdas, se esperaban {len(cabecera)}")
        usuario = tds[1].get_text(" ", strip=True)
        login, _, sufijo = usuario.partition("/")
        pais = pais_boca(tds[1], sufijo)
        nombre_completo = _texto_antes_de_br(tds[2])
        if es_ccl(login, nombre_completo):
            continue
        universidad, nombre = separar_universidad(nombre_completo)
        total = RE_TOTAL.search(tds[-1].get_text(" ", strip=True))
        if total is None:
            raise ValueError(f"Total ilegible para {login}")
        celdas = [
            c
            for problema, td in zip(problemas, tds[3:-1], strict=True)
            if (c := parsear_celda(problema, td.get_text(" ", strip=True)))
        ]
        equipos.append(
            Equipo(
                posicion=int(tds[0].get_text(strip=True)),
                login=login.strip(),
                pais=pais,
                universidad=universidad,
                nombre=nombre,
                resueltos=int(total.group(1)),
                penalidad=int(total.group(2)),
                celdas=celdas,
            )
        )
    return equipos


# --- MOJ --------------------------------------------------------------------------------------


def arbol_vistas_moj(html: str) -> list[dict]:
    m = re.search(r"var RTREE=(\[.*?\]);", html, re.S)
    return json.loads(m.group(1)) if m else []


def _nombre_moj(td: Tag) -> str:
    """Texto propio de la celda, sin las insignias (<span> de clasificado, guest, etc.)."""
    texto = "".join(str(n) for n in td.children if isinstance(n, NavigableString))
    return " ".join(texto.split())


def parsear_moj(html: str, vista: str) -> list[Equipo]:
    soup = BeautifulSoup(html, "lxml")
    tabla = soup.find("table", class_="score")
    if tabla is None:
        raise ValueError("No se encontró table.score")
    cabecera = tabla.find("tr")
    problemas = [th.get_text(strip=True) for th in cabecera.find_all("th", class_="prob")]

    filtro = None
    if vista.lower() != "global":
        arbol = arbol_vistas_moj(html)
        nodos = [x for x in arbol if x["d"] == 0 and x["n"].lower() == vista.lower()]
        if not nodos:
            raise ValueError(f"No existe la vista {vista!r} de nivel 0")
        filtro = re.compile(nodos[0]["r"])

    equipos = []
    for tr in tabla.find_all("tr", attrs={"data-login": True}):
        login = tr["data-login"]
        td_equipo = tr.find("td", class_="team")
        nombre_completo = _nombre_moj(td_equipo)
        if "guest-row" in (tr.get("class") or []) or es_ccl(login, nombre_completo):
            continue
        if filtro is not None and not filtro.match(login):
            continue
        celdas_td = [
            td
            for td in tr.find_all("td", class_="cell")
            if not {"tot", "pen"} & set(td.get("class", []))
        ]
        celdas = []
        for problema, td in zip(problemas, celdas_td, strict=True):
            pv = td.find("span", class_="pv")
            if pv and (c := parsear_celda(problema, pv.get_text(" ", strip=True))):
                celdas.append(c)
        resueltos, penalidad, _ = tr["data-tie"].split("|")
        universidad, nombre = separar_universidad(nombre_completo)
        equipos.append(
            Equipo(
                posicion=0,  # se recalcula abajo
                login=login,
                pais=(tr.get("data-country") or "").upper() or None,
                universidad=tr.get("data-univ") or universidad,
                nombre=nombre,
                resueltos=int(resueltos),
                penalidad=int(penalidad),
                celdas=celdas,
            )
        )
    # data-place es la posición en la tabla completa; dentro de la vista se numera 1..n en el
    # orden de la página, igual que BOCA.
    for i, e in enumerate(equipos, 1):
        e.posicion = i
    return equipos


def parsear(html: str, vista: str) -> list[Equipo]:
    if detectar_formato(html) == "moj":
        return parsear_moj(html, vista)
    return parsear_boca(html, vista)


# --- Competencias y carga ---------------------------------------------------------------------


def slug_de_url(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def vista_para(tipo: str) -> str:
    """Regional: ranking completo (Global). Nacional: vista Bolivia de la Primera Fase."""
    return "Bolivia" if tipo == "nacional" else "Global"


def leer_competencias(ruta: Path = RUTA_COMPETENCIAS) -> list[dict]:
    with open(ruta, encoding="utf-8", newline="") as f:
        filas = [f for f in csv.DictReader(f) if "scorelatam" in (f.get("url_scoreboard") or "")]
    for f in filas:
        f["slug"] = slug_de_url(f["url_scoreboard"])
    return filas


def ruta_html(slug: str) -> Path:
    return DIR_HTML / f"{slug}.html"


def descargar_todo(competencias: list[dict]) -> None:
    with ClienteHTTP("scorelatam") as cliente:
        for c in competencias:
            destino = ruta_html(c["slug"])
            ya_estaba = destino.exists()
            cliente.descargar_archivo(c["url_scoreboard"], destino)
            log.info("%s: %s", c["slug"], "ya estaba" if ya_estaba else "descargado")


def cargar_competencia(conn: sqlite3.Connection, comp: dict, equipos: list[Equipo]) -> int:
    """Reemplaza la competencia (por slug) y sus equipos, resultados y celdas."""
    viejo = conn.execute("SELECT id FROM competencias WHERE slug = ?", (comp["slug"],)).fetchone()
    if viejo:
        ids = "SELECT id FROM equipos WHERE competencia_id = ?"
        conn.execute(f"DELETE FROM celdas WHERE equipo_id IN ({ids})", viejo)
        conn.execute(f"DELETE FROM resultados WHERE equipo_id IN ({ids})", viejo)
        conn.execute(f"DELETE FROM integrantes WHERE equipo_id IN ({ids})", viejo)
        conn.execute("DELETE FROM equipos WHERE competencia_id = ?", viejo)
        conn.execute("DELETE FROM competencias WHERE id = ?", viejo)

    cur = conn.execute(
        "INSERT INTO competencias (slug, nombre, tipo, año, fecha, n_equipos, formato, fuente_url)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            comp["slug"],
            comp["nombre"],
            comp["tipo"],
            int(comp["año"]) if comp["año"] else None,
            comp["fecha"] or None,
            len(equipos),
            comp["formato"] or None,
            comp["url_scoreboard"],
        ),
    )
    comp_id = cur.lastrowid
    for e in equipos:
        eq_id = conn.execute(
            "INSERT INTO equipos (competencia_id, login, nombre, universidad, pais)"
            " VALUES (?, ?, ?, ?, ?)",
            (comp_id, e.login, e.nombre, e.universidad, e.pais),
        ).lastrowid
        conn.execute(
            "INSERT INTO resultados (equipo_id, posicion, resueltos, penalidad)"
            " VALUES (?, ?, ?, ?)",
            (eq_id, e.posicion, e.resueltos, e.penalidad),
        )
        conn.executemany(
            "INSERT INTO celdas (equipo_id, problema, intentos, minuto, resuelto)"
            " VALUES (?, ?, ?, ?, ?)",
            [(eq_id, c.problema, c.intentos, c.minuto, int(c.resuelto)) for c in e.celdas],
        )
    conn.commit()
    return comp_id


def cargar_todo(conn: sqlite3.Connection, competencias: list[dict]) -> None:
    for c in competencias:
        ruta = ruta_html(c["slug"])
        if not ruta.exists():
            log.warning("%s: falta el HTML, correr 'descargar' primero", c["slug"])
            continue
        equipos = parsear(ruta.read_text(encoding="utf-8"), vista_para(c["tipo"]))
        cargar_competencia(conn, c, equipos)
        log.info("%s (%s): %d equipos", c["slug"], vista_para(c["tipo"]), len(equipos))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("comando", choices=["descargar", "cargar"])
    args = parser.parse_args()
    competencias = leer_competencias()
    if args.comando == "descargar":
        descargar_todo(competencias)
    else:
        conn = crear_db(RUTA_DB)
        cargar_todo(conn, competencias)
        conn.close()


if __name__ == "__main__":
    main()
