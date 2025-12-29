"""Parser for Florida Statutes via web scraping.

Florida Legislature provides statutes at leg.state.fl.us/statutes. There is no
public API, so this parser scrapes the HTML pages.

Structure:
- Statutes are organized by Title (e.g., Title XIV: Taxation and Finance)
- Titles contain Chapters (e.g., Chapter 212: Tax on Sales, Use, and Other Transactions)
- Chapters contain Sections (e.g., 212.05: Sales, storage, use tax)

URL Patterns:
- Chapter index: index.cfm?App_mode=Display_Statute&URL=0200-0299/0212/0212ContentsIndex.html
- Section: index.cfm?App_mode=Display_Statute&URL=0200-0299/0212/Sections/0212.05.html
"""

import re
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date

import httpx
from bs4 import BeautifulSoup

from arch.models import Citation, Section, Subsection

BASE_URL = "https://leg.state.fl.us/statutes"

# Florida Statutes Title XIV: Taxation and Finance (Chapters 192-220)
# Key chapters for tax/benefit policy
FL_TAX_CHAPTERS: dict[int, str] = {
    192: "Taxation: General Provisions",
    193: "Assessments",
    194: "Administrative and Judicial Review of Property Taxes",
    195: "Property Assessment Administration and Finance",
    196: "Exemption",
    197: "Tax Collections, Sales, and Liens",
    198: "Estate Taxes",
    199: "Intangible Personal Property Taxes",
    200: "Determination of Millage",
    201: "Excise Tax on Documents",
    202: "Communications Services Tax Simplification Law",
    203: "Gross Receipts Taxes",
    205: "Local Business Taxes",
    206: "Motor and Other Fuel Taxes",
    207: "Tax on Operation of Commercial Motor Vehicles",
    210: "Tax on Tobacco Products",
    211: "Tax on Production of Oil and Gas and Severance of Solid Minerals",
    212: "Tax on Sales, Use, and Other Transactions",
    213: "State Revenue Laws: General Provisions",
    215: "Financial Matters: General Provisions",
    216: "Planning and Budgeting",
    217: "Surplus Property",
    218: "Financial Matters Pertaining to Political Subdivisions",
    219: "County Public Money, Handling by State and County",
    220: "Income Tax Code",
}

# Florida Statutes Title XXX: Social Welfare (Chapters 409-430)
FL_WELFARE_CHAPTERS: dict[int, str] = {
    409: "Social and Economic Assistance",
    410: "Adult Services",
    411: "Child and Family Programs",
    414: "Family Self-Sufficiency",
    415: "Adult Protective Services",
    420: "Housing",
    429: "Assisted Living Facilities",
    430: "Elderly Affairs",
}


@dataclass
class FLChapterInfo:
    """Information about a Florida Statutes chapter."""

    number: int
    title: str
    url_range: str  # e.g., "0200-0299" for chapters 200-299

    @property
    def padded_number(self) -> str:
        """Return zero-padded chapter number (e.g., '0212')."""
        return f"{self.number:04d}"

    @property
    def contents_url(self) -> str:
        """Return URL to chapter contents index."""
        return (
            f"{BASE_URL}/index.cfm?App_mode=Display_Statute"
            f"&URL={self.url_range}/{self.padded_number}/{self.padded_number}ContentsIndex.html"
        )


@dataclass
class FLSectionInfo:
    """Information about a Florida Statutes section."""

    number: str  # e.g., "212.05", "220.02"
    title: str
    chapter: int
    url: str


@dataclass
class FLSection:
    """A section from Florida Statutes with full content."""

    number: str
    title: str
    chapter: int
    chapter_title: str
    text: str
    html: str
    url: str
    subsections: list["FLSubsection"] = field(default_factory=list)


@dataclass
class FLSubsection:
    """A subsection within a Florida statute."""

    identifier: str  # e.g., "1", "a", "I"
    text: str
    children: list["FLSubsection"] = field(default_factory=list)


class FLStatutesError(Exception):
    """Error accessing Florida Statutes."""

    def __init__(self, message: str, url: str | None = None):
        super().__init__(message)
        self.url = url


class FLStatutesClient:
    """Client for scraping Florida Statutes.

    Example:
        >>> client = FLStatutesClient()
        >>> sections = client.get_chapter_sections(212)
        >>> section = client.get_section("212.05")
        >>> for sec in client.iter_chapter(212):
        ...     print(sec.number, sec.title)
    """

    def __init__(self, rate_limit_delay: float = 0.5, year: int | None = None):
        """Initialize the Florida Statutes client.

        Args:
            rate_limit_delay: Seconds to wait between requests (default 0.5)
            year: Statute year to fetch (default: current year)
        """
        self.rate_limit_delay = rate_limit_delay
        self.year = year or date.today().year
        self._last_request_time = 0.0
        self.client = httpx.Client(
            timeout=60.0,
            headers={
                "User-Agent": "Arch/1.0 (Statute Research; contact@cosilico.ai)"
            },
        )

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def _get(self, url: str) -> str:
        """Make a GET request and return HTML content."""
        self._rate_limit()
        response = self.client.get(url)
        response.raise_for_status()
        return response.text

    def _get_url_range(self, chapter: int) -> str:
        """Determine the URL range folder for a chapter number."""
        # Florida uses 100-chapter ranges: 0000-0099, 0100-0199, 0200-0299, etc.
        lower = (chapter // 100) * 100
        upper = lower + 99
        return f"{lower:04d}-{upper:04d}"

    def get_chapter_info(self, chapter: int) -> FLChapterInfo:
        """Get chapter info from known chapters or by probing.

        Args:
            chapter: Chapter number (e.g., 212)

        Returns:
            FLChapterInfo with chapter details
        """
        # Check known chapters first
        title = FL_TAX_CHAPTERS.get(chapter) or FL_WELFARE_CHAPTERS.get(chapter)
        if not title:
            title = f"Chapter {chapter}"

        return FLChapterInfo(
            number=chapter,
            title=title,
            url_range=self._get_url_range(chapter),
        )

    def get_chapter_sections(self, chapter: int) -> list[FLSectionInfo]:
        """Get list of all sections in a chapter.

        Args:
            chapter: Chapter number (e.g., 212)

        Returns:
            List of FLSectionInfo for each section in the chapter
        """
        info = self.get_chapter_info(chapter)
        html = self._get(info.contents_url)
        soup = BeautifulSoup(html, "html.parser")

        sections = []

        # Find section links - they follow pattern like "212.01", "212.02", etc.
        # Links are in format: Sections/0212.01.html
        section_pattern = re.compile(rf"Sections/{info.padded_number}\.(\d+[A-Za-z]?)\.html")

        for link in soup.find_all("a", href=section_pattern):
            href = link.get("href", "")
            match = section_pattern.search(href)
            if match:
                section_num = f"{chapter}.{match.group(1)}"
                # Get title from link text, cleaning up whitespace
                title = link.get_text(strip=True)
                # Title often includes section number prefix, remove it
                title = re.sub(rf"^{re.escape(section_num)}\s*[-:.]?\s*", "", title)

                # Build full URL
                section_url = (
                    f"{BASE_URL}/index.cfm?App_mode=Display_Statute"
                    f"&URL={info.url_range}/{info.padded_number}/Sections/{info.padded_number}.{match.group(1)}.html"
                )

                sections.append(
                    FLSectionInfo(
                        number=section_num,
                        title=title or f"Section {section_num}",
                        chapter=chapter,
                        url=section_url,
                    )
                )

        return sections

    def get_section(self, section_number: str) -> FLSection:
        """Get full content of a specific section.

        Args:
            section_number: Section number (e.g., "212.05", "220.02")

        Returns:
            FLSection with full text and metadata
        """
        # Parse chapter from section number
        chapter = int(section_number.split(".")[0])
        info = self.get_chapter_info(chapter)

        # Build URL - section numbers can include letters (e.g., 212.08, 212.0596)
        section_suffix = section_number.split(".", 1)[1] if "." in section_number else section_number
        url = (
            f"{BASE_URL}/index.cfm?App_mode=Display_Statute"
            f"&URL={info.url_range}/{info.padded_number}/Sections/{info.padded_number}.{section_suffix}.html"
        )

        html = self._get(url)
        return self._parse_section_page(html, section_number, chapter, info.title, url)

    def _parse_section_page(
        self,
        html: str,
        section_number: str,
        chapter: int,
        chapter_title: str,
        url: str,
    ) -> FLSection:
        """Parse a section page HTML into FLSection."""
        soup = BeautifulSoup(html, "html.parser")

        # Check for "cannot be found" error
        if "cannot be found" in html.lower():
            raise FLStatutesError(f"Section {section_number} not found", url)

        # Find the section title - usually in a heading or strong tag
        title = ""
        # Look for section header pattern like "212.05 Sales, storage, use tax.—"
        title_pattern = re.compile(rf"{re.escape(section_number)}\s+(.+?)\.?—")
        title_match = title_pattern.search(html)
        if title_match:
            title = title_match.group(1).strip()

        # Alternative: look in page title or heading
        if not title:
            h1 = soup.find("h1") or soup.find("h2")
            if h1:
                h1_text = h1.get_text(strip=True)
                title_match = title_pattern.search(h1_text)
                if title_match:
                    title = title_match.group(1).strip()
                else:
                    # Use full h1 text, removing section number prefix
                    title = re.sub(rf"^{re.escape(section_number)}\s*[-:.]?\s*", "", h1_text)

        # Get full text content
        # Florida statutes are typically in a main content area
        # Look for the statute text - often in a specific div or the main body
        content_div = soup.find("div", class_="Statute") or soup.find("div", id="statute")

        if content_div:
            text = content_div.get_text(separator="\n", strip=True)
            section_html = str(content_div)
        else:
            # Fall back to body text, trying to exclude navigation
            body = soup.find("body")
            if body:
                # Remove navigation elements
                for nav in body.find_all(["nav", "header", "footer", "script", "style"]):
                    nav.decompose()
                text = body.get_text(separator="\n", strip=True)
                section_html = str(body)
            else:
                text = soup.get_text(separator="\n", strip=True)
                section_html = html

        # Parse subsections
        subsections = self._parse_subsections(text)

        return FLSection(
            number=section_number,
            title=title or f"Section {section_number}",
            chapter=chapter,
            chapter_title=chapter_title,
            text=text,
            html=section_html,
            url=url,
            subsections=subsections,
        )

    def _parse_subsections(self, text: str) -> list[FLSubsection]:
        """Parse subsection structure from statute text.

        Florida statutes typically use:
        (1), (2), (3) - Primary divisions
        (a), (b), (c) - Secondary divisions
        1., 2., 3. - Tertiary divisions (sometimes)
        """
        # For now, return empty list - full parsing is complex
        # TODO: Implement hierarchical subsection parsing
        return []

    def iter_chapter(self, chapter: int) -> Iterator[FLSection]:
        """Iterate over all sections in a chapter.

        Args:
            chapter: Chapter number (e.g., 212)

        Yields:
            FLSection for each section in the chapter
        """
        sections = self.get_chapter_sections(chapter)
        for section_info in sections:
            try:
                yield self.get_section(section_info.number)
            except FLStatutesError as e:
                # Log but continue with other sections
                print(f"Warning: Could not fetch {section_info.number}: {e}")
                continue

    def iter_chapters(self, chapters: list[int] | None = None) -> Iterator[FLSection]:
        """Iterate over all sections in multiple chapters.

        Args:
            chapters: List of chapter numbers (default: all tax chapters)

        Yields:
            FLSection for each section
        """
        if chapters is None:
            chapters = list(FL_TAX_CHAPTERS.keys())

        for chapter in chapters:
            yield from self.iter_chapter(chapter)

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()

    def __enter__(self) -> "FLStatutesClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()


class FLStateCitation:
    """Citation for Florida state laws.

    Format: "Fla. Stat. section {section}" e.g., "Fla. Stat. section 212.05"
    """

    def __init__(self, section: str, subsection: str | None = None):
        self.section = section
        self.subsection = subsection

    @property
    def cite_string(self) -> str:
        """Return formatted citation string."""
        base = f"Fla. Stat. \u00a7 {self.section}"
        if self.subsection:
            parts = self.subsection.split("/")
            formatted = "".join(f"({p})" for p in parts)
            return f"{base}{formatted}"
        return base

    @property
    def path(self) -> str:
        """Return filesystem-style path."""
        chapter = self.section.split(".")[0]
        if self.subsection:
            return f"state/fl/{chapter}/{self.section}/{self.subsection}"
        return f"state/fl/{chapter}/{self.section}"

    @classmethod
    def from_string(cls, cite: str) -> "FLStateCitation":
        """Parse a citation string like 'Fla. Stat. section 212.05(1)(a)'.

        Handles formats:
        - Fla. Stat. section 212.05
        - Fla. Stat. section 212.05(1)
        - Fla. Stat. section 212.05(1)(a)
        - F.S. 212.05
        - section 212.05, F.S.
        """
        # Normalize the citation
        cite = cite.strip()

        # Pattern for section number with optional subsections
        section_pattern = r"(\d+\.\d+[A-Za-z]?)(?:\(([^)]+)\))?"

        # Try to find the section number
        match = re.search(section_pattern, cite)
        if not match:
            raise ValueError(f"Cannot parse Florida citation: {cite}")

        section = match.group(1)

        # Parse subsections like (1)(a)(I) into 1/a/I
        subsection = None
        remainder = cite[match.end():]
        sub_pattern = r"\(([^)]+)\)"
        subs = re.findall(sub_pattern, cite)
        if subs:
            subsection = "/".join(subs)

        return cls(section=section, subsection=subsection)


def convert_to_section(fl_section: FLSection) -> Section:
    """Convert FL scrape section to Arch Section model.

    Args:
        fl_section: Section from FL scraper

    Returns:
        Arch Section model
    """
    # Create citation - use 0 as title indicator for state laws
    citation = Citation(
        title=0,  # State law indicator
        section=f"FL-{fl_section.number}",
    )

    # Convert subsections
    subsections = [
        Subsection(
            identifier=sub.identifier,
            heading=None,
            text=sub.text,
            children=[
                Subsection(
                    identifier=child.identifier,
                    heading=None,
                    text=child.text,
                    children=[],
                )
                for child in sub.children
            ],
        )
        for sub in fl_section.subsections
    ]

    return Section(
        citation=citation,
        title_name=f"Florida Statutes Chapter {fl_section.chapter}",
        section_title=fl_section.title,
        text=fl_section.text,
        subsections=subsections,
        source_url=fl_section.url,
        retrieved_at=date.today(),
        uslm_id=f"fl/{fl_section.chapter}/{fl_section.number}",
    )


def download_fl_chapter(
    chapter: int,
    rate_limit_delay: float = 0.5,
) -> Iterator[Section]:
    """Download all sections from a Florida Statutes chapter.

    Args:
        chapter: Chapter number (e.g., 212)
        rate_limit_delay: Seconds between requests

    Yields:
        Section objects for each section in the chapter
    """
    with FLStatutesClient(rate_limit_delay=rate_limit_delay) as client:
        for fl_section in client.iter_chapter(chapter):
            yield convert_to_section(fl_section)


def download_fl_tax_statutes(
    rate_limit_delay: float = 0.5,
) -> Iterator[Section]:
    """Download all sections from Florida tax-related chapters (192-220).

    Args:
        rate_limit_delay: Seconds between requests

    Yields:
        Section objects for each section
    """
    with FLStatutesClient(rate_limit_delay=rate_limit_delay) as client:
        yield from (convert_to_section(s) for s in client.iter_chapters())


def download_fl_welfare_statutes(
    rate_limit_delay: float = 0.5,
) -> Iterator[Section]:
    """Download all sections from Florida social welfare chapters (409-430).

    Args:
        rate_limit_delay: Seconds between requests

    Yields:
        Section objects for each section
    """
    chapters = list(FL_WELFARE_CHAPTERS.keys())
    with FLStatutesClient(rate_limit_delay=rate_limit_delay) as client:
        yield from (convert_to_section(s) for s in client.iter_chapters(chapters))
