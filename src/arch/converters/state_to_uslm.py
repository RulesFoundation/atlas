"""Convert state statute HTML to USLM-style XML.

This module converts scraped state statute HTML into a USLM-compatible XML format
that can be ingested using the existing USLMParser.

Usage:
    from arch.converters.state_to_uslm import OhioToUSLM

    converter = OhioToUSLM()
    xml_str = converter.convert_html(html_content, section_url)

    # Save to file
    converter.convert_file("input.html", "output.xml")
"""

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup, Tag


# USLM namespace - using House.gov format for compatibility
USLM_NS = "http://xml.house.gov/schemas/uslm/1.0"
NSMAP = {"uslm": USLM_NS}


@dataclass
class ParsedSubsection:
    """A parsed subsection from HTML."""
    identifier: str  # e.g., "A", "1", "a"
    level: int  # 0=subsection, 1=paragraph, 2=subparagraph, etc.
    text: str
    children: list["ParsedSubsection"] = field(default_factory=list)


@dataclass
class ParsedSection:
    """A parsed section from HTML."""
    state: str  # e.g., "oh"
    code: str  # e.g., "orc" (Ohio Revised Code)
    title_num: str  # e.g., "57"
    title_name: str  # e.g., "Taxation"
    chapter_num: str  # e.g., "5747"
    chapter_name: str  # e.g., "Income Tax"
    section_num: str  # e.g., "5747.02"
    section_title: str  # e.g., "Tax rates"
    effective_date: Optional[str] = None
    legislation: Optional[str] = None
    text: str = ""
    subsections: list[ParsedSubsection] = field(default_factory=list)
    source_url: str = ""


class StateToUSLMConverter:
    """Base class for converting state HTML to USLM XML."""

    state_code: str = ""
    code_abbrev: str = ""  # e.g., "orc" for Ohio Revised Code

    def convert_html(self, html: str, source_url: str = "") -> str:
        """Convert HTML string to USLM XML string.

        Args:
            html: Raw HTML content
            source_url: Source URL for the section

        Returns:
            USLM XML as string
        """
        parsed = self.parse_html(html, source_url)
        return self.to_uslm_xml(parsed)

    def convert_file(self, input_path: Path | str, output_path: Path | str) -> None:
        """Convert an HTML file to USLM XML file."""
        input_path = Path(input_path)
        output_path = Path(output_path)

        html = input_path.read_text()
        xml_str = self.convert_html(html, f"file://{input_path}")
        output_path.write_text(xml_str)

    def parse_html(self, html: str, source_url: str = "") -> ParsedSection:
        """Parse HTML into structured data. Override in subclasses."""
        raise NotImplementedError

    def to_uslm_xml(self, parsed: ParsedSection) -> str:
        """Convert ParsedSection to USLM XML string."""
        # Create root element with namespace
        root = ET.Element(f"{{{USLM_NS}}}lawDoc")
        root.set("identifier", f"/us/{parsed.state}/{parsed.code}")

        # Add meta section
        meta = ET.SubElement(root, f"{{{USLM_NS}}}meta")

        doc_num = ET.SubElement(meta, f"{{{USLM_NS}}}docNumber")
        doc_num.text = parsed.title_num

        if parsed.effective_date:
            eff_date = ET.SubElement(meta, f"{{{USLM_NS}}}date")
            eff_date.set("type", "effective")
            eff_date.text = parsed.effective_date

        # Add title element
        title = ET.SubElement(root, f"{{{USLM_NS}}}title")
        title.set("identifier", f"/us/{parsed.state}/{parsed.code}/t{parsed.title_num}")

        title_heading = ET.SubElement(title, f"{{{USLM_NS}}}heading")
        title_heading.text = f"Title {parsed.title_num} - {parsed.title_name}"

        # Add chapter element
        chapter = ET.SubElement(title, f"{{{USLM_NS}}}chapter")
        chapter.set("identifier", f"/us/{parsed.state}/{parsed.code}/t{parsed.title_num}/ch{parsed.chapter_num}")

        chapter_heading = ET.SubElement(chapter, f"{{{USLM_NS}}}heading")
        chapter_heading.text = f"Chapter {parsed.chapter_num} - {parsed.chapter_name}"

        # Add section element
        section = ET.SubElement(chapter, f"{{{USLM_NS}}}section")
        section.set("identifier", f"/us/{parsed.state}/{parsed.code}/s{parsed.section_num}")

        section_heading = ET.SubElement(section, f"{{{USLM_NS}}}heading")
        section_heading.text = parsed.section_title

        # Add content
        if parsed.text and not parsed.subsections:
            content = ET.SubElement(section, f"{{{USLM_NS}}}content")
            content.text = parsed.text

        # Add subsections recursively
        self._add_subsections(section, parsed.subsections)

        # Convert to string with XML declaration
        ET.register_namespace("", USLM_NS)
        ET.register_namespace("uslm", USLM_NS)

        # Use indent for readability (Python 3.9+)
        ET.indent(root)

        xml_str = ET.tostring(root, encoding="unicode", xml_declaration=True)
        return xml_str

    def _add_subsections(self, parent: ET.Element, subsections: list[ParsedSubsection]) -> None:
        """Recursively add subsections to XML element."""
        # USLM level mapping
        level_tags = ["subsection", "paragraph", "subparagraph", "clause", "subclause"]

        for sub in subsections:
            tag = level_tags[min(sub.level, len(level_tags) - 1)]
            elem = ET.SubElement(parent, f"{{{USLM_NS}}}{tag}")

            # Build identifier from parent
            parent_id = parent.get("identifier", "")
            elem.set("identifier", f"{parent_id}/{sub.identifier}")

            # Add num element for the identifier
            num = ET.SubElement(elem, f"{{{USLM_NS}}}num")
            num.text = f"({sub.identifier})"

            # Add content
            if sub.text:
                content = ET.SubElement(elem, f"{{{USLM_NS}}}content")
                content.text = sub.text

            # Recurse for children
            if sub.children:
                self._add_subsections(elem, sub.children)


class OhioToUSLM(StateToUSLMConverter):
    """Convert Ohio Revised Code HTML to USLM XML."""

    state_code = "oh"
    code_abbrev = "orc"

    def parse_html(self, html: str, source_url: str = "") -> ParsedSection:
        """Parse Ohio statute HTML."""
        soup = BeautifulSoup(html, "html.parser")

        # Extract section number and title from h1
        h1 = soup.find("h1")
        section_num = ""
        section_title = ""
        if h1:
            h1_text = h1.get_text(strip=True)
            # Format: "Section 5747.02 | Tax rates."
            match = re.match(r"Section\s+([\d.]+)\s*\|\s*(.+)", h1_text)
            if match:
                section_num = match.group(1)
                section_title = match.group(2).rstrip(".")

        # Extract hierarchy from breadcrumbs
        title_num = ""
        title_name = ""
        chapter_num = ""
        chapter_name = ""

        breadcrumbs = soup.find_all("a", href=re.compile(r"/ohio-revised-code/(title|chapter)-"))
        for crumb in breadcrumbs:
            href = crumb.get("href", "")
            text = crumb.get_text(strip=True)

            if "/title-" in href:
                # "Title 57 Taxation"
                match = re.match(r"Title\s+(\d+)\s+(.+)", text)
                if match:
                    title_num = match.group(1)
                    title_name = match.group(2)
            elif "/chapter-" in href:
                # "Chapter 5747 Income Tax"
                match = re.match(r"Chapter\s+(\d+)\s+(.+)", text)
                if match:
                    chapter_num = match.group(1)
                    chapter_name = match.group(2)

        # Extract effective date
        effective_date = None
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if text.startswith("Effective:"):
                effective_date = text.replace("Effective:", "").strip()
                break

        # Extract legislation info
        legislation = None
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if text.startswith("Latest Legislation:"):
                legislation = text.replace("Latest Legislation:", "").strip()
                break

        # Extract main content and parse subsections
        main_content = soup.find("main") or soup.find("article") or soup.find("body")
        text, subsections = self._parse_content(main_content)

        return ParsedSection(
            state=self.state_code,
            code=self.code_abbrev,
            title_num=title_num,
            title_name=title_name,
            chapter_num=chapter_num,
            chapter_name=chapter_name,
            section_num=section_num,
            section_title=section_title,
            effective_date=effective_date,
            legislation=legislation,
            text=text,
            subsections=subsections,
            source_url=source_url,
        )

    def _parse_content(self, elem: Tag | None) -> tuple[str, list[ParsedSubsection]]:
        """Parse content and extract subsections."""
        if not elem:
            return "", []

        # Get full text
        full_text = elem.get_text(separator="\n", strip=True)

        # Parse subsections from text using regex
        subsections = self._parse_subsections_from_text(full_text)

        # If we found subsections, return empty text (it's in the subsections)
        # Otherwise return the full text
        if subsections:
            return "", subsections
        return full_text, []

    def _parse_subsections_from_text(self, text: str) -> list[ParsedSubsection]:
        """Parse subsections from plain text using regex patterns."""
        # Ohio uses: (A), (B)... for subsections, (1), (2)... for paragraphs,
        # (a), (b)... for subparagraphs

        # Pattern to match subsection markers
        # We'll parse level by level
        subsections = []

        # Level 0: (A), (B), etc. - uppercase letters
        level0_pattern = r'\(([A-Z])\)\s*'
        # Level 1: (1), (2), etc. - numbers
        level1_pattern = r'\((\d+)\)\s*'
        # Level 2: (a), (b), etc. - lowercase letters
        level2_pattern = r'\(([a-z])\)\s*'

        # Split by top-level subsections first
        parts = re.split(r'(?=\([A-Z]\))', text)

        for part in parts[1:]:  # Skip content before first (A)
            match = re.match(level0_pattern, part)
            if not match:
                continue

            identifier = match.group(1)
            content = part[match.end():]

            # Parse level 1 children
            children = self._parse_level1(content)

            # Get text before first child
            if children:
                first_child_match = re.search(r'\(\d+\)', content)
                direct_text = content[:first_child_match.start()].strip() if first_child_match else content.strip()
            else:
                direct_text = content.strip()

            subsections.append(ParsedSubsection(
                identifier=identifier,
                level=0,
                text=direct_text[:2000] if len(direct_text) > 2000 else direct_text,  # Limit text size
                children=children,
            ))

        return subsections

    def _parse_level1(self, text: str) -> list[ParsedSubsection]:
        """Parse level 1 subsections (1), (2), etc."""
        subsections = []
        parts = re.split(r'(?=\(\d+\))', text)

        for part in parts[1:]:
            match = re.match(r'\((\d+)\)\s*', part)
            if not match:
                continue

            identifier = match.group(1)
            content = part[match.end():]

            # Parse level 2 children
            children = self._parse_level2(content)

            # Get text before first child
            if children:
                first_child_match = re.search(r'\([a-z]\)', content)
                direct_text = content[:first_child_match.start()].strip() if first_child_match else content.strip()
            else:
                direct_text = content.strip()

            subsections.append(ParsedSubsection(
                identifier=identifier,
                level=1,
                text=direct_text[:2000] if len(direct_text) > 2000 else direct_text,
                children=children,
            ))

        return subsections

    def _parse_level2(self, text: str) -> list[ParsedSubsection]:
        """Parse level 2 subsections (a), (b), etc."""
        subsections = []
        parts = re.split(r'(?=\([a-z]\))', text)

        for part in parts[1:]:
            match = re.match(r'\(([a-z])\)\s*', part)
            if not match:
                continue

            identifier = match.group(1)
            content = part[match.end():]

            # Limit content to reasonable size
            direct_text = content.strip()
            if len(direct_text) > 2000:
                direct_text = direct_text[:2000] + "..."

            subsections.append(ParsedSubsection(
                identifier=identifier,
                level=2,
                text=direct_text,
                children=[],  # Could add level 3 parsing if needed
            ))

        return subsections


# Registry of state converters
STATE_CONVERTERS: dict[str, type[StateToUSLMConverter]] = {
    "oh": OhioToUSLM,
}


def get_converter(state_code: str) -> StateToUSLMConverter | None:
    """Get a converter for a state."""
    converter_class = STATE_CONVERTERS.get(state_code.lower())
    if converter_class:
        return converter_class()
    return None


if __name__ == "__main__":
    # Test with a sample
    import httpx

    print("Fetching Ohio section 5747.02...")
    response = httpx.get("https://codes.ohio.gov/ohio-revised-code/section-5747.02")
    html = response.text

    converter = OhioToUSLM()
    xml_output = converter.convert_html(html, "https://codes.ohio.gov/ohio-revised-code/section-5747.02")

    print("\n" + "="*60)
    print("USLM XML Output (first 3000 chars):")
    print("="*60)
    print(xml_output[:3000])

    # Save to file
    output_path = Path("data/ohio_5747.02.xml")
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(xml_output)
    print(f"\nSaved to {output_path}")
