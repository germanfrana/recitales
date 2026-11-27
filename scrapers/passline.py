"""Passline (www.passline.com).

La home (home.passline.com/home) arma la cartelera con la API pública
api.passline.com/v1/event/GetBillboardByFilters (POST JSON). Con
country="argentina" y limit="desde,cantidad" se pagina toda la cartelera del
país (~2.300 eventos en 5 páginas de 500). El filtro por categoría de la API
no es estricto, así que se trae todo y se filtra acá.
"""
import html
from datetime import date

from scrapers import base

PORTAL = "Passline"

API = "https://api.passline.com/v1/event/GetBillboardByFilters"
PAGINA = 500

# upper_category_id de Passline: 17 = Música, 26 = Festivales
CATEGORIAS_MUSICA = {"17", "26"}
# Eventos sin categoría superior: se aceptan solo con estas subcategorías.
SUBCATEGORIAS_SUELTAS = {"show", "live music", "electronic music",
                         "electronic dance music", "electro house",
                         "musica & concerti"}
# Subcategorías que son fiesta de boliche, infantil o teatro aunque cuelguen de Música.
SUBCATEGORIAS_EXCLUIDAS = {"fiesta", "club & discoteche", "discoteca", "cachengue",
                           "baile", "evento infantil", "evento familiar",
                           "evento infantil educativo", "educational childrens event",
                           "comedy musical", "experiencia inmersiva",
                           "musical theatre", "stand-up comedy"}
# Regiones de Passline -> provincia
REGIONES = {"capital federal": "Buenos Aires", "buenos aires": "Buenos Aires",
            "cordoba": "Córdoba", "santa fe": "Santa Fe"}


def _pagina(desde):
    r = base.sesion.post(API, json={"country": "argentina", "offset": "1",
                                    "limit": f"{desde},{PAGINA}"}, timeout=60)
    r.raise_for_status()
    d = r.json()
    if not isinstance(d, list):
        if desde == 0:
            raise RuntimeError(f"Passline respondió {str(d)[:200]}")
        return []
    return d


def _es_musica(x):
    sup = x.get("upper_category_id") or ""
    sub = base.sin_acentos(html.unescape(x.get("category_name") or "")).strip()
    titulo = base.sin_acentos(x.get("nombre"))
    # Traslados en micro a un recital ("TRASLADO ... DESDE LA PLATA @ ...")
    if titulo.startswith("traslado") or " desde " in titulo and "@" in titulo:
        return False
    if "egresados" in titulo:  # fiestas de egresados en boliches
        return False
    if sub in SUBCATEGORIAS_EXCLUIDAS:
        return False
    if sup in CATEGORIAS_MUSICA:
        return True
    return sup == "" and sub in SUBCATEGORIAS_SUELTAS


def obtener():
    todos, desde = [], 0
    while desde < 20 * PAGINA:  # tope de seguridad
        lote = _pagina(desde)
        if not lote:
            break
        todos += lote
        desde += PAGINA

    hoy = date.today().isoformat()
    vistos, salida = set(), []
    for x in todos:
        if x.get("id") in vistos or x.get("streaming") == "1":
            continue
        vistos.add(x.get("id"))
        if not _es_musica(x):
            continue
        region = html.unescape(x.get("nombre_region") or "")
        provincia = REGIONES.get(base.sin_acentos(region).strip())
        if not provincia:
            continue
        fin = x.get("fecha_termino") or x.get("fecha_inicio")
        if fin and fin < hoy:
            continue
        fecha = x.get("fecha_inicio")
        hora = (x.get("hora_inicio") or "")[:5]
        if fecha and fecha < hoy:
            fecha, hora = hoy, ""  # evento de varios días ya empezado
        if not fecha:
            continue
        if hora and hora != "00:00":
            fecha = f"{fecha}T{hora}"
        try:
            precio = float(x.get("precio_min") or 0) or None
        except ValueError:
            precio = None
        categoria = html.unescape(x.get("upper_category_name") or "")
        if x.get("category_name"):
            categoria = f"{categoria} / {html.unescape(x['category_name'])}".strip(" /")
        salida.append(base.evento(
            PORTAL,
            html.unescape(x.get("nombre") or ""),
            fecha,
            x.get("url") or f"https://www.passline.com/eventos/{x.get('slug')}",
            lugar=html.unescape(x.get("lugar") or ""),
            ciudad=("CABA" if base.sin_acentos(region) == "capital federal"
                    else html.unescape(x.get("nombre_communa") or "") or region),
            provincia=provincia,
            imagen=x.get("recorte") or x.get("miniatura") or None,
            precio=precio,
            categoria=categoria or None,
        ))
    return salida
