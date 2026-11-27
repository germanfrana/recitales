"""Contrato común para los lectores de portales.

Cada portal es un módulo scrapers/<portal>.py con:

    PORTAL = "Nombre visible"
    def obtener() -> list[dict]

y cada dict es lo que devuelve evento(...) más abajo. Si el portal falla,
obtener() levanta la excepción: el armado general la registra y sigue con
los demás portales.
"""
import re
import unicodedata

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

sesion = requests.Session()
sesion.headers.update({"User-Agent": UA, "Accept-Language": "es-AR,es;q=0.9"})

PROVINCIAS = ("Buenos Aires", "Córdoba", "Santa Fe")


def get(url, **kw):
    kw.setdefault("timeout", 30)
    r = sesion.get(url, **kw)
    r.raise_for_status()
    return r


def post(url, **kw):
    kw.setdefault("timeout", 30)
    r = sesion.post(url, **kw)
    r.raise_for_status()
    return r


def sin_acentos(s):
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn").lower()


# Ciudades conocidas -> provincia (incluye CABA dentro de "Buenos Aires").
_CIUDADES = {
    "Buenos Aires": ["caba", "capital federal", "ciudad autonoma", "buenos aires",
                     "la plata", "mar del plata", "bahia blanca", "tandil",
                     "quilmes", "lanus", "avellaneda", "moron", "san isidro",
                     "vicente lopez", "tigre", "pilar", "lomas de zamora",
                     "san martin", "san justo", "la matanza", "hurlingham",
                     "ituzaingo", "banfield", "adrogue", "olivos", "martinez",
                     "palermo", "villa crespo", "colegiales", "belgrano",
                     "nunez", "almagro", "san telmo", "recoleta", "caballito",
                     "chacarita", "villa urquiza", "flores", "boedo", "balvanera",
                     "monserrat", "retiro", "puerto madero", "la boca",
                     "pergamino", "junin", "necochea", "olavarria", "zarate",
                     "campana", "lujan", "merlo", "moreno", "escobar",
                     "san nicolas", "azul", "chivilcoy", "villa gesell",
                     "pinamar", "tres arroyos", "san fernando", "berazategui",
                     "florencio varela", "ezeiza", "ramos mejia", "haedo",
                     "castelar", "temperley", "bernal", "gba", "conurbano"],
    "Córdoba": ["cordoba", "villa carlos paz", "rio cuarto", "villa maria",
                "alta gracia", "jesus maria", "cosquin", "la falda",
                "san francisco", "rio tercero", "villa allende", "unquillo",
                "mendiolaza", "bell ville", "marcos juarez", "la cumbre",
                "capilla del monte", "mina clavero", "villa general belgrano",
                "arroyito", "laboulaye", "deán funes", "dean funes",
                "villa dolores", "rio ceballos", "salsipuedes", "malagueno"],
    "Santa Fe": ["santa fe", "rosario", "rafaela", "venado tuerto",
                 "reconquista", "santo tome", "funes", "villa gobernador galvez",
                 "san lorenzo", "esperanza", "casilda", "firmat", "canada de gomez",
                 "granadero baigorria", "roldan", "perez", "sunchales",
                 "san justo santa fe", "villa constitucion", "rufino",
                 "gálvez", "galvez", "las parejas", "armstrong",
                 "san jeronimo norte", "ataliva", "humboldt", "san carlos centro",
                 "coronda", "helvecia", "san javier", "vera", "avellaneda santa fe"],
}


_OTRAS = [
    "san luis", "potrero de los funes", "merlo san luis", "mendoza", "san juan",
    "la rioja", "catamarca", "tucuman", "salta", "jujuy", "santiago del estero",
    "chaco", "resistencia", "formosa", "corrientes", "misiones", "posadas",
    "entre rios", "parana", "concordia", "gualeguaychu", "la pampa",
    "santa rosa la pampa", "neuquen", "rio negro", "bariloche", "chubut",
    "lago puelo", "el bolson", "puerto madryn", "trelew", "comodoro rivadavia",
    "santa cruz", "tierra del fuego", "ushuaia", "uruguay", "montevideo",
    "punta del este", "chile", "santiago de chile", "paraguay", "asuncion",
]


def provincia_de(*textos):
    """Devuelve 'Buenos Aires' / 'Córdoba' / 'Santa Fe' o None.

    Busca primero el nombre de la provincia explícito y después ciudades
    conocidas. Se le pasan ciudad, provincia, dirección, nombre del lugar...
    """
    t = " | ".join(sin_acentos(x) for x in textos if x)
    if not t:
        return None
    # Las calles no ubican: "Av. San Martín 902" o "Av. Córdoba 1500".
    t = re.sub(r"\b(av|avda|avenida|calle|bv|bvd|boulevard|bulevar|pasaje|pje|ruta)"
               r"\.?\s+[a-z .'-]{2,40}?\s*\d+", " ", t)
    # Otra provincia o ciudad de afuera nombrada: no es de las nuestras.
    # ("Corrientes 1660" o "Mendoza 2500" son calles: sin número detrás.)
    if re.search(r"\b(" + "|".join(_OTRAS) + r")\b(?!\s*\d)", t):
        return None
    # Provincia explícita (Santa Fe y Córdoba antes que Buenos Aires porque
    # "Buenos Aires" aparece en direcciones como "Av. Buenos Aires 123").
    if re.search(r"\bsanta fe\b", t) and "av. santa fe" not in t and "avenida santa fe" not in t:
        return "Santa Fe"
    if re.search(r"\bcordoba\b", t) and "av. cordoba" not in t and "avenida cordoba" not in t:
        return "Córdoba"
    # Córdoba y Santa Fe primero: barrios de CABA como "Belgrano" o
    # "San Martín" aparecen dentro de nombres de ciudades de esas provincias.
    for prov in ("Córdoba", "Santa Fe", "Buenos Aires"):
        ciudades = _CIUDADES[prov]
        for c in ciudades:
            if re.search(r"\b" + re.escape(c) + r"\b", t):
                return prov
    return None


def evento(portal, titulo, fecha, url, lugar=None, ciudad=None,
           provincia=None, imagen=None, precio=None, categoria=None):
    """Arma el registro común.

    fecha: 'AAAA-MM-DD' o 'AAAA-MM-DDTHH:MM' (hora local de Argentina).
    provincia: una de PROVINCIAS; si viene None se infiere de ciudad/lugar.
    """
    if provincia not in PROVINCIAS:
        provincia = provincia_de(provincia, ciudad, lugar)
    return {
        "portal": portal,
        "titulo": re.sub(r"\s+", " ", (titulo or "")).strip(),
        "fecha": fecha,
        "lugar": (lugar or "").strip() or None,
        "ciudad": (ciudad or "").strip() or None,
        "provincia": provincia,
        "url": url,
        "imagen": imagen,
        "precio": precio,
        "categoria": categoria,
    }
