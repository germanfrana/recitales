"""Tu Entrada: búsqueda por categoría (Next.js App Router).

La página /busqueda?categoria=<nombre> trae los resultados ya renderizados en
el payload RSC (self.__next_f.push) como un arreglo "events" con nombre,
lugar, ciudad, fecha e imagen. Pagina de a 6 con un cursor en el enlace
"Siguiente".
"""
import json
import re
import time
from urllib.parse import quote

from scrapers import base

PORTAL = "Tu Entrada"
SITIO = "https://www.tuentrada.com"
CATEGORIAS = ["Música", "Festivales De Música", "Jazz/blues"]
MAX_PAGINAS = 40          # por categoría (6 eventos por página)
PAUSA = 0.3

_RE_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', re.S)
_RE_SIGUIENTE = re.compile(
    r'"href":"(/busqueda\?[^"]*cursor=[^"]*)","children":\[\["\$","span",null,'
    r'\{"children":"Siguiente"')
_RE_FECHA = re.compile(r"(\d{2})-(\d{2})-(\d{4})(?:\s+(\d{1,2}):(\d{2}))?")


def _pagina(ruta):
    html = base.get(SITIO + ruta).text
    rsc = "".join(json.loads('"' + c + '"') for c in _RE_CHUNK.findall(html))
    i = rsc.find('"events":[', rsc.find("Resultados de b"))
    eventos = []
    if i >= 0:
        eventos, _ = json.JSONDecoder().raw_decode(rsc[i + len('"events":'):])
    m = _RE_SIGUIENTE.search(rsc)
    return eventos, (m.group(1) if m else None)


def _fecha(texto):
    m = _RE_FECHA.search(texto or "")
    if not m:
        return None
    d, mes, a, h, mi = m.groups()
    f = f"{a}-{mes}-{d}"
    return f"{f}T{int(h):02d}:{mi}" if h else f


def obtener():
    vistos, salida = set(), []
    for cat in CATEGORIAS:
        ruta = "/busqueda?categoria=" + quote(cat)
        for _ in range(MAX_PAGINAS):
            eventos, ruta = _pagina(ruta)
            for e in eventos:
                if e.get("id") in vistos:
                    continue
                vistos.add(e.get("id"))
                fecha = _fecha(e.get("dateRange"))
                if not fecha:
                    continue
                prov = base.provincia_de(e.get("city"), e.get("venue"))
                if prov not in base.PROVINCIAS:
                    continue
                img = (e.get("imageMainNew") or {}).get("src")
                salida.append(base.evento(
                    PORTAL, e.get("name"), fecha, f"{SITIO}/{e.get('slug')}",
                    lugar=e.get("venue"), ciudad=e.get("city"), provincia=prov,
                    imagen=img, categoria=cat))
            if not ruta:
                break
            time.sleep(PAUSA)
    return salida
