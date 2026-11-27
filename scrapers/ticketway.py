"""Ticketway (www.ticketway.com.ar) - fuerte en Santa Fe y Paraná.

La app (Ionic) pide la cartelera completa con un POST a su backend:
    POST https://www.ticketway.com.ar/twn/be/carteleras
y devuelve todos los espectáculos en una sola respuesta. El portal no tiene
categorías, así que se descartan por palabras los que claramente no son
música (ballet, fiestas temáticas, stand up...). Alguna obra de teatro
puede colarse.
"""
import re

from scrapers import base

PORTAL = "Ticketway"
BACK = "https://www.ticketway.com.ar/twn/be/"

_NO_MUSICA = re.compile(
    r"\b(ballet|danza|stand ?up|humor|comedia|obra|teatro infantil|infantil|"
    r"fiesta retro|tunel del tiempo|wallet|taller|curso|charla|magia)\b")


def obtener():
    r = base.post(BACK + "carteleras",
                  json={"espectaculoId": None, "turno": None,
                        "turnoValido": False, "allEvent": True},
                  headers={"Origin": "https://www.ticketway.com.ar",
                           "Referer": "https://www.ticketway.com.ar/"})
    datos = r.json()["data"]["espectaculos_disponibles"] or []
    eventos = []
    for e in datos:
        if not e.get("fec_inicio") or e.get("cancelado"):
            continue
        nombre = (e.get("nombre") or "").strip().strip('"')
        if _NO_MUSICA.search(base.sin_acentos(nombre)):
            continue
        localidad = (e.get("establecimineto_localidad") or "").strip()
        lugar = (e.get("establecimiento_nombre") or "").strip()
        direccion = " ".join(str(x) for x in (e.get("establecimiento_calle"),
                                              e.get("establecimiento_altura")) if x)
        fecha = e["fec_inicio"][:16].replace(" ", "T")
        img = e.get("imagen_mini") or e.get("imagen")
        eventos.append(base.evento(
            PORTAL, nombre, fecha,
            f"https://www.ticketway.com.ar/#/cartelera?evento={e['id']}",
            lugar=lugar, ciudad=localidad.title() or None,
            provincia=base.provincia_de(localidad, lugar, direccion),
            imagen=BACK + img if img else None,
            categoria="Agotado" if e.get("agotado") else None,
        ))
    return [e for e in eventos if e["provincia"] in base.PROVINCIAS]
