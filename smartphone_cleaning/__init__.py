"""Smartphone dataset cleaning.

Decomposes the noisy composite attribute strings in ``smart phone dataset.xlsx``
(e.g. ``"50 MP + 8 MP + 2 MP Triple Rear & 16 MP Front Camera"``) into clean,
structured numeric features so the distance and conjoint pipelines no longer
ingest free text. Extraction is content-based (by pattern, not column position),
which also corrects the column-shifted feature-phone rows in the raw workbook.
"""

from __future__ import annotations

__all__ = ["parsers", "extract", "clean"]
