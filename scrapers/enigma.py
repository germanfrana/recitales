"""Enigma Tickets: app Remix con los datos en window.__remixContext.

- Portada (/): loaderData["routes/_index"] trae nextEvents y featuredEvents
  (los "tours" se abren con /tour/<uid>, que trae childEvents).
- Detalle (/event/<uid>): schedules con fecha (año/mes/día) y una etiqueta
  tipo "Vie 04/12 21:00hs" de donde sale la hora.
- El lugar solo trae nombre y un link corto de Google Maps: se sigue la
  redirección (sin bajar la página) para sacar las coordenadas y ubicar la
  provincia cuando el nombre no alcanza.
El portal no tiene categorías: es casi todo música (Deseo Club, festivales);
se descartan fiestas y otras cosas por palabras clave.
"""
import json
import re
import time
from datetime import date, datetime, timedelta, timezone

from scrapers import base

PORTAL = "Enigma Tickets"
SITIO = "https://www.enigmatickets.com"
PAUSA = 0.3
MAX_EVENTOS = 120
_ART = timezone(timedelta(hours=-3))

# Fiestas/ciclos sin artista y otros rubros que no son recitales.
_EXCLUIR = re.compile(
    r"\b(fiesta|party|navidad|stand ?up|teatro|taller|curso|charla|"
    r"pop hereje|militantes del climax|vicio fantasia|six sex|bingo)\b")
_NO_EXCLUIR = re.compile(r"\bfestival\b")


def _remix(ruta):
    html = base.get(SITIO + ruta).text
    marca = "window.__remixContext = "
    i = html.find(marca)
    if i < 0:
        raise ValueError("Enigma: no se encontró __remixContext en " + ruta)
    d, _ = json.JSONDecoder().raw_decode(html[i + len(marca):])
    return d["state"]["loaderData"]


_coords_cache = {}


def _coords(url_mapa):
    """Sigue el link corto de Google Maps y devuelve (lat, lon) o None."""
    if not url_mapa:
        return None
    if url_mapa in _coords_cache:
        return _coords_cache[url_mapa]
    res = None
    try:
        r = base.get(url_mapa, allow_redirects=False, timeout=15)
        destino = r.headers.get("Location") or url_mapa
        m = (re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", destino) or
             re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", destino))
        if m:
            res = (float(m.group(1)), float(m.group(2)))
    except Exception:
        res = None
    _coords_cache[url_mapa] = res
    return res


def _provincia_por_coords(lat, lon):
    """Cajas aproximadas; alcanzan para separar las tres provincias del resto."""
    if -35.0 <= lat <= -29.4 and -65.8 <= lon <= -61.9:
        return "Córdoba"
    # Santa Fe (el sur angosto se corta en San Nicolás, que es Buenos Aires).
    if -34.4 <= lat <= -28.0 and -62.0 <= lon <= -58.8 and \
            not (lat < -33.25 and lon > -60.45):
        return "Santa Fe"
    if -41.1 <= lat <= -33.25 and -63.4 <= lon <= -56.6:
        return "Buenos Aires"
    return None


_MESES = {m: i + 1 for i, m in enumerate(
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre "
    "noviembre diciembre".split())}


def _dias_de_etiqueta(etiqueta, anio):
    """'16, 17 y 18 DE ABRIL' -> ['AAAA-04-16', ...] (fecha real cuando el
    schedule tiene una fecha comodín)."""
    m = re.search(r"((?:\d{1,2}\s*(?:,|y)\s*)*\d{1,2})\s+de\s+([a-z]+)",
                  base.sin_acentos(etiqueta or ""))
    if not m or m.group(2) not in _MESES:
        return []
    mes = _MESES[m.group(2)]
    return [f"{anio:04d}-{mes:02d}-{int(d):02d}"
            for d in re.findall(r"\d{1,2}", m.group(1))]


def _hora(etiqueta):
    m = re.search(r"(\d{1,2})[:.](\d{2})\s*h", etiqueta or "", re.I)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def _lista_eventos():
    ld = _remix("/")["routes/_index"]
    eventos, vistos = [], set()
    for e in (ld.get("nextEvents") or []) + (ld.get("featuredEvents") or []):
        if e.get("isTour"):
            time.sleep(PAUSA)
            try:
                tour = _remix("/tour/" + e["uid"])
                hijos = next((v.get("childEvents") for v in tour.values()
                              if isinstance(v, dict) and "childEvents" in v), [])
            except Exception:
                hijos = []
            for h in hijos or []:
                if h["uid"] not in vistos:
                    vistos.add(h["uid"])
                    eventos.append(h)
        elif e.get("uid") and e["uid"] not in vistos:
            vistos.add(e["uid"])
            eventos.append(e)
    return eventos[:MAX_EVENTOS]


def obtener():
    hoy = date.today().isoformat()
    salida = []
    for resumen in _lista_eventos():
        titulo = (resumen.get("title") or "").strip()
        if _EXCLUIR.search(base.sin_acentos(titulo)) and \
                not _NO_EXCLUIR.search(base.sin_acentos(titulo)):
            continue
        uid = resumen["uid"]
        url = f"{SITIO}/event/{uid}"
        time.sleep(PAUSA)
        try:
            ev = _remix("/event/" + uid).get("routes/event.$eventId", {}).get("event") or {}
        except Exception:
            ev = {}
        venue = ev.get("venue") or resumen.get("venue") or {}
        lugar = venue.get("name") or resumen.get("placeDescription")
        prov = base.provincia_de(lugar, titulo)
        c = _coords(venue.get("url"))
        if prov is None and c:
            prov = _provincia_por_coords(*c)
        ciudad = None
        if c and -34.71 <= c[0] <= -34.52 and -58.54 <= c[1] <= -58.33:
            ciudad = "CABA"
        if prov not in base.PROVINCIAS:
            continue
        if ev.get("isFinished"):
            continue

        fechas = []
        for s in (ev.get("schedules") or {}).values():
            d = s.get("date") or {}
            if not d.get("year"):
                continue          # p. ej. "Abonos"
            etiqueta = s.get("labelForReplaceDate")
            h = _hora(etiqueta)
            dias = _dias_de_etiqueta(etiqueta, d["year"]) or                 [f"{d['year']:04d}-{d['month']:02d}-{d['day']:02d}"]
            fechas += [f"{f}T{h}" if h else f for f in dias]
        if not fechas:            # sin detalle: fechas de la portada (00:00 ART)
            fechas = [datetime.fromtimestamp(t, _ART).date().isoformat()
                      for t in resumen.get("eventDates") or []]
        precios = [p.get("price") for s in (ev.get("schedules") or {}).values()
                   for p in (s.get("enabledPrices") or {}).values()
                   if p.get("price")]
        for f in sorted(set(fechas)):
            if f[:10] < hoy:
                continue
            salida.append(base.evento(
                PORTAL, titulo, f, url, lugar=lugar, ciudad=ciudad, provincia=prov,
                imagen=ev.get("imageUrl") or resumen.get("imageUrl"),
                precio=min(precios) if precios else None,
                categoria=None))
    return salida
