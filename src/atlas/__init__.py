"""Cosilico Arch - Foundational archive for all raw government source files."""

from atlas.archive import Arch

# Legacy USC models (still used internally)
from atlas.models import Citation, SearchResult, Section, Subsection

# Unified statute model (new architecture)
from atlas.models_statute import (
    JURISDICTIONS,
    JurisdictionInfo,
    JurisdictionType,
    Statute,
    StatuteSearchResult,
    StatuteSubsection,
)

__version__ = "0.1.0"
__all__ = [
    # Main archive class
    "Arch",
    # Legacy USC models
    "Section",
    "Subsection",
    "Citation",
    "SearchResult",
    # Unified statute model
    "Statute",
    "StatuteSubsection",
    "StatuteSearchResult",
    "JurisdictionInfo",
    "JurisdictionType",
    "JURISDICTIONS",
]
