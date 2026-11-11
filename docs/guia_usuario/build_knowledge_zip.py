"""Build the Dashboards user guide as a ZIP importable with Zinapsia's knowledge_transfer.

The guide is written as one HTML file per article in ``articulos/``. This
script packs them in the knowledge_transfer format (manifest.json + one
``articles/<key>/body.html`` per article, format_version 1) so the whole tree
can be imported in Knowledge > Transfer > Import.

Usage (no Odoo needed):
    python3 docs/guia_usuario/build_knowledge_zip.py
Output:
    docs/guia_usuario/guia_dashboards_knowledge.zip
"""

import hashlib
import json
import mimetypes
import pathlib
import re
import zipfile
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
SOURCE_DIR = HERE / "articulos"
IMAGE_DIR = HERE / "img"
# Images are referenced in the articles as src="../img/<file>" (so the HTML
# previews in a browser) and shipped as knowledge_transfer attachments.
IMAGE_SRC = re.compile(r'src="\.\./img/([^"]+)"')
OUTPUT = HERE / "guia_dashboards_knowledge.zip"
ODOO_SERIES = "19.0"
FORMAT_VERSION = 1

# (key, parent key, article name, icon, source file). Parents must come
# before their children; the order is the order shown in Knowledge.
ARTICLES = [
    ("guia", None, "Dashboards – Guía de implementación", "📊", "00_inicio.html"),
    ("puesta_en_marcha", "guia", "Puesta en marcha", "🚀", "01_puesta_en_marcha.html"),
    ("resultados", "guia", "Estado de resultados de gestión", "📈", "10_resultados.html"),
    ("resultados_configuracion", "resultados", "Configuración del estado de resultados de gestión", "⚙️", "11_resultados_configuracion.html"),
    ("resultados_tablero", "resultados", "Qué muestra el estado de resultados de gestión", "🔎", "12_resultados_tablero.html"),
    ("cobranzas", "guia", "Cobranzas", "💰", "20_cobranzas.html"),
    ("cobranzas_configuracion", "cobranzas", "Configuración de cobranzas", "⚙️", "21_cobranzas_configuracion.html"),
    ("cobranzas_tablero", "cobranzas", "Qué muestra el tablero de cobranzas", "🔎", "22_cobranzas_tablero.html"),
    ("tesoreria", "guia", "Tesorería", "🏦", "30_tesoreria.html"),
    ("tesoreria_configuracion", "tesoreria", "Configuración de tesorería", "⚙️", "31_tesoreria_configuracion.html"),
    ("tesoreria_tablero", "tesoreria", "Qué muestra el tablero de tesorería", "🔎", "32_tesoreria_tablero.html"),
    ("faq", "guia", "Preguntas frecuentes", "❓", "40_faq.html"),
    ("novedades", "guia", "Novedades por versión", "🆕", "50_novedades.html"),
]


def build():
    manifest_articles = []
    bodies = {}
    attachments = []
    payloads = {}
    index_by_image = {}
    sequence_by_parent = {}
    for key, parent_key, name, icon, filename in ARTICLES:
        body = (SOURCE_DIR / filename).read_text(encoding="utf-8").strip()
        article_attachments = []

        def to_marker(match, key=key, article_attachments=article_attachments):
            name = match.group(1)
            if name not in index_by_image:
                raw = (IMAGE_DIR / name).read_bytes()
                index = len(attachments) + 1
                index_by_image[name] = index
                file_path = f"attachments/{index}__{name}"
                payloads[file_path] = raw
                attachments.append(
                    {
                        "index": index,
                        "name": name,
                        "mimetype": mimetypes.guess_type(name)[0] or "application/octet-stream",
                        "checksum": hashlib.sha1(raw).hexdigest(),
                        "type": "binary",
                        "article_key": key,
                        "articles": [key],
                        "file": file_path,
                    }
                )
            index = index_by_image[name]
            if index not in article_attachments:
                article_attachments.append(index)
            return f'src="kt-attachment:{index}:image"'

        body = IMAGE_SRC.sub(to_marker, body)
        body_path = f"articles/{key}/body.html"
        bodies[body_path] = body
        sequence = sequence_by_parent.get(parent_key, 0) + 1
        sequence_by_parent[parent_key] = sequence
        manifest_articles.append(
            {
                "key": key,
                "parent_key": parent_key,
                "sequence": sequence,
                "name": name,
                "icon": icon,
                "full_width": False,
                "is_article_item": False,
                "body": body_path,
                "cover": None,
                "stage_key": None,
                "stages": [],
                "properties_definition": [],
                "properties": {},
                "attachments": article_attachments,
            }
        )
    manifest = {
        "format_version": FORMAT_VERSION,
        "odoo_series": ODOO_SERIES,
        "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "articles": manifest_articles,
        "attachments": attachments,
        "warnings": [],
    }
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        for path, body in bodies.items():
            archive.writestr(path, body)
        for path, raw in payloads.items():
            archive.writestr(path, raw)
    return OUTPUT, len(manifest_articles)


if __name__ == "__main__":
    output, count = build()
    print(f"{output} ({count} articles)")
