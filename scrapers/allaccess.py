"""AllAccess (www.allaccess.com.ar).

Plataforma Crowder (app Rendr): la API JSON (public.getcrowder.com y /api/
del sitio) pide autenticación o la rechaza el WAF, pero cada página trae el
modelo completo embebido en App.bootstrapData({...}).

Recorrido:
  1. juntar links /event/<slug> de la home, de las páginas de sede (/venue/...)
     que enlaza la home y de los resultados de búsqueda /list/<letra> (la
     búsqueda devuelve como mucho 50 por consulta, por eso varias letras);
  2. abrir cada evento y leer de bootstrapData la sede (ciudad/provincia) y
     las funciones (shows[].startDate, en UTC). Un registro por función.

El portal no tiene categorías cargadas (category viene null): casi todo es
música; se descartan por palabras clave los que claramente no lo son.
robots.txt no tiene reglas para "*" (no prohíbe nada).
"""
import json
import re
import time
from datetime import date, datetime, timedelta, timezone

from scrapers import base

PORTAL = "AllAccess"

SITIO = "https://www.allaccess.com.ar"
BUSQUEDAS = "aeiousmcdu"
MAX_EVENTOS = 150
PAUSA = 0.3
ARG = timezone(timedelta(hours=-3))

NO_MUSICA = re.compile(
    r"stand[\s-]?up|\bhumor|comedia|\bobra\b|teatro infantil|infantil|\bmagia\b|"
    r"\bpolo\b|paddle|padel|f[uú]tbol|\bpartido\b|\bboxeo\b|conferencia|"
    r"\bcharla\b|workshop|\btaller\b|\bpole\b|merchandising|estacionamiento|"
    r"parking|gift ?card|\bkids\b|astrol[oó]gico|vocal coach",
    re.I)

MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
         "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
         "octubre": 10, "noviembre": 11, "diciembre": 12}


def _bootstrap(html):
    i = html.find("App.bootstrapData(")
    if i < 0:
        return None
    try:
        d, _ = json.JSONDecoder().raw_decode(html[i + len("App.bootstrapData("):])
    except ValueError:
        return None
    return (d.get("model") or {}).get("data")


def _links(html):
    return set(re.findall(r"(?:allaccess\.com\.ar)?/event/([A-Za-z0-9_-]+)", html))


def _slugs():
    slugs = set()
    home = base.get(SITIO + "/").text
    slugs |= _links(home)
    sedes = set(re.findall(r"/venue/([A-Za-z0-9_-]+)", home))
    for sede in sorted(sedes):
        time.sleep(PAUSA)
        try:
            slugs |= _links(base.get(f"{SITIO}/venue/{sede}").text)
        except Exception:
            pass
    for q in BUSQUEDAS:
        time.sleep(PAUSA)
        try:
            data = _bootstrap(base.get(f"{SITIO}/list/{q}").text) or {}
        except Exception:
            continue
        for w in data.get("widgetComponents") or []:
            for c in (w.get("state") or {}).get("cards") or []:
                m = re.search(r"/event/([A-Za-z0-9_-]+)", c.get("link") or "")
                if m:
                    slugs.add(m.group(1))
    return sorted(slugs)


def _fecha_texto(desc):
    """'21 de Agosto 2027' -> '2027-08-21' (solo si trae año)."""
    m = re.search(r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+(?:de\s+)?(\d{4})",
                  desc or "", re.I)
    if not m or base.sin_acentos(m.group(2)) not in MESES:
        return None
    try:
        return date(int(m.group(3)), MESES[base.sin_acentos(m.group(2))],
                    int(m.group(1))).isoformat()
    except ValueError:
        return None


def _fechas(ev):
    fechas = set()
    for s in ev.get("shows") or []:
        sd = s.get("startDate")
        if not sd:
            continue
        try:
            dt = datetime.fromisoformat(sd.replace("Z", "+00:00"))
        except ValueError:
            continue
        fechas.add(dt.astimezone(ARG).strftime("%Y-%m-%dT%H:%M"))
    if not fechas:
        f = _fecha_texto(ev.get("description"))
        if f:
            fechas.add(f)
    hoy = date.today().isoformat()
    return sorted(f for f in fechas if f[:10] >= hoy)


def _precio(html):
    precios = []
    for m in re.finditer(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            ld = json.loads(m.group(1))
        except ValueError:
            continue
        offers = ld.get("offers") if isinstance(ld, dict) else None
        if isinstance(offers, dict):
            offers = [offers]
        for o in offers or []:
            try:
                p = float(o.get("price"))
                if p > 0:
                    precios.append(p)
            except (TypeError, ValueError):
                pass
    return min(precios) if precios else None


def obtener():
    salida = []
    for slug in _slugs()[:MAX_EVENTOS]:
        time.sleep(PAUSA)
        url = f"{SITIO}/event/{slug}"
        try:
            html = base.get(url).text
        except Exception:
            continue
        ev = _bootstrap(html)
        if not ev or not ev.get("name"):
            continue
        titulo = ev["name"]
        if NO_MUSICA.search(titulo):
            continue
        venue = ev.get("venue") or {}
        dire = venue.get("address") or {}
        lugar = venue.get("name")
        ciudad = dire.get("city")
        prov = base.provincia_de(dire.get("province"), ciudad, lugar)
        if prov is None:
            continue
        imagen = ev.get("thumbImage") or ev.get("image")
        if not imagen:
            m = re.search(r'property="og:image" content="([^"]+)"', html)
            imagen = m.group(1) if m else None
        precio = _precio(html)
        for f in _fechas(ev):
            salida.append(base.evento(PORTAL, titulo, f, url, lugar=lugar,
                                      ciudad=ciudad, provincia=prov,
                                      imagen=imagen, precio=precio,
                                      categoria=ev.get("category")))
    return salida
