"""Parser for USLM (United States Legislative Markup) XML format.

USLM is the official XML schema for the US Code, published by the Office of
the Law Revision Counsel at uscode.house.gov.

Schema documentation: https://uscode.house.gov/download/resources/USLM-User-Guide.pdf
"""

from collections.abc import Iterator
from datetime import date
from pathlib import Path

from lxml import etree

from atlas.models import Citation, Section, Subsection

# USLM namespaces - the actual namespace varies by source
USLM_NS_GPO = {"uslm": "http://schemas.gpo.gov/xml/uslm"}
USLM_NS_HOUSE = {"uslm": "http://xml.house.gov/schemas/uslm/1.0"}


class USLMParser:
    """Parser for USLM XML files from uscode.house.gov."""

    def __init__(self, xml_path: Path | str):
        """Initialize parser with path to USLM XML file.

        Args:
            xml_path: Path to the USLM XML file (e.g., usc26.xml for Title 26)
        """
        self.xml_path = Path(xml_path)
        self._tree: etree._ElementTree | None = None
        self._ns: dict[str, str] = {}  # Detected namespace

    def _detect_namespace(self) -> dict[str, str]:
        """Detect which USLM namespace the document uses."""
        root = self.tree.getroot()
        ns = root.nsmap.get(None, "")  # Default namespace

        if "xml.house.gov" in ns:
            return USLM_NS_HOUSE
        elif "schemas.gpo.gov" in ns:
            return USLM_NS_GPO
        else:
            # Try to detect from root element
            if "house.gov" in str(root.tag):
                return USLM_NS_HOUSE
            return USLM_NS_GPO

    @property
    def ns(self) -> dict[str, str]:
        """Get the namespace dict for XPath queries."""
        if not self._ns:
            self._ns = self._detect_namespace()
        return self._ns

    @property
    def tree(self) -> etree._ElementTree:
        """Lazily load and return the XML tree."""
        if self._tree is None:
            self._tree = etree.parse(str(self.xml_path))
        return self._tree

    def get_title_number(self) -> int:
        """Extract the title number from the XML."""
        root = self.tree.getroot()
        # Try to get from docNumber in meta first (most reliable)
        doc_num = root.find(".//docNumber", self.ns)
        if doc_num is None:
            # Try without namespace
            doc_num = root.find(".//{http://xml.house.gov/schemas/uslm/1.0}docNumber")
        if doc_num is None:
            doc_num = root.find(".//docNumber")
        if doc_num is not None and doc_num.text:
            return int(doc_num.text.strip())

        # Fallback: Title number is in the identifier attribute
        title_elem = root.find(".//uslm:title", self.ns)
        if title_elem is not None:
            identifier = title_elem.get("identifier", "")
            # Format: /us/usc/t26 -> 26
            if "/t" in identifier:
                return int(identifier.split("/t")[-1])

        # Last resort: check root identifier
        root_id = root.get("identifier", "")
        if "/t" in root_id:
            return int(root_id.split("/t")[-1].split("/")[0])

        raise ValueError(f"Cannot determine title number from {self.xml_path}")

    def get_title_name(self) -> str:
        """Extract the title name (e.g., 'Internal Revenue Code')."""
        root = self.tree.getroot()
        # Try with namespace
        heading = root.find(".//uslm:title/uslm:heading", self.ns)
        if heading is not None and heading.text:
            return heading.text.strip()
        # Try finding title element directly with full namespace
        ns_uri = self.ns.get("uslm", "")
        for title_elem in root.iter(f"{{{ns_uri}}}title"):
            heading = title_elem.find(f"{{{ns_uri}}}heading")
            if heading is not None and heading.text:
                return heading.text.strip()
        return f"Title {self.get_title_number()}"

    def iter_sections(self) -> Iterator[Section]:
        """Iterate over all sections in the title.

        Yields:
            Section objects for each section in the title
        """
        root = self.tree.getroot()
        title_num = self.get_title_number()
        title_name = self.get_title_name()
        ns_uri = self.ns.get("uslm", "")

        for section_elem in root.iter(f"{{{ns_uri}}}section"):
            try:
                section = self._parse_section(section_elem, title_num, title_name)
                if section:
                    yield section
            except Exception as e:
                # Log but continue - don't let one bad section stop everything
                identifier = section_elem.get("identifier", "unknown")
                print(f"Warning: Failed to parse section {identifier}: {e}")

    def get_section(self, section_num: str) -> Section | None:
        """Get a specific section by number.

        Args:
            section_num: Section number (e.g., "32" or "32A")

        Returns:
            Section object or None if not found
        """
        root = self.tree.getroot()
        title_num = self.get_title_number()
        title_name = self.get_title_name()
        ns_uri = self.ns.get("uslm", "")

        # USLM identifier format: /us/usc/t26/s32
        target_id = f"/us/usc/t{title_num}/s{section_num}"

        for section_elem in root.iter(f"{{{ns_uri}}}section"):
            if section_elem.get("identifier") == target_id:
                return self._parse_section(section_elem, title_num, title_name)

        return None

    def _parse_section(
        self, elem: etree._Element, title_num: int, title_name: str
    ) -> Section | None:
        """Parse a section element into a Section model."""
        identifier = elem.get("identifier", "")
        if not identifier:
            return None

        # Extract section number from identifier like /us/usc/t26/s32
        section_num = identifier.split("/s")[-1] if "/s" in identifier else ""
        if not section_num:
            return None

        # Get section heading
        heading_elem = elem.find("uslm:heading", self.ns)
        section_title = ""
        if heading_elem is not None:
            section_title = self._get_text_content(heading_elem)

        # Get full text content
        text = self._get_section_text(elem)

        # Parse subsections
        subsections = self._parse_subsections(elem)

        # Extract cross-references
        references = self._extract_references(elem)

        # Get source URL
        source_url = f"https://uscode.house.gov/view.xhtml?req={title_num}+USC+{section_num}"

        return Section(
            citation=Citation(title=title_num, section=section_num),
            title_name=title_name,
            section_title=section_title,
            text=text,
            subsections=subsections,
            references_to=references,
            source_url=source_url,
            retrieved_at=date.today(),
            uslm_id=identifier,
        )

    def _parse_subsections(self, parent: etree._Element) -> list[Subsection]:
        """Recursively parse subsection hierarchy."""
        subsections = []

        # USLM uses various elements for subsection levels
        subsection_tags = ["subsection", "paragraph", "subparagraph", "clause", "subclause"]

        for tag in subsection_tags:
            for sub_elem in parent.findall(f"uslm:{tag}", self.ns):
                identifier = sub_elem.get("identifier", "")
                # Extract the local identifier (e.g., "a" from "/us/usc/t26/s32/a")
                local_id = identifier.split("/")[-1] if identifier else ""

                heading_elem = sub_elem.find("uslm:heading", self.ns)
                heading = self._get_text_content(heading_elem) if heading_elem is not None else None

                # Get text content (excluding child subsections)
                text = self._get_direct_text(sub_elem)

                # Recursively parse children
                children = self._parse_subsections(sub_elem)

                if local_id:
                    subsections.append(
                        Subsection(
                            identifier=local_id,
                            heading=heading,
                            text=text,
                            children=children,
                        )
                    )

        return subsections

    def _get_text_content(self, elem: etree._Element) -> str:
        """Get all text content from an element, including nested elements."""
        return "".join(elem.itertext()).strip()

    def _get_direct_text(self, elem: etree._Element) -> str:
        """Get text content directly in this element, not in child subsections."""
        # Get text from content/chapeau elements, not from child subsections
        parts = []

        if elem.text:
            parts.append(elem.text.strip())

        for child in elem:
            tag = etree.QName(child.tag).localname
            # Skip subsection children, include content elements
            if tag in ["content", "chapeau", "text", "continuation"]:
                parts.append(self._get_text_content(child))
            elif (
                tag not in ["subsection", "paragraph", "subparagraph", "clause", "subclause"]
                and child.text
            ):
                # Include other inline content
                parts.append(child.text.strip())
            if child.tail:
                parts.append(child.tail.strip())

        return " ".join(filter(None, parts))

    def _get_section_text(self, elem: etree._Element) -> str:
        """Get the full text of a section including all subsections."""
        return self._get_text_content(elem)

    def _extract_references(self, elem: etree._Element) -> list[str]:
        """Extract cross-references to other sections."""
        references = []
        ns_uri = self.ns.get("uslm", "")

        for ref in elem.iter(f"{{{ns_uri}}}ref"):
            href = ref.get("href", "")
            if href.startswith("/us/usc/"):
                # Convert USLM reference to citation
                # /us/usc/t26/s32 -> 26 USC 32
                parts = href.split("/")
                if len(parts) >= 5:
                    title = parts[3].replace("t", "")
                    section = parts[4].replace("s", "")
                    references.append(f"{title} USC {section}")

        return list(set(references))  # Deduplicate


def download_title(title_num: int, output_dir: Path) -> Path:
    """Download a US Code title from uscode.house.gov.

    Args:
        title_num: Title number (1-54)
        output_dir: Directory to save the XML file

    Returns:
        Path to the downloaded XML file
    """
    import httpx

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"usc{title_num}.xml"

    # URL format for USLM XML downloads
    url = f"https://uscode.house.gov/download/releasepoints/us/pl/119/46/xml_usc{title_num:02d}@119-46.zip"

    print(f"Downloading Title {title_num} from {url}...")

    with httpx.Client(timeout=120.0) as client:
        response = client.get(url)
        response.raise_for_status()

        # It's a zip file, extract the XML
        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            # Find the main XML file
            xml_files = [n for n in zf.namelist() if n.endswith(".xml")]
            if not xml_files:
                raise ValueError(f"No XML files found in downloaded archive for Title {title_num}")

            # Extract the first (usually only) XML file
            xml_content = zf.read(xml_files[0])
            output_path.write_bytes(xml_content)

    print(f"Saved to {output_path}")
    return output_path
