"""Autoentrada (autoentrada.com).

autoentrada.com solo responde por http y redirige a ventas.autoentrada.com
(plataforma Ticketplus). Se leen los listados de categoría /taxons/musica y
/taxons/fiesta (donde cuelgan los festivales, p. ej. Cosquín) y después el
JSON-LD (schema.org Event) de cada página /events/<slug>. robots.txt permite
/events/<slug> y /taxons; prohíbe /api/*, /eventos/* y subrutas de compra,
que no se usan.
"""
import json
import re
import time
from datetime import date

from bs4 import BeautifulSoup

from scrapers import base

PORTAL = "Autoentrada"

SITIO = "https://ventas.autoentrada.com"
# taxón -> se acepta todo (True) o solo si el título suena a festival (False)
TAXONES = {"musica": True, "fiesta": False}
EXCLUIR = ("muestra final", "taller de", "comedia musical", "visitas guiadas")
MAX_EVENTOS = 150


def _links(taxon):
    h = base.get(f"{SITIO}/taxons/{taxon}").text
    s = BeautifulSoup(h, "html.parser")
    salida = []
    for a in s.select("div.evento a[href*='/events/']") or s.find_all("a", href=re.compile(r"^/events/[^/]+$")):
        href = a["href"]
        titulo = a.find("h2").get_text(" ", strip=True) if a.find("h2") else ""
        salida.append((SITIO + href if href.startswith("/") else href, titulo))
    return salida


def _jsonld_evento(html):
    s = BeautifulSoup(html, "html.parser")
    for tag in s.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(tag.string or "")
        except ValueError:
            continue
        for x in d if isinstance(d, list) else [d]:
            if isinstance(x, dict) and x.get("@type") == "Event":
                return x
    return None


def obtener():
    candidatos = {}
    for taxon, todo in TAXONES.items():
        for url, titulo in _links(taxon):
            t = base.sin_acentos(titulo)
            if any(e in t for e in EXCLUIR):
                continue
            if not todo and "festival" not in t:
                continue
            candidatos.setdefault(url, ("Música" if taxon == "musica" else "Festival", titulo))

    hoy = date.today().isoformat()
    salida = []
    for i, (url, (categoria, titulo)) in enumerate(list(candidatos.items())[:MAX_EVENTOS]):
        if i:
            time.sleep(0.3)
        ev = _jsonld_evento(base.get(url).text)
        if not ev:
            continue
        inicio = ev.get("startDate") or ""
        fin = ev.get("endDate") or inicio
        if not inicio or fin[:10] < hoy:
            continue
        fecha = inicio[:16] if len(inicio) >= 16 else inicio[:10]
        if fecha[:10] < hoy:
            fecha = hoy  # varios días, ya empezado
        loc = ev.get("location") or {}
        dire = loc.get("address") or {}
        region = dire.get("addressRegion") or ""
        ciudad = dire.get("addressLocality") or ""
        if ciudad.lower() == "capital":
            ciudad = region
        # Con región se usa solo la región: los departamentos de otras
        # provincias ("Doctor Manuel Belgrano", Jujuy) engañan a provincia_de.
        provincia = base.provincia_de(region) if region else base.provincia_de(ciudad)
        if provincia not in base.PROVINCIAS:
            continue
        ofertas = ev.get("offers") or {}
        if isinstance(ofertas, list):
            ofertas = ofertas[0] if ofertas else {}
        try:
            precio = float(ofertas.get("lowPrice") or ofertas.get("price") or 0) or None
        except (TypeError, ValueError):
            precio = None
        salida.append(base.evento(
            PORTAL,
            titulo or ev.get("name"),  # el listado trae los acentos; el JSON-LD no
            fecha,
            ev.get("url") or url,
            lugar=loc.get("name"),
            ciudad=ciudad,
            provincia=provincia,
            imagen=ev.get("image") if isinstance(ev.get("image"), str) else None,
            precio=precio,
            categoria=categoria,
        ))
    return salida
