"""Builders of the generic content a dashboard section returns.

The frontend renders these blocks without knowing which section they come
from, so a section (including one added by another module) only has to
return them:

- "cards": KPI tiles;
- "table": rows x columns, with per-cell drill-down and alerts;
- "chart": bars and lines sharing the same labels.

A value is always sent with its type, so that the frontend formats it
(amounts are never rounded here): "monetary" (with a currency id),
"integer", "float", "percent", "date" (ISO string), "days" or "text".

A drill-down is a {"key": str, "params": dict} reference, sent back as is
to account.treasury.dashboard.get_drilldown() when clicked.
"""
from odoo import fields

ALERT_LEVELS = ("info", "warning", "danger")


def value(raw, value_type="text", currency=None, alert=None, drilldown=None, note=None, count=None):
    """One displayable value (a card's figure or a table cell). ``count``
    is an optional number of items shown next to it (e.g. "(3)")."""
    if value_type == "date" and raw:
        raw = fields.Date.to_string(raw)
    return {
        "value": raw,
        "type": value_type,
        "currency_id": currency.id if currency else False,
        "alert": alert or False,
        "drilldown": drilldown or False,
        "note": note or False,
        "count": count if count is not None else False,
    }


def money(amount, currency, **kwargs):
    return value(amount, "monetary", currency=currency, **kwargs)


def drilldown(key, **params):
    return {"key": key, "params": params}


def card(title, main, secondary=None, alert=None):
    """A KPI tile: ``main`` and ``secondary`` are value() dicts."""
    return {"title": str(title), "main": main, "secondary": secondary or False, "alert": alert or False}


def cards_block(items, title=None):
    return {"type": "cards", "title": str(title) if title else False, "items": items}


def column(key, label, value_type="text"):
    return {"key": key, "label": str(label), "type": value_type}


def row(key, cells, style=None, alert=None):
    """A table row. ``cells`` maps column keys to value() dicts; ``style`` is
    "total", "subtotal" or "muted"."""
    return {"key": key, "cells": cells, "style": style or False, "alert": alert or False}


def table_block(columns, rows, title=None, empty_message=None, note=None):
    return {
        "type": "table",
        "title": str(title) if title else False,
        "columns": columns,
        "rows": rows,
        "empty_message": str(empty_message) if empty_message else False,
        "note": str(note) if note else False,
    }


def chart_block(labels, series, title=None, currency=None, zero_line=True):
    """``series``: [{"label", "kind": "bar" | "line", "values": [...]}]."""
    return {
        "type": "chart",
        "title": str(title) if title else False,
        "labels": [str(label) for label in labels],
        "series": [{**serie, "label": str(serie["label"])} for serie in series],
        "currency_id": currency.id if currency else False,
        "zero_line": zero_line,
    }


def alert(level, message):
    assert level in ALERT_LEVELS
    return {"level": level, "message": str(message)}
