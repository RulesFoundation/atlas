"""Parser for New York State laws via the Open Legislation API.

NY Senate provides a free REST API at legislation.nysenate.gov for accessing
all consolidated NYS laws including Tax Law, Social Services Law, etc.

API Documentation: https://legislation.nysenate.gov/static/docs/html/laws.html

Requires a free API key from legislation.nysenate.gov (set as NY_LEGISLATION_API_KEY
environment variable).
"""

import os
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from arch.models import Citation, Section, Subsection

BASE_URL = "https://legislation.nysenate.gov/api/3"

# Common NY law codes for tax/benefit programs
NY_LAW_CODES = {
    "TAX": "Tax Law",
    "SOS": "Social Services Law",
    "EDN": "Education Law",
    "LAB": "Labor Law",
    "EXC": "Executive Law",
    "PBH": "Public Health Law",
    "INS": "Insurance Law",
}


@dataclass
class NYLawInfo:
    """Information about a NY law book."""

    law_id: str
    chapter: str
    name: str
    law_type: str


@dataclass
class NYSection:
    """A section from NY law."""

    law_id: str
    location_id: str
    title: str
    text: str
    doc_type: str
    doc_level_id: str
    active_date: str | None = None


class NYLegislationAPIError(Exception):
    """Error from the NY Legislation API."""

    def __init__(self, message: str, error_code: int | None = None):
        super().__init__(message)
        self.error_code = error_code


class NYLegislationClient:
    """Client for the NY Open Legislation API.

    Example:
        >>> client = NYLegislationClient()  # Uses NY_LEGISLATION_API_KEY env var
        >>> laws = client.get_law_ids()
        >>> tax_tree = client.get_law_tree("TAX")
        >>> section = client.get_section("TAX", "606")
    """

    def __init__(self, api_key: str | None = None, rate_limit_delay: float = 0.2):
        """Initialize the NY Legislation API client.

        Args:
            api_key: API key (defaults to NY_LEGISLATION_API_KEY env var)
            rate_limit_delay: Seconds to wait between requests (default 0.2)
        """
        self.api_key = api_key or os.environ.get("NY_LEGISLATION_API_KEY")
        if not self.api_key:
            raise ValueError(
                "NY API key required. Set NY_LEGISLATION_API_KEY environment variable "
                "or pass api_key parameter. Get a free key at legislation.nysenate.gov"
            )
        self.rate_limit_delay = rate_limit_delay
        self._last_request_time = 0.0
        self.client = httpx.Client(
            base_url=BASE_URL,
            params={"key": self.api_key},
            timeout=60.0,
        )

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict:
        """Make a GET request to the API."""
        self._rate_limit()
        response = self.client.get(endpoint, params=params or {})
        response.raise_for_status()
        data = response.json()

        if not data.get("success", False):
            raise NYLegislationAPIError(
                data.get("message", "Unknown API error"),
                data.get("errorCode"),
            )

        return data.get("result", {})

    def get_law_ids(self) -> list[NYLawInfo]:
        """List all available law codes.

        Returns:
            List of NYLawInfo with law_id, name, etc.
        """
        result = self._get("/laws", {"limit": 200})
        items = result.get("items", [])

        return [
            NYLawInfo(
                law_id=item.get("lawId", ""),
                chapter=item.get("chapter", ""),
                name=item.get("name", ""),
                law_type=item.get("lawType", ""),
            )
            for item in items
        ]

    def get_law_tree(self, law_id: str, full: bool = False) -> dict:
        """Get the hierarchical structure of a law.

        Args:
            law_id: Law code (e.g., "TAX", "SOS")
            full: If True, include full text in response

        Returns:
            Dict with law structure including articles and sections
        """
        params = {}
        if full:
            params["full"] = "true"
        return self._get(f"/laws/{law_id}", params)

    def get_section(
        self,
        law_id: str,
        location_id: str,
        date_str: str | None = None,
    ) -> NYSection:
        """Get a specific section.

        Args:
            law_id: Law code (e.g., "TAX")
            location_id: Section location (e.g., "606", "A22S606")
            date_str: ISO date for historical version (optional)

        Returns:
            NYSection with full text
        """
        # Trailing slash is important per API docs
        endpoint = f"/laws/{law_id}/{location_id}/"
        params = {}
        if date_str:
            params["date"] = date_str

        result = self._get(endpoint, params)

        return NYSection(
            law_id=result.get("lawId", law_id),
            location_id=result.get("locationId", location_id),
            title=result.get("title", ""),
            text=result.get("text", ""),
            doc_type=result.get("docType", ""),
            doc_level_id=result.get("docLevelId", ""),
            active_date=result.get("activeDate"),
        )

    def iter_sections(self, law_id: str) -> Iterator[NYSection]:
        """Iterate over all sections in a law.

        Args:
            law_id: Law code (e.g., "TAX")

        Yields:
            NYSection for each section in the law
        """
        # Get the full law tree with text
        tree = self.get_law_tree(law_id, full=True)

        # Process the document tree recursively
        yield from self._iter_tree_sections(tree, law_id)

    def _iter_tree_sections(self, node: dict, law_id: str) -> Iterator[NYSection]:
        """Recursively iterate through law tree to find sections."""
        # Handle both top-level result dict and nested document nodes
        if "documents" in node and "info" in node:
            # Top-level result - start from documents
            node = node["documents"]

        doc_type = node.get("docType", "")

        # Sections are the leaf nodes we want
        if doc_type == "SECTION":
            yield NYSection(
                law_id=law_id,
                location_id=node.get("locationId", ""),
                title=node.get("title", ""),
                text=node.get("text", ""),
                doc_type=doc_type,
                doc_level_id=node.get("docLevelId", ""),
                active_date=node.get("activeDate"),
            )

        # Recurse into documents dict - API uses {items: [...], size: N} structure
        documents = node.get("documents", {})
        if isinstance(documents, dict):
            items = documents.get("items", [])
            for child in items:
                yield from self._iter_tree_sections(child, law_id)

    def search(self, term: str, law_id: str | None = None, limit: int = 100) -> list[dict]:
        """Full-text search across laws.

        Args:
            term: Search term
            law_id: Optional law code to limit search
            limit: Maximum results

        Returns:
            List of search result dicts
        """
        endpoint = f"/laws/{law_id}/search" if law_id else "/laws/search"
        result = self._get(endpoint, {"term": term, "limit": limit})
        return result.get("items", [])

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()

    def __enter__(self) -> "NYLegislationClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class NYStateCitation:
    """Citation for NY state laws.

    Format: "NY {Law} Law {symbol} {section}" e.g., "NY Tax Law {symbol} 606"
    """

    def __init__(self, law_id: str, section: str, subsection: str | None = None):
        self.law_id = law_id
        self.section = section
        self.subsection = subsection

    @property
    def cite_string(self) -> str:
        """Return formatted citation string."""
        law_name = NY_LAW_CODES.get(self.law_id, f"{self.law_id} Law")
        base = f"NY {law_name} \u00a7 {self.section}"
        if self.subsection:
            parts = self.subsection.split("/")
            formatted = "".join(f"({p})" for p in parts)
            return f"{base}{formatted}"
        return base

    @property
    def path(self) -> str:
        """Return filesystem-style path."""
        if self.subsection:
            return f"state/ny/{self.law_id.lower()}/{self.section}/{self.subsection}"
        return f"state/ny/{self.law_id.lower()}/{self.section}"


def convert_to_section(ny_section: NYSection) -> Section:
    """Convert NY API section to Arch Section model.

    Args:
        ny_section: Section from NY API

    Returns:
        Arch Section model
    """
    law_name = NY_LAW_CODES.get(ny_section.law_id, f"{ny_section.law_id} Law")

    # Extract section number from location_id
    # Format varies: "606", "A22S606" (Article 22 Section 606), etc.
    section_num = _extract_section_number(ny_section.location_id)

    # Create citation - use a special title number for state laws
    # We use negative numbers or a state prefix scheme
    # For now, use 0 as a placeholder for state laws
    citation = Citation(
        title=0,  # State law indicator
        section=f"NY-{ny_section.law_id}-{section_num}",
    )

    # Parse subsections from text if present
    subsections = _parse_subsections(ny_section.text)

    return Section(
        citation=citation,
        title_name=f"New York {law_name}",
        section_title=ny_section.title or f"Section {section_num}",
        text=ny_section.text,
        subsections=subsections,
        source_url=f"https://legislation.nysenate.gov/api/3/laws/{ny_section.law_id}/{ny_section.location_id}/",
        retrieved_at=date.today(),
        uslm_id=f"ny/{ny_section.law_id}/{ny_section.location_id}",
    )


def _extract_section_number(location_id: str) -> str:
    """Extract section number from location ID.

    Examples:
        "606" -> "606"
        "A22S606" -> "606"
        "A1S1" -> "1"
    """
    if not location_id:
        return ""

    # If it contains "S" followed by a number, extract that
    if "S" in location_id:
        parts = location_id.split("S")
        if len(parts) > 1 and parts[-1]:
            return parts[-1]

    # Otherwise return as-is (simple section numbers)
    return location_id


def _parse_subsections(text: str) -> list[Subsection]:
    """Parse subsections from NY law text.

    NY laws typically use formats like:
    1. Numbered paragraphs
    (a) Lettered paragraphs
    (i) Roman numeral sub-paragraphs

    For now, returns empty list - full parsing would require
    sophisticated regex or NLP.
    """
    # TODO: Implement subsection parsing for NY laws
    # This is complex because NY law formatting varies significantly
    return []


def download_ny_law(
    law_id: str,
    api_key: str | None = None,
) -> Iterator[Section]:
    """Download all sections from a NY law.

    Args:
        law_id: Law code (e.g., "TAX", "SOS")
        api_key: Optional API key (uses env var if not provided)

    Yields:
        Section objects for each section in the law
    """
    with NYLegislationClient(api_key=api_key) as client:
        for ny_section in client.iter_sections(law_id):
            if ny_section.text:  # Skip empty sections
                yield convert_to_section(ny_section)
