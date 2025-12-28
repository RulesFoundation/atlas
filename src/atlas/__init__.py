"""Cosilico Law Archive - Open source US statute text via API."""

from atlas.archive import Atlas
from atlas.models import Citation, SearchResult, Section, Subsection

__version__ = "0.1.0"
__all__ = ["Atlas", "Section", "Subsection", "Citation", "SearchResult"]
