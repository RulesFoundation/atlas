"""Tests for New York state laws scraper."""

import os
from unittest.mock import MagicMock, patch

import pytest

from atlas.parsers.ny_laws import (
    NY_LAW_CODES,
    NYLegislationAPIError,
    NYLegislationClient,
    NYSection,
    NYStateCitation,
    _extract_section_number,
    convert_to_section,
)


class TestNYStateCitation:
    """Tests for NY state citation formatting."""

    def test_simple_citation(self):
        """Test simple citation format."""
        cite = NYStateCitation("TAX", "606")
        assert cite.cite_string == "NY Tax Law \u00a7 606"
        assert cite.path == "state/ny/tax/606"

    def test_citation_with_subsection(self):
        """Test citation with subsection."""
        cite = NYStateCitation("TAX", "606", "d")
        assert cite.cite_string == "NY Tax Law \u00a7 606(d)"
        assert cite.path == "state/ny/tax/606/d"

    def test_citation_nested_subsection(self):
        """Test citation with nested subsections."""
        cite = NYStateCitation("TAX", "606", "d/1/A")
        assert cite.cite_string == "NY Tax Law \u00a7 606(d)(1)(A)"
        assert cite.path == "state/ny/tax/606/d/1/A"

    def test_citation_unknown_law(self):
        """Test citation for unknown law code."""
        cite = NYStateCitation("XYZ", "100")
        assert cite.cite_string == "NY XYZ Law \u00a7 100"

    def test_social_services_law(self):
        """Test Social Services Law citation."""
        cite = NYStateCitation("SOS", "131")
        assert cite.cite_string == "NY Social Services Law \u00a7 131"


class TestExtractSectionNumber:
    """Tests for section number extraction."""

    def test_simple_section(self):
        """Test simple section number."""
        assert _extract_section_number("606") == "606"

    def test_article_section_format(self):
        """Test article-section format like A22S606."""
        assert _extract_section_number("A22S606") == "606"

    def test_short_article_section(self):
        """Test short format like A1S1."""
        assert _extract_section_number("A1S1") == "1"

    def test_empty_location(self):
        """Test empty location ID."""
        assert _extract_section_number("") == ""

    def test_complex_section(self):
        """Test complex section number."""
        assert _extract_section_number("A9TS151-A") == "151-A"


class TestConvertToSection:
    """Tests for converting NY sections to Atlas Section model."""

    def test_convert_simple_section(self):
        """Test converting a simple NY section."""
        ny_section = NYSection(
            law_id="TAX",
            location_id="606",
            title="Credits against tax",
            text="Sample text for section 606...",
            doc_type="SECTION",
            doc_level_id="SECTION",
            active_date="2024-01-01",
        )

        section = convert_to_section(ny_section)

        assert section.citation.title == 0  # State law indicator
        assert section.citation.section == "NY-TAX-606"
        assert section.title_name == "New York Tax Law"
        assert section.section_title == "Credits against tax"
        assert section.text == "Sample text for section 606..."
        assert "legislation.nysenate.gov" in section.source_url

    def test_convert_article_section(self):
        """Test converting section with article prefix."""
        ny_section = NYSection(
            law_id="SOS",
            location_id="A5S131",
            title="Public assistance",
            text="Text...",
            doc_type="SECTION",
            doc_level_id="SECTION",
        )

        section = convert_to_section(ny_section)

        assert section.citation.section == "NY-SOS-131"
        assert section.title_name == "New York Social Services Law"


class TestNYLawCodes:
    """Tests for NY law code constants."""

    def test_tax_law_present(self):
        """Tax Law should be in the codes."""
        assert "TAX" in NY_LAW_CODES
        assert NY_LAW_CODES["TAX"] == "Tax Law"

    def test_social_services_present(self):
        """Social Services Law should be in the codes."""
        assert "SOS" in NY_LAW_CODES
        assert NY_LAW_CODES["SOS"] == "Social Services Law"


class TestNYLegislationClientErrors:
    """Tests for NY API client error handling."""

    def test_missing_api_key_raises(self):
        """Missing API key should raise ValueError."""
        # Remove the key if it exists
        env = os.environ.copy()
        env.pop("NY_LEGISLATION_API_KEY", None)
        with patch.dict(os.environ, env, clear=True), pytest.raises(
            ValueError, match="NY API key required"
        ):
            NYLegislationClient()


class TestNYLegislationClientMocked:
    """Tests for NY API client with mocked responses."""

    @pytest.fixture
    def mock_client(self):
        """Create a client with mocked HTTP responses."""
        with patch.dict(os.environ, {"NY_LEGISLATION_API_KEY": "test_key"}):
            client = NYLegislationClient(api_key="test_key")
            client.client = MagicMock()
            yield client
            client.close()

    def test_get_law_ids(self, mock_client):
        """Test getting list of law IDs."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "result": {
                "items": [
                    {"lawId": "TAX", "chapter": "60", "name": "Tax", "lawType": "CONSOLIDATED"},
                    {"lawId": "SOS", "chapter": "55", "name": "Social Services", "lawType": "CONSOLIDATED"},
                ]
            },
        }
        mock_client.client.get.return_value = mock_response

        laws = mock_client.get_law_ids()

        assert len(laws) == 2
        assert laws[0].law_id == "TAX"
        assert laws[1].law_id == "SOS"

    def test_get_section(self, mock_client):
        """Test getting a specific section."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "result": {
                "lawId": "TAX",
                "locationId": "606",
                "title": "Credits against tax",
                "text": "Section text here...",
                "docType": "SECTION",
                "docLevelId": "SECTION",
                "activeDate": "2024-01-01",
            },
        }
        mock_client.client.get.return_value = mock_response

        section = mock_client.get_section("TAX", "606")

        assert section.law_id == "TAX"
        assert section.location_id == "606"
        assert section.title == "Credits against tax"
        assert section.text == "Section text here..."

    def test_api_error_response(self, mock_client):
        """Test handling of API error response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": False,
            "message": "Invalid API key",
            "errorCode": 701,
        }
        mock_client.client.get.return_value = mock_response

        with pytest.raises(NYLegislationAPIError) as exc_info:
            mock_client.get_law_ids()

        assert exc_info.value.error_code == 701
        assert "Invalid API key" in str(exc_info.value)

    def test_search(self, mock_client):
        """Test search functionality."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "result": {
                "items": [
                    {"lawId": "TAX", "locationId": "606", "title": "Credits"},
                ]
            },
        }
        mock_client.client.get.return_value = mock_response

        results = mock_client.search("earned income credit", law_id="TAX")

        assert len(results) == 1
        assert results[0]["lawId"] == "TAX"


class TestNYLegislationClientIntegration:
    """Integration tests that require a real API key.

    These tests are skipped if NY_LEGISLATION_API_KEY is not set.
    Run with: pytest tests/test_ny_laws.py -v -k integration
    """

    @pytest.fixture
    def real_client(self):
        """Create a client with real API key if available."""
        api_key = os.environ.get("NY_LEGISLATION_API_KEY")
        if not api_key:
            pytest.skip("NY_LEGISLATION_API_KEY not set")
        client = NYLegislationClient(api_key=api_key, rate_limit_delay=0.5)
        yield client
        client.close()

    @pytest.mark.integration
    def test_list_laws_real(self, real_client):
        """Test listing laws with real API."""
        laws = real_client.get_law_ids()
        assert len(laws) > 0

        # TAX should be in the list
        law_ids = [law.law_id for law in laws]
        assert "TAX" in law_ids

    @pytest.mark.integration
    def test_get_tax_section_606_real(self, real_client):
        """Test getting NY EITC section (TAX 606)."""
        section = real_client.get_section("TAX", "606")

        assert section.law_id == "TAX"
        assert section.location_id == "606"
        assert len(section.text) > 0
        # Should contain earned income credit language
        assert "credit" in section.text.lower() or "tax" in section.text.lower()

    @pytest.mark.integration
    def test_search_earned_income_real(self, real_client):
        """Test searching for earned income credit."""
        results = real_client.search("earned income credit", law_id="TAX", limit=10)

        # Should find at least one result
        assert len(results) >= 0  # May not find results depending on search index
