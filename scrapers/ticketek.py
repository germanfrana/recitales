"""Ticketek Argentina (www.ticketek.com.ar).

El sitio es AngularJS y lee todo de la API del CMS (Drupal):
    https://prod-cms-api.ticketek.com.ar/api/1.0/node%3Fpath%3D<ruta>
(la ruta va con la primera "/" cambiada por "--" y todo url-encodeado, igual
que hace node/node.factory.js).

No se usa la API de búsqueda (prod-cms-search.ticketek.com.ar): su robots.txt
tiene "Disallow: /".

Recorrido:
  1. nodos de listado: home, musica y cada subcategoría de música;
  2. de cada ítem se queda con los de categoría Música en las provincias
     pedidas (los ítems de "artista" sin sede se abren para ver sus shows);
  3. abre el nodo de cada show y arma un registro por función
     (data-performances del widget tkt-show-ticket).
"""
import time
from datetime import date, datetime, timezone
from urllib.parse import quote

from scrapers import base

PORTAL = "Ticketek"

API = "https://prod-cms-api.ticketek.com.ar/api/1.0/node%3Fpath%3D"
SITIO = "https://www.ticketek.com.ar/"
MAX_SHOWS = 130
PAUSA = 0.3
NO_MUSICA = {"teatro", "familia", "infantiles", "deportes", "humor", "stand up",
             "experiencias", "exposiciones", "musical"}


def _nodo(ruta):
    ruta = ruta.strip("/").replace("/", "--", 1)
    try:
        return base.get(API + quote(ruta, safe="")).json()
    except Exception:
        return None


def _widgets(nodo):
    for ws in (nodo or {}).get("widgets", {}).values():
        for w in ws or []:
            if isinstance(w, dict):
                yield w


def _es_musica(cats):
    nombres = {base.sin_acentos(c) for c in cats}
    if "musica" in nombres:
        return True
    return not cats  # sin categorías: se decide al abrir el show


def _provincia_ok(venue):
    if not venue or not (venue.get("state") or venue.get("city")):
        return True  # sin datos: se decide al abrir el show
    return base.provincia_de(venue.get("state"), venue.get("city")) is not None


def _img(u):
    if u and u.startswith("//"):
        return "https:" + u
    return u or None


def _candidatos():
    """Rutas de shows (artista/sede) y de artistas sueltos a revisar."""
    rutas = {}
    musica = _nodo("musica")
    listados = [_nodo("home"), musica]
    for w in _widgets(musica):
        if w.get("type") == "tkt-subcategories":
            for it in w.get("items") or []:
                if it.get("link"):
                    time.sleep(PAUSA)
                    listados.append(_nodo(it["link"]))
    for nodo in listados:
        for w in _widgets(nodo):
            for a in w.get("artists") or []:
                url = (a.get("url") or "").strip("/")
                cats = [c.get("title", "") for c in a.get("categories") or []]
                if not url or url in rutas:
                    continue
                if not _es_musica(cats) or not _provincia_ok(a.get("venue")):
                    continue
                rutas[url] = a
    return rutas


def _shows_de_artista(ruta):
    nodo = _nodo(ruta)
    links = []
    for w in _widgets(nodo):
        if w.get("type") == "tkt-artist-shows":
            for s in w.get("shows") or []:
                loc = s.get("venue-locality") or ""
                if s.get("link") and base.provincia_de(loc, s.get("venue-title")):
                    links.append(s["link"].strip("/"))
    return links


def _fechas(nodo):
    fechas = []
    for w in _widgets(nodo):
        if w.get("type") != "tkt-show-ticket":
            continue
        perfs = w.get("data-performances") or {}
        if isinstance(perfs, dict):
            perfs = perfs.values()
        for p in perfs:
            try:
                ts = int(p.get("date"))
            except (TypeError, ValueError):
                continue
            # El timestamp trae la hora local de Argentina como si fuera UTC.
            fechas.append(datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M"))
    if not fechas:
        for g in nodo.get("google_structured_data") or []:
            sd = (g or {}).get("startDate") or ""
            if len(sd) >= 16:
                fechas.append(sd[:16])
    hoy = date.today().isoformat()
    return sorted(f for f in set(fechas) if f[:10] >= hoy)


def _precio(nodo):
    p = nodo.get("lowerPrice")
    try:
        return float(p) if p else None
    except (TypeError, ValueError):
        return None


def obtener():
    candidatos = _candidatos()
    shows = []
    for ruta in candidatos:
        if "/" in ruta:
            shows.append(ruta)
        else:
            time.sleep(PAUSA)
            shows.extend(_shows_de_artista(ruta))
    vistos, salida = set(), []
    for ruta in shows:
        if ruta in vistos or len(vistos) >= MAX_SHOWS:
            continue
        vistos.add(ruta)
        time.sleep(PAUSA)
        nodo = _nodo(ruta)
        if not nodo or nodo.get("layout") != "full_show":
            continue
        cat = (nodo.get("category") or {}).get("parent") or ""
        if base.sin_acentos(cat) != "musica":
            continue
        item = candidatos.get(ruta) or {}
        cats = [c.get("title", "") for c in item.get("categories") or []]
        # Sin un género musical además de "Musica" y con alguna categoría de
        # otro rubro (Familia, Teatro, Musical...): no es un recital.
        otras = {base.sin_acentos(c) for c in cats} - {"musica"}
        if otras and otras <= NO_MUSICA:
            continue
        venue = nodo.get("venue") or {}
        lugar = venue.get("title")
        ciudad = venue.get("city")
        estado = venue.get("state")
        prov = base.provincia_de(estado, ciudad)
        if prov is None:
            continue
        # "Centro", "Belgrano", etc. son barrios de CABA
        if base.sin_acentos(estado) in ("capital federal", "caba"):
            ciudad = "CABA"
        titulo = (nodo.get("artist") or {}).get("title") or nodo.get("title")
        meta = (nodo.get("metatags") or {}).get("property") or {}
        imagen = _img(meta.get("og:image") or item.get("imagelandscape") or item.get("image"))
        url = (nodo.get("metatags") or {}).get("canonical") or SITIO + ruta
        categoria = ", ".join(c for c in cats if c != "Musica") or "Música"
        for f in _fechas(nodo):
            salida.append(base.evento(PORTAL, titulo, f, url, lugar=lugar,
                                      ciudad=ciudad, provincia=prov, imagen=imagen,
                                      precio=_precio(nodo), categoria=categoria))
    return salida
