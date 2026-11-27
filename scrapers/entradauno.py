"""EntradaUno: cartelera completa en un JSON público (S3) que usa la web.

La URL sale de VUE_APP_URL_CARTELERA_JSON en el JS de www.entradauno.com
(el 12 es el canal de EntradaUno). Una sola petición trae espectáculos,
funciones y establecimientos.
"""
from datetime import date

from scrapers import base

PORTAL = "EntradaUno"

CARTELERA = ("https://s3.sa-east-1.amazonaws.com/contenido.general.entradauno/"
             "cache/12/cartelera.json")
CAT_MUSICA = 100
# idProvincia de los establecimientos (los que vienen en 0 se infieren por zona).
_PROV_ID = {1: "Buenos Aires", 25: "Buenos Aires", 5: "Córdoba",
            20: "Santa Fe", 24: "Santa Fe"}
MAX_FUNCIONES = 40


def _imagen(e):
    for k in ("cImagenLanding", "cImagenBannerVertical", "cImagenBanner",
              "cImagenEquityThumb"):
        if e.get(k):
            return e[k]
    for im in e.get("listaImagen") or []:
        if im.get("cUri"):
            return im["cUri"]
    return None


def obtener():
    r = base.get(CARTELERA)
    r.encoding = "utf-8"
    c = r.json()["oData"]["oCartelera"]
    estab = {e["idEstablecimiento"]: e for e in c.get("listaEstablecimiento") or []}
    hoy = date.today().isoformat()
    salida, vistos = [], set()
    for e in c.get("listaEspectaculoCartel") or []:
        if CAT_MUSICA not in (e.get("listaIdEspectaculoCartelCategoria") or []):
            continue
        titulo = e.get("cNombre") or ""
        # Los "Palcos VIP" son la misma función vendida aparte.
        if "palcos vip" in base.sin_acentos(titulo):
            continue
        url = (e.get("cWebUri") or "").strip() or \
            "https://www.entradauno.com/landing/" + e.get("cSeo", "")
        funciones = e.get("oFuncionLista") or []
        if not funciones and e.get("oFuncionMenor"):
            fm = e["oFuncionMenor"]
            funciones = [{"dFuncion": fm["oFuncionFecha"]["dFuncion"],
                          "idEstablecimiento": (e.get("listaIdEstablecimiento") or [0])[0]}]
        for f in funciones[:MAX_FUNCIONES]:
            d = (f.get("dFuncion") or "")[:16]
            if not d or d[:10] < hoy:
                continue
            est = estab.get(f.get("idEstablecimiento")) or \
                estab.get((e.get("listaIdEstablecimiento") or [0])[0]) or {}
            zona = est.get("cZona") or ""
            prov = _PROV_ID.get(est.get("idProvincia")) or \
                base.provincia_de(zona, est.get("cDomicilio"))
            if prov not in base.PROVINCIAS:
                continue
            clave = (titulo, d, est.get("idEstablecimiento"))
            if clave in vistos:
                continue
            vistos.add(clave)
            salida.append(base.evento(
                PORTAL, titulo, d, url,
                lugar=est.get("cNombre"),
                ciudad="CABA" if zona == "CABA" else zona,
                provincia=prov,
                imagen=_imagen(e),
                precio=e.get("fPrecioDesde") or None,
                categoria="Música"))
    return salida
