"""Eventbrite Argentina: páginas de búsqueda /d/<lugar>/music--events/.

Cada página trae los resultados en window.__SERVER_DATA__ (search_data.events:
results + pagination, 20 por página). Se recorren el país y las ciudades /
provincias de interés y se deduplica por id.

Notas:
- Sin "?page=N" algunas URL redirigen (301) a /b/<lugar>/music/, una página
  "browse" con solo 8 resultados; por eso siempre se pide con ?page=N y sin
  seguir redirecciones.
- robots.txt prohíbe /api/v3/destination/events/ (la API que usa la web), así
  que no se usa; las páginas /d/ están permitidas.
- CloudFront corta con 429 si se piden muchas páginas seguidas: pausa larga y,
  ante un 429, una espera y un reintento; si sigue, se devuelve lo juntado.
"""
import json
import re
import time

import requests

from scrapers import base

PORTAL = "Eventbrite"
SITIO = "https://www.eventbrite.com.ar"
LUGARES = [
    "argentina",
    "argentina--ciudad-de-buenos-aires",
    "argentina--buenos-aires",                 # Gran Buenos Aires
    "argentina--buenos-aires--85668015",       # provincia de Buenos Aires
    "argentina--la-plata",
    "argentina--mar-del-plata",
    "argentina--c%C3%B3rdoba",                 # ciudad de Córdoba
    "argentina--cordoba--85668031",            # provincia de Córdoba
    "argentina--rosario",
    "argentina--santa-fe",                     # provincia de Santa Fe
]
MAX_PAGINAS = 6        # por lugar
MAX_PETICIONES = 40
PAUSA = 1.5
ESPERA_429 = 30

MUSICA = "EventbriteCategory/103"
FORMATOS_OK = {"EventbriteFormat/5",   # Festival or Fair
               "EventbriteFormat/6"}   # Concert or Performance
_EXCLUIR = re.compile(r"\b(taller|workshop|clase|clases|curso|seminario|"
                      r"stand ?up|masterclass|bingo|charla|conferencia)\b")
# Fiestas: solo se miran en el título (el resumen dice "fiesta" en recitales).
_EXCLUIR_TITULO = re.compile(r"\b(fiesta|party|karaoke|feria|patin|ejemplo)\b")
_OTRAS = re.compile(
    r"entre rios|mendoza|san luis|la pampa|neuquen|rio negro|chubut|"
    r"santa cruz|tierra del fuego|misiones|corrientes|chaco|formosa|"
    r"santiago del estero|tucuman|salta|jujuy|catamarca|la rioja|san juan|"
    r"uruguay|chile")
_MARCA = "window.__SERVER_DATA__ = "


class _Cortado(Exception):
    pass


def _pagina(lugar, n):
    url = f"{SITIO}/d/{lugar}/music--events/?page={n}"
    for intento in range(2):
        try:
            r = base.get(url, allow_redirects=False)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                if intento == 0:
                    time.sleep(ESPERA_429)
                    continue
                raise _Cortado()
            raise
        if r.status_code != 200:
            return None               # redirección u otra cosa: lugar inválido
        i = r.text.find(_MARCA)
        if i < 0:
            return None
        d, _ = json.JSONDecoder().raw_decode(r.text[i + len(_MARCA):])
        return (d.get("search_data") or {}).get("events") or {}
    raise _Cortado()


def _es_musica(e):
    tags = {t.get("tag") for t in e.get("tags") or []}
    if MUSICA not in tags or e.get("is_online_event") or e.get("is_cancelled"):
        return False
    subcat = any((t or "").startswith("EventbriteSubCategory/") for t in tags)
    if not (tags & FORMATOS_OK or subcat):
        return False
    nombre = base.sin_acentos(e.get("name") or "")
    texto = nombre + " " + base.sin_acentos(e.get("summary") or "")
    return not (_EXCLUIR.search(texto) or _EXCLUIR_TITULO.search(nombre))


def _registro(e):
    v = e.get("primary_venue") or {}
    a = v.get("address") or {}
    ciudad, region = a.get("city"), a.get("region")
    # La región manda cuando es una provincia. Si es otra provincia, afuera
    # (evita que "Av. San Martín" en Paraná, Entre Ríos, cuente como Bs. As.).
    prov = base.provincia_de(region) if region else None
    if prov is None and not _OTRAS.search(base.sin_acentos(region or "")):
        # Región vacía o un departamento ("Colon"): ciudad y nombre del lugar
        # (no la calle, que da falsos positivos).
        prov = base.provincia_de(ciudad, v.get("name"))
    if prov not in base.PROVINCIAS:
        return None
    fecha = e.get("start_date")
    if not fecha:
        return None
    if e.get("start_time"):
        fecha += "T" + e["start_time"][:5]
    url = re.sub(r"^https?://[^/]+", SITIO, e.get("url") or "")
    img = e.get("image") or {}
    imagen = (img.get("original") or {}).get("url") or img.get("url")
    if base.sin_acentos(region or "").startswith("cdad. autonoma"):
        ciudad = "CABA"
    cat = next((t.get("display_name") for t in e.get("tags") or []
                if (t.get("tag") or "").startswith("EventbriteSubCategory/")),
               "Música")
    return base.evento(PORTAL, e.get("name"), fecha, url, lugar=v.get("name"),
                       ciudad=ciudad, provincia=prov, imagen=imagen,
                       categoria=cat)


def obtener():
    vistos, salida, peticiones = set(), [], 0
    try:
        for lugar in LUGARES:
            for n in range(1, MAX_PAGINAS + 1):
                if peticiones >= MAX_PETICIONES:
                    raise _Cortado()
                if peticiones:
                    time.sleep(PAUSA)
                peticiones += 1
                ev = _pagina(lugar, n)
                if not ev:
                    break
                for e in ev.get("results") or []:
                    if e.get("id") in vistos:
                        continue
                    vistos.add(e.get("id"))
                    if _es_musica(e):
                        reg = _registro(e)
                        if reg:
                            salida.append(reg)
                pag = ev.get("pagination") or {}
                if n >= (pag.get("page_count") or 0):
                    break
    except _Cortado:
        if not salida:
            raise RuntimeError("Eventbrite: bloqueado (429) sin resultados")
    return salida
