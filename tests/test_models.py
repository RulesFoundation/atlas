"""Tests for data models."""

import pytest

from atlas.models import Citation


class TestCitation:
    """Tests for Citation parsing and formatting."""

    def test_parse_simple_citation(self):
        """Parse simple citation like '26 USC 32'."""
        cite = Citation.from_string("26 USC 32")
        assert cite.title == 26
        assert cite.section == "32"
        assert cite.subsection is None

    def test_parse_citation_with_subsection(self):
        """Parse citation with subsection like '26 USC 32(a)'."""
        cite = Citation.from_string("26 USC 32(a)")
        assert cite.title == 26
        assert cite.section == "32"
        assert cite.subsection == "a"

    def test_parse_citation_with_nested_subsections(self):
        """Parse citation with nested subsections like '26 USC 32(a)(1)(A)'."""
        cite = Citation.from_string("26 USC 32(a)(1)(A)")
        assert cite.title == 26
        assert cite.section == "32"
        assert cite.subsection == "a/1/A"

    def test_parse_citation_with_periods(self):
        """Parse citation with U.S.C. format."""
        cite = Citation.from_string("26 U.S.C. 32")
        assert cite.title == 26
        assert cite.section == "32"

    def test_parse_citation_with_section_symbol(self):
        """Parse citation with section symbol."""
        cite = Citation.from_string("26 USC § 32")
        assert cite.title == 26
        assert cite.section == "32"

    def test_parse_section_with_letter(self):
        """Parse section numbers with letters like '32A'."""
        cite = Citation.from_string("26 USC 32A")
        assert cite.title == 26
        assert cite.section == "32A"

    def test_usc_cite_format(self):
        """Test USC citation string output."""
        cite = Citation(title=26, section="32", subsection="a/1")
        assert cite.usc_cite == "26 USC 32(a)(1)"

    def test_path_format(self):
        """Test filesystem path format."""
        cite = Citation(title=26, section="32", subsection="a/1")
        assert cite.path == "statute/26/32/a/1"

    def test_path_format_no_subsection(self):
        """Test path format without subsection."""
        cite = Citation(title=26, section="32")
        assert cite.path == "statute/26/32"

    def test_invalid_citation_raises(self):
        """Invalid citation string raises ValueError."""
        with pytest.raises(ValueError):
            Citation.from_string("not a citation")
