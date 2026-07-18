# Preparador Inteligente de Materiales para Winmaker

Aplicación web local con identidad DIVANNI para transformar una Orden de Producción digital de Winmaker en:

- listado de vidrios sin consolidar filas;
- listado consolidado de accesorios;
- exportaciones independientes por listado en Excel, CSV y PDF vertical;
- historial básico y trazabilidad de modificaciones.

## Requisitos

- Python 3.9 o superior.
- PDF digital exportado directamente desde Winmaker.

No requiere PostgreSQL, servicios en la nube ni conexión con Winmaker.

## Instalación

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Ejecución

```bash
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abrir `http://127.0.0.1:8000`.

La base SQLite y los PDFs cargados se guardan dentro de `data/`, carpeta excluida de Git.

## Flujo

1. Ingresar manualmente el cliente.
2. Cargar el PDF digital original de Winmaker.
3. Revisar cada tipología.
4. Modificar, excluir o agregar vidrios, telas y accesorios.
5. Confirmar todas las tipologías.
6. Resolver conflictos de descripción, si existen.
7. Finalizar y exportar la pestaña activa.

Los vidrios y las telas son editables. Cada fila original se mantiene una vez con su cantidad original; no se expanden ni se consolidan filas. Cantidad, medida, descripción, exclusión y observaciones conservan trazabilidad.

## Pruebas de regresión

Con los tres PDFs de muestra disponibles en `~/Downloads`:

```bash
PYTHONPYCACHEPREFIX=/tmp/lector-pycache .venv/bin/python -m unittest discover -s tests -v
```

Los valores esperados son:

| PDF | Páginas | Filas de vidrio | Filas de accesorios |
|---|---:|---:|---:|
| Solsona | 11 | 14 (incluye 4 telas) | 121 |
| Torres | 10 | 16 | 170 |
| Lenan | 15 | 31 (incluye 1 tela) | 251 |

## Arquitectura

- `app/parser.py`: motor determinista PDF → JSON.
- `app/services.py`: reglas de revisión, trazabilidad, consolidación y exportaciones.
- `app/database.py`: persistencia SQLite mediante SQLAlchemy.
- `app/main.py`: API web.
- `app/static/`: interfaz responsive.
- `tests/`: corpus de regresión.

La lógica de negocio no usa características exclusivas de SQLite, facilitando una migración futura a PostgreSQL.
