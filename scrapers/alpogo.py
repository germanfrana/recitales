"""Alpogo (alpogo.com).

El sitio (Astro) consulta la API JSON pública apiweb.alpogo.com/api. Se usa
/events/search/fulltext?type=<actividad>&page=N&take=100, que pagina por
tipo de actividad. Cada evento trae una sola fecha (primera_funcion); cuando
hay varias funciones Alpogo suele publicarlas como eventos separados.
"""
import re
from datetime import date

from scrapers import base

PORTAL = "Alpogo"

API = "https://apiweb.alpogo.com/api/events/search/fulltext"
# Actividades de Alpogo que son música en vivo (se excluyen Fiesta/Disco,
# Baile, Teatro, Stand up, Cultural, etc.).
ACTIVIDADES = ["Recital", "Festival", "Tributo", "Peña", "Café Concert"]
PROVINCIAS = {"buenos aires": "Buenos Aires", "capital federal": "Buenos Aires",
              "ciudad autonoma de buenos aires": "Buenos Aires", "caba": "Buenos Aires",
              "cordoba": "Córdoba", "santa fe": "Santa Fe"}


def _slug(nombre, id_):
    s = base.sin_acentos(nombre or "")
    s = re.sub(r"<[^>]*>", "", s)
    s = re.sub(r"[^\w\d _-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return f"{s or 'evento'}-{id_}"


def _por_actividad(actividad):
    salida, pagina = [], 1
    while pagina <= 30:  # tope de seguridad (100 por página)
        d = base.get(API, params={"page": pagina, "take": 100, "type": actividad},
                     headers={"Accept": "application/json"}).json()
        salida += d.get("data") or []
        if pagina >= (d.get("meta") or {}).get("pages", 0):
            break
        pagina += 1
    return salida


def _ubicacion(x):
    """(lugar, ciudad, provincia) a partir de place_*."""
    nombre = (x.get("place_name") or "").strip()
    ciudad = (x.get("place_city") or "").strip()
    prov_txt = (x.get("place_province") or "").strip()
    lugar = nombre
    # place_name suele venir como "Venue, Ciudad"
    if "," in nombre:
        lugar, _, resto = nombre.rpartition(",")
        lugar = lugar.strip()
        if not ciudad:
            ciudad = resto.strip().rstrip(".")
    if prov_txt:
        provincia = PROVINCIAS.get(base.sin_acentos(prov_txt))
        p = base.sin_acentos(prov_txt)
        if "autonoma" in p or "capital federal" in p or p == "caba":
            ciudad = "CABA"  # place_city trae la comuna o el barrio
        elif ciudad.lower() == "capital":
            ciudad = prov_txt
    else:
        provincia = base.provincia_de(ciudad)
    return lugar or nombre, ciudad, provincia


def obtener():
    hoy = date.today().isoformat()
    vistos, salida = set(), []
    for actividad in ACTIVIDADES:
        for x in _por_actividad(actividad):
            if x.get("id") in vistos:
                continue
            vistos.add(x.get("id"))
            if (x.get("place_country") or "ar") != "ar" or x.get("visible") is False:
                continue
            if x.get("status") == 0:  # finalizado
                continue
            fecha = (x.get("primera_funcion") or "")[:16]
            if not fecha or fecha[:10] < hoy:
                continue
            lugar, ciudad, provincia = _ubicacion(x)
            if provincia not in base.PROVINCIAS:
                continue
            if fecha.endswith("T00:00"):
                fecha = fecha[:10]
            precio = x.get("price_from")
            salida.append(base.evento(
                PORTAL,
                x.get("nombre"),
                fecha,
                f"https://alpogo.com/evento/{_slug(x.get('nombre'), x.get('id'))}",
                lugar=lugar,
                ciudad=ciudad,
                provincia=provincia,
                imagen=x.get("featured_image") or x.get("image") or None,
                precio=float(precio) if precio else None,
                categoria=x.get("actividad") or actividad,
            ))
    return salida
