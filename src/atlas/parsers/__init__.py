"""Parsers for various legal document formats."""

from atlas.parsers.uslm import USLMParser

# State parsers - imported conditionally to avoid import errors if API keys not set
try:
    from atlas.parsers.ny_laws import (
        NY_LAW_CODES,
        NYLegislationClient,
        NYStateCitation,
        download_ny_law,
    )
except ImportError:
    NY_LAW_CODES = {}
    NYLegislationClient = None  # type: ignore[misc, assignment]
    NYStateCitation = None  # type: ignore[misc, assignment]
    download_ny_law = None  # type: ignore[misc, assignment]

__all__ = [
    "USLMParser",
    "NY_LAW_CODES",
    "NYLegislationClient",
    "NYStateCitation",
    "download_ny_law",
]
