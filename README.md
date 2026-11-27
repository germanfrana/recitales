# Recitales

Página que reúne los recitales de Buenos Aires, Córdoba y Santa Fe publicados en los
principales portales de entradas. GitHub la actualiza sola a las 6 y a las 18 h.

- `scrapers/` — un lector por portal (`base.py` es el formato común).
- `actualizar.py` — corre todos los lectores y regenera `docs/eventos.json`.
- `docs/index.html` — la página (lee `eventos.json`).
- `.github/workflows/actualizar.yml` — la tarea programada de GitHub.

## Probar en la PC

```
pip install -r requirements.txt
python actualizar.py
python -m http.server 8000 -d docs
```

y abrir http://localhost:8000.

## Si un portal deja de andar

En el pie de la página ese portal aparece en naranja ("sin leer desde …") y se siguen
mostrando sus últimos eventos leídos. El detalle del error está en la pestaña
**Actions** del repositorio. Hay que ajustar `scrapers/<portal>.py`; para probar solo ese:
`python actualizar.py <portal>`.
