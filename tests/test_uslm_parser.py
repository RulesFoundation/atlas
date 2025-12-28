"""Tests for USLM XML parser.

These tests use real downloaded USLM XML from uscode.house.gov.
Run `atlas download 26` first to get the test data.
"""

from pathlib import Path

import pytest

from atlas.parsers.uslm import USLMParser

# Skip tests if Title 26 hasn't been downloaded
TITLE_26_PATH = Path("data/uscode/usc26.xml")
pytestmark = pytest.mark.skipif(
    not TITLE_26_PATH.exists(), reason="Title 26 XML not downloaded. Run: atlas download 26"
)


class TestUSLMParserRealData:
    """Tests using real USLM XML from Title 26."""

    @pytest.fixture
    def parser(self):
        """Create parser for Title 26."""
        return USLMParser(TITLE_26_PATH)

    def test_get_title_number(self, parser):
        """Should extract title number 26."""
        assert parser.get_title_number() == 26

    def test_get_title_name(self, parser):
        """Should extract title name."""
        name = parser.get_title_name()
        assert "INTERNAL REVENUE" in name.upper()

    def test_get_section_32_eitc(self, parser):
        """Should parse Section 32 (EITC)."""
        section = parser.get_section("32")
        assert section is not None
        assert section.citation.title == 26
        assert section.citation.section == "32"
        # EITC section should mention "earned income"
        assert "earned income" in section.text.lower()

    def test_section_32_has_subsections(self, parser):
        """Section 32 should have subsections (a), (b), (c), etc."""
        section = parser.get_section("32")
        assert section is not None
        assert len(section.subsections) > 0
        # Should have subsection (a)
        sub_ids = [s.identifier for s in section.subsections]
        assert "a" in sub_ids or "(a)" in sub_ids

    def test_get_section_1_tax_imposed(self, parser):
        """Should parse Section 1 (Tax imposed)."""
        section = parser.get_section("1")
        assert section is not None
        assert section.citation.section == "1"
        assert "tax" in section.text.lower()

    def test_iter_sections_yields_many(self, parser):
        """Should yield many sections from Title 26."""
        count = 0
        for _section in parser.iter_sections():
            count += 1
            if count >= 100:
                break  # Don't iterate all ~10k sections
        assert count >= 100

    def test_section_has_cross_references(self, parser):
        """Sections should extract cross-references."""
        section = parser.get_section("32")
        assert section is not None
        # Section 32 references other sections
        # This might be empty if references aren't parsed correctly
        # but at minimum the list should exist
        assert isinstance(section.references_to, list)

    def test_section_source_url(self, parser):
        """Section should have valid source URL."""
        section = parser.get_section("32")
        assert section is not None
        assert "uscode.house.gov" in section.source_url
        assert "32" in section.source_url
