"""Livepass (livepass.com.ar).

Listado: https://livepass.com.ar/events/search.json?q=&searching=true
(el endpoint de búsqueda que la propia home declara en su JSON-LD SearchAction;
con q vacío devuelve todos los eventos publicados, ~120, en una sola petición).
Trae título, categoría del portal (SHOW / TEATRO / ...), dirección, imagen,
precio y la fecha como texto sin año ("Sábado 06 de Marzo 21:00"): el año se
deduce por el día de la semana.

El nombre de la sede no viene en el listado: se toma del JSON-LD (schema.org
Event) de la página de un evento por cada dirección distinta (~15 peticiones).

robots.txt prohíbe /eventos/*, /api/* y subrutas de /events/<slug>/... (carrito,
ventas, etc.); /events/search.json y /events/<slug> están permitidas.

Categorías: SHOW se toma como música; TEATRO también, porque en Livepass la usa
sobre todo Café Berlín (sala de música en vivo). Se descartan las demás y los
títulos que por palabras clave no son recitales.
"""
import json
import re
import time
from datetime import date

from scrapers import base

PORTAL = "Livepass"

LISTADO = "https://livepass.com.ar/events/search.json?q=&searching=true"
CATEGORIAS = {"SHOW", "TEATRO"}
PAUSA = 0.3
MAX_SEDES = 40

NO_MUSICA = re.compile(
    r"merchandising|stand[\s-]?up|\bhumor|unipersonal|\bobra\b|infantil|"
    r"\bcharla\b|conferencia|\btaller\b|workshop",
    re.I)

MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
         "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
         "octubre": 10, "noviembre": 11, "diciembre": 12}
DIAS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4,
        "sabado": 5, "domingo": 6}


def _fecha(texto, hoy):
    """'Sábado 06 de Marzo 21:00' -> '2027-03-06T21:00'.

    El año es el primero (desde el actual) en que esa fecha cae en ese día de
    la semana; si ninguno coincide, la próxima ocurrencia de día y mes.
    """
    m = re.match(r"\s*(\w+)\s+(\d{1,2})\s+de\s+(\w+)\s*(\d{1,2}:\d{2})?",
                 base.sin_acentos(texto or ""))
    if not m or m.group(3) not in MESES:
        return None
    dia_sem = DIAS.get(m.group(1))
    dia, mes, hora = int(m.group(2)), MESES[m.group(3)], m.group(4)
    candidatas = []
    for anio in range(hoy.year, hoy.year + 3):
        try:
            candidatas.append(date(anio, mes, dia))
        except ValueError:
            pass
    futuras = [d for d in candidatas if d >= hoy]
    elegida = next((d for d in futuras if d.weekday() == dia_sem), None)
    if elegida is None:
        # Sin coincidencia de día de la semana: evento viejo o dato raro.
        if dia_sem is not None and any(d.weekday() == dia_sem for d in candidatas):
            return None
        elegida = futuras[0] if futuras else None
    if elegida is None:
        return None
    f = elegida.isoformat()
    if hora and hora != "00:00":
        f += "T" + hora.zfill(5)
    return f


def _ciudad(location):
    """Ciudad a partir de 'Calle 58 770, B1900 La Plata, Buenos Aires, Argentina'."""
    partes = [p.strip() for p in (location or "").split(",") if p.strip()]
    if partes and base.sin_acentos(partes[-1]) == "argentina":
        partes = partes[:-1]
    if not partes:
        return None
    ultima = partes[-1]
    sa = base.sin_acentos(ultima)
    if "ciudad autonoma" in sa or sa in ("caba", "capital federal"):
        return "CABA"
    if sa.startswith("provincia de") and len(partes) > 1:
        ultima = partes[-2]
    elif sa == "buenos aires" and len(partes) > 1:
        # "Calle 123, Buenos Aires" = CABA; "B1900 La Plata, Buenos Aires" = La Plata
        previa = re.sub(r"^[A-Z]\d{4}[A-Z]{0,3}\s+", "", partes[-2]).strip()
        if previa and not re.search(r"\d", previa) and not re.fullmatch(r"[A-Z]{2,4}", previa):
            return previa
        return "CABA"
    return re.sub(r"^[A-Z]\d{4}[A-Z]{0,3}\s+", "", ultima).strip() or None


def _sede(url):
    """Nombre de la sede desde el JSON-LD Event de la página del evento."""
    try:
        html = base.get(url).text
    except Exception:
        return None
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            ld = json.loads(m.group(1), strict=False)
        except ValueError:
            continue
        if isinstance(ld, dict) and ld.get("@type") == "Event":
            return ((ld.get("location") or {}).get("name") or "").strip() or None
    return None


def _sede_por_titulo(titulo):
    m = re.search(r"\s+en\s+(?:el\s+|la\s+|los\s+)?(.+)$", titulo or "", re.I)
    return m.group(1).strip() if m else None


def _precio(p):
    try:
        p = float(p)
    except (TypeError, ValueError):
        return None
    return p or None


def obtener():
    datos = base.get(LISTADO).json()
    hoy = date.today()
    sedes = {}
    salida = []
    for ev in datos.get("results") or []:
        cat = (ev.get("category") or "").strip().upper()
        titulo = re.sub(r"\s+", " ", ev.get("title") or "").strip()
        loc = ev.get("location")
        if cat not in CATEGORIAS or not loc or NO_MUSICA.search(titulo):
            continue
        ciudad = _ciudad(loc)
        prov = base.provincia_de(loc, ciudad)
        if prov is None:
            continue
        fecha = _fecha(ev.get("date"), hoy)
        if not fecha:
            continue
        url = ev.get("url")
        if loc not in sedes and len(sedes) < MAX_SEDES:
            time.sleep(PAUSA)
            sedes[loc] = _sede(url)
        lugar = sedes.get(loc) or _sede_por_titulo(titulo)
        salida.append(base.evento(PORTAL, titulo, fecha, url, lugar=lugar,
                                  ciudad=ciudad, provincia=prov,
                                  imagen=ev.get("img"),
                                  precio=_precio(ev.get("price")),
                                  categoria=cat.capitalize()))
    return salida
