"""Lee todos los portales y regenera docs/eventos.json.

Uso:  python actualizar.py            (todos los portales)
      python actualizar.py ticketek   (solo los indicados; el resto queda como estaba)

Si un portal falla, se conservan sus eventos de la corrida anterior y en el
JSON queda marcado el error, para que la página avise.
"""
import importlib
import json
import pkgutil
import re
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

import scrapers
from scrapers.base import PROVINCIAS, sin_acentos

RAIZ = Path(__file__).resolve().parent
SALIDA = RAIZ / "docs" / "eventos.json"
AR = timezone(timedelta(hours=-3))


def modulos():
    for m in pkgutil.iter_modules(scrapers.__path__):
        if m.name != "base" and not m.name.startswith("_"):
            yield m.name


def clave(ev):
    """Mismo show en dos portales: título normalizado + día + provincia."""
    t = sin_acentos(ev["titulo"])
    t = re.sub(r"\b(en|la|el|los|las|de|del|y|tour|gira|concierto|recital|show|"
               r"en vivo|live|20\d\d)\b", " ", t)
    t = re.sub(r"[^a-z0-9]+", "", t)
    return (t[:40], (ev["fecha"] or "")[:10], ev["provincia"])


def anterior():
    try:
        return json.loads(SALIDA.read_text(encoding="utf-8"))
    except Exception:
        return {"eventos": [], "portales": {}}


def main(solo):
    previo = anterior()
    ahora = datetime.now(AR)
    hoy = ahora.strftime("%Y-%m-%d")
    estado = dict(previo.get("portales", {}))
    crudos = []  # (modulo, evento)

    # Eventos anteriores, separados por módulo, por si hay que reusarlos.
    previos_por_mod = {}
    for ev in previo.get("eventos", []):
        for e in ev.get("enlaces", []):
            previos_por_mod.setdefault(e["modulo"], []).append(
                dict(ev, portal=e["portal"], url=e["url"], enlaces=None))

    for nombre in modulos():
        if solo and nombre not in solo:
            crudos += [(nombre, e) for e in previos_por_mod.get(nombre, [])]
            continue
        t0 = time.time()
        try:
            mod = importlib.import_module(f"scrapers.{nombre}")
            evs = [e for e in mod.obtener()
                   if e.get("fecha") and e.get("provincia") in PROVINCIAS]
            crudos += [(nombre, e) for e in evs]
            estado[nombre] = {"portal": mod.PORTAL, "ok": True,
                              "cantidad": len(evs), "error": None,
                              "ultima_ok": ahora.isoformat(timespec="minutes"),
                              "segundos": round(time.time() - t0)}
            print(f"{nombre}: {len(evs)} eventos ({time.time() - t0:.0f}s)")
        except Exception as ex:
            viejos = previos_por_mod.get(nombre, [])
            crudos += [(nombre, e) for e in viejos]
            st = estado.get(nombre, {})
            estado[nombre] = {"portal": st.get("portal", nombre), "ok": False,
                              "cantidad": len(viejos),
                              "error": f"{type(ex).__name__}: {ex}"[:300],
                              "ultima_ok": st.get("ultima_ok"),
                              "segundos": round(time.time() - t0)}
            print(f"{nombre}: ERROR {ex}", file=sys.stderr)
            traceback.print_exc()

    # Unificar: un registro por show, con los links de cada portal.
    unidos = {}
    for mod, ev in crudos:
        if (ev["fecha"] or "")[:10] < hoy:
            continue
        k = clave(ev)
        enlace = {"portal": ev["portal"], "modulo": mod, "url": ev["url"],
                  "precio": ev.get("precio")}
        if k in unidos:
            u = unidos[k]
            if all(e["url"] != ev["url"] for e in u["enlaces"]):
                u["enlaces"].append(enlace)
            for campo in ("lugar", "ciudad", "imagen", "categoria"):
                u[campo] = u[campo] or ev.get(campo)
            if len(ev["fecha"]) > len(u["fecha"]):
                u["fecha"] = ev["fecha"]  # la que trae hora
        else:
            unidos[k] = {
                "titulo": ev["titulo"], "fecha": ev["fecha"],
                "lugar": ev.get("lugar"), "ciudad": ev.get("ciudad"),
                "provincia": ev["provincia"], "imagen": ev.get("imagen"),
                "categoria": ev.get("categoria"), "enlaces": [enlace],
            }

    eventos = sorted(unidos.values(), key=lambda e: (e["fecha"], e["titulo"]))
    SALIDA.parent.mkdir(exist_ok=True)
    SALIDA.write_text(json.dumps({
        "generado": ahora.isoformat(timespec="minutes"),
        "portales": estado,
        "eventos": eventos,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Total: {len(eventos)} shows -> {SALIDA}")


if __name__ == "__main__":
    main(set(sys.argv[1:]))
