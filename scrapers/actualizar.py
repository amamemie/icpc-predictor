"""Actualiza los ratings de Codeforces y regenera el dataset (Fases 8 y 9).

Uso:
    python -m scrapers.actualizar                  # todo: candidatos, historiales y dataset
    python -m scrapers.actualizar --sin-candidatos # no vuelve a bajar user.ratedList (~47 MB)
    python -m scrapers.actualizar --limite 5       # prueba con pocos handles

Pensado para correr antes de cada competencia o semanalmente con cron, por ejemplo:
    0 6 * * 1  cd /ruta/icpc_proyect && .venv/bin/python -m scrapers.actualizar >> act.log 2>&1

Cada refresco guarda una versión nueva con fecha en data/raw/codeforces/ (nunca sobrescribe), así
que el historial de descargas queda auditable. Con ~370 candidatos tarda ~13 min (1 petición / 2 s).
"""

import argparse
import logging

from db.crear import RUTA_DB, crear_db
from features import build_dataset
from scrapers.codeforces import PLATAFORMA, descargar_candidatos, descargar_historiales
from scrapers.http import ClienteHTTP

log = logging.getLogger(__name__)


def resumen(conn) -> dict[str, int]:
    def uno(sql):
        return conn.execute(sql).fetchone()[0]

    return {
        "candidatos": uno("SELECT COUNT(*) FROM cf_usuarios"),
        "registros_rating": uno("SELECT COUNT(*) FROM historial_rating"),
        "ultimo_contest": uno("SELECT MAX(fecha) FROM historial_rating"),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--pais", default="Bolivia")
    parser.add_argument("--sin-candidatos", action="store_true")
    parser.add_argument("--limite", type=int, help="solo los primeros N handles (prueba)")
    parser.add_argument("--sin-dataset", action="store_true")
    args = parser.parse_args()

    conn = crear_db(RUTA_DB)
    antes = resumen(conn)
    with ClienteHTTP(PLATAFORMA) as cliente:
        if not args.sin_candidatos:
            n = descargar_candidatos(cliente, conn, args.pais, refrescar=True)
            log.info("Candidatos de %s: %d", args.pais, n)
        conteo = descargar_historiales(cliente, conn, limite=args.limite, refrescar=True)
        log.info("Historiales: %s", conteo)
    despues = resumen(conn)
    log.info("Antes: %s", antes)
    log.info("Después: %s", despues)
    conn.close()
    if not args.sin_dataset:
        build_dataset.main()


if __name__ == "__main__":
    main()
