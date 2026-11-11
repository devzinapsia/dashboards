# Guía de implementación para usuarios — Dashboards

Guía para los usuarios finales de los tableros de este repositorio
(Estado de resultados de gestión, Cobranzas y Tesorería), en español,
armada para importarse en **Knowledge** (Odoo Enterprise) con el módulo
`knowledge_transfer` de Zinapsia (repo `devzinapsia/knowledge`).

Está fuera de los módulos porque cubre todos los tableros a la vez. No es
un módulo de Odoo (no tiene `__manifest__.py`), así que Odoo y odoo.sh la
ignoran.

Se actualiza **en cada versión de los módulos** que cambie algo visible
para el usuario: se edita el artículo que corresponde, se agrega la
entrada en `articulos/50_novedades.html` (y las versiones en
`articulos/00_inicio.html`) y se regenera el ZIP.

## Estructura

- `articulos/*.html`: un archivo por artículo (fuente editable). HTML simple
  (títulos, párrafos, listas, tablas y avisos `alert`) que Knowledge muestra
  tal cual.
- `build_knowledge_zip.py`: arma el ZIP importable. El árbol de artículos
  (nombres, íconos, orden, padre) está definido en la lista `ARTICLES` del
  script.
- `guia_dashboards_knowledge.zip`: el ZIP generado, listo para importar.
- `img/`: capturas de pantalla.

Árbol:

```
Dashboards – Guía de implementación
├── Puesta en marcha
├── Estado de resultados de gestión
│   ├── Configuración del estado de resultados de gestión
│   └── Qué muestra el estado de resultados de gestión
├── Cobranzas
│   ├── Configuración de cobranzas
│   └── Qué muestra el tablero de cobranzas
├── Tesorería
│   ├── Configuración de tesorería
│   └── Qué muestra el tablero de tesorería
├── Preguntas frecuentes
└── Novedades por versión
```

## Imágenes

Se guardan en `img/` y se usan en el artículo como
`<img src="../img/<archivo>.png" alt="..."/>` (así se ven al abrir el HTML
en un navegador). El script las empaqueta como adjuntos de
`knowledge_transfer` (`attachments/` + marca `kt-attachment:N:image`) y al
importar quedan como adjuntos del artículo. Una imagen referenciada que no
existe en `img/` hace fallar el script.

## Regenerar el ZIP

```bash
python3 docs/guia_usuario/build_knowledge_zip.py
```

## Importar en Knowledge

1. Instalar `knowledge_transfer` en la base (repo `devzinapsia/knowledge`).
2. **Artículos › Transferencia › Importar** (la app Knowledge se llama
   *Artículos* en español), subir el ZIP y pulsar *Importar*.
3. El árbol queda en la sección privada de quien importa, dentro de
   "Artículos importados Zinapsia", con la fecha y hora agregadas al nombre
   del artículo raíz. Moverlo al *Espacio de trabajo*, renombrarlo si hace falta y
   compartirlo con los usuarios de los tableros.

Sin `knowledge_transfer`, también se puede crear cada artículo a mano en
Knowledge y pegar el contenido del HTML correspondiente abierto en un
navegador.
