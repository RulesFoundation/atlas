"""Source adapters for fetching statutes from various jurisdictions."""

from atlas.sources.base import StatuteSource, SourceConfig
from atlas.sources.uslm import USLMSource
from atlas.sources.html import HTMLSource
from atlas.sources.api import APISource

__all__ = [
    "StatuteSource",
    "SourceConfig",
    "USLMSource",
    "HTMLSource",
    "APISource",
]
