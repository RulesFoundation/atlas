"""State statute pipeline runner.

This module runs the full pipeline for processing state statutes:
1. Fetch raw HTML from state legislature websites
2. Archive raw HTML to R2 arch bucket
3. Parse into sections using state-specific converters
4. Convert to Akoma Ntoso XML
5. Upload AKN XML to R2 rules-xml bucket
"""

import hashlib
import importlib
import inspect
import time
from datetime import datetime, timezone
from typing import Any

from atlas.models import Section
from atlas.pipeline.akn import section_to_akn_xml
from atlas.storage.r2 import R2Storage, get_r2_arch, get_r2_rules_xml


# State converter module paths
STATE_CONVERTERS = {
    "ak": "arch.converters.us_states.ak",
    "al": "arch.converters.us_states.al",
    "ar": "arch.converters.us_states.ar",
    "az": "arch.converters.us_states.az",
    "ca": "arch.converters.us_states.ca",
    "co": "arch.converters.us_states.co",
    "ct": "arch.converters.us_states.ct",
    "fl": "arch.converters.us_states.fl",
    "hi": "arch.converters.us_states.hi",
    "id": "arch.converters.us_states.id_",
    "il": "arch.converters.us_states.il",
    "in": "arch.converters.us_states.in_",
    "ks": "arch.converters.us_states.ks",
    "ky": "arch.converters.us_states.ky",
    "la": "arch.converters.us_states.la",
    "ma": "arch.converters.us_states.ma",
    "md": "arch.converters.us_states.md",
    "me": "arch.converters.us_states.me",
    "mi": "arch.converters.us_states.mi",
    "mn": "arch.converters.us_states.mn",
    "mo": "arch.converters.us_states.mo",
    "ms": "arch.converters.us_states.ms",
    "mt": "arch.converters.us_states.mt",
    "nc": "arch.converters.us_states.nc",
    "nd": "arch.converters.us_states.nd",
    "ne": "arch.converters.us_states.ne",
    "nh": "arch.converters.us_states.nh",
    "nj": "arch.converters.us_states.nj",
    "nm": "arch.converters.us_states.nm",
    "nv": "arch.converters.us_states.nv",
    "ny": "arch.converters.us_states.ny",
    "oh": "arch.converters.us_states.oh",
    "ok": "arch.converters.us_states.ok",
    "or": "arch.converters.us_states.or_",
    "pa": "arch.converters.us_states.pa",
    "ri": "arch.converters.us_states.ri",
    "sc": "arch.converters.us_states.sc",
    "sd": "arch.converters.us_states.sd",
    "tn": "arch.converters.us_states.tn",
    "tx": "arch.converters.us_states.tx",
    "ut": "arch.converters.us_states.ut",
    "va": "arch.converters.us_states.va",
    "vt": "arch.converters.us_states.vt",
    "wa": "arch.converters.us_states.wa",
    "wi": "arch.converters.us_states.wi",
    "wv": "arch.converters.us_states.wv",
    "wy": "arch.converters.us_states.wy",
}


class StatePipeline:
    """Pipeline for processing a single state's statutes.

    Example:
        >>> pipeline = StatePipeline("ak")
        >>> stats = pipeline.run()
        >>> print(f"Uploaded {stats['akn_uploaded']} sections")
    """

    def __init__(
        self,
        state: str,
        dry_run: bool = False,
        r2_arch: R2Storage | None = None,
        r2_rules: R2Storage | None = None,
    ):
        """Initialize the pipeline.

        Args:
            state: Two-letter state code (e.g., 'ak', 'ny')
            dry_run: If True, don't upload anything
            r2_arch: Optional pre-configured R2Storage for arch bucket
            r2_rules: Optional pre-configured R2Storage for rules-xml bucket
        """
        self.state = state.lower()
        self.dry_run = dry_run
        self.r2_arch = r2_arch or get_r2_arch()
        self.r2_rules = r2_rules or get_r2_rules_xml()
        self.converter: Any = None
        self.stats = {
            "sections_found": 0,
            "raw_uploaded": 0,
            "akn_uploaded": 0,
            "errors": 0,
        }

    def _load_converter(self) -> Any:
        """Dynamically load the state converter."""
        module_path = STATE_CONVERTERS.get(self.state)
        if not module_path:
            raise ValueError(f"No converter for state: {self.state}")

        module = importlib.import_module(module_path)

        # Find the converter class (e.g., AKConverter, NYConverter)
        class_name = f"{self.state.upper()}Converter"
        if hasattr(module, class_name):
            return getattr(module, class_name)()

        # Try alternate naming
        for name in dir(module):
            if name.endswith("Converter") and name != "Converter":
                return getattr(module, name)()

        raise ValueError(f"No converter class found in {module_path}")

    def _get_chapter_url(self, chapter: Any, title: int | str | None = None) -> str:
        """Get the URL for a chapter.

        Args:
            chapter: Chapter number or identifier
            title: Title/code for states that need it (e.g., AK uses title, TX uses code)
        """
        if hasattr(self.converter, "_build_chapter_url"):
            sig = inspect.signature(self.converter._build_chapter_url)
            params = list(sig.parameters.keys())
            if len(params) == 2 and title is not None:
                return self.converter._build_chapter_url(title, chapter)
            elif len(params) == 1:
                return self.converter._build_chapter_url(chapter)
            else:
                return f"https://{self.state}.gov/statute/chapter/{chapter}"
        elif hasattr(self.converter, "base_url"):
            return f"{self.converter.base_url}/chapter/{chapter}"
        else:
            return f"https://{self.state}.gov/statute/chapter/{chapter}"

    def _fetch_raw_html(self, url: str) -> str | None:
        """Fetch raw HTML from URL using converter's HTTP client.

        Returns None if fetch fails, allowing the pipeline to continue.
        """
        try:
            if hasattr(self.converter, "_get"):
                return self.converter._get(url)
            elif hasattr(self.converter, "client"):
                response = self.converter.client.get(url)
                return response.text
            else:
                import httpx

                response = httpx.get(url, follow_redirects=True, timeout=30)
                return response.text
        except Exception as e:
            print(f"    WARN: fetch failed: {e}")
            return None

    def _get_chapters(self) -> list[tuple[Any, Any]]:
        """Get list of (chapter, title/code) tuples to process."""
        module = type(self.converter).__module__
        mod = importlib.import_module(module)

        chapters: list[tuple[Any, Any]] = []

        # State-specific handling
        if self.state == "ak":
            # Alaska uses title + chapter
            if hasattr(mod, "AK_TAX_CHAPTERS"):
                for ch in getattr(mod, "AK_TAX_CHAPTERS").keys():
                    chapters.append((ch, 43))  # Title 43 = Revenue and Taxation
            if hasattr(mod, "AK_WELFARE_CHAPTERS"):
                for ch in getattr(mod, "AK_WELFARE_CHAPTERS").keys():
                    chapters.append((ch, 47))  # Title 47 = Welfare

        elif self.state == "tx":
            # Texas uses code + chapter
            if hasattr(mod, "TX_TAX_CHAPTERS"):
                for ch in getattr(mod, "TX_TAX_CHAPTERS").keys():
                    chapters.append((ch, "TX"))  # TX = Tax Code
            if hasattr(mod, "TX_WELFARE_CHAPTERS"):
                for ch in getattr(mod, "TX_WELFARE_CHAPTERS").keys():
                    chapters.append((ch, "HR"))  # HR = Human Resources Code

        else:
            # Standard pattern for other states
            for attr in [
                "TAX_CHAPTERS",
                "WELFARE_CHAPTERS",
                f"{self.state.upper()}_TAX_CHAPTERS",
                f"{self.state.upper()}_WELFARE_CHAPTERS",
            ]:
                if hasattr(mod, attr):
                    for ch in getattr(mod, attr).keys():
                        chapters.append((ch, None))

            if not chapters:
                # Try title-based approach
                for attr in ["TITLES", f"{self.state.upper()}_TITLES", "TAX_TITLES"]:
                    if hasattr(mod, attr):
                        for t in getattr(mod, attr).keys():
                            chapters.append((str(t), None))

        return chapters

    def _get_sections(
        self, chapter: Any, title_or_code: Any
    ) -> list[Section]:
        """Get sections for a chapter using the appropriate method."""
        sections: list[Section] = []

        if self.state == "ak" and title_or_code:
            # Alaska uses iter_chapter(title, chapter)
            if hasattr(self.converter, "iter_chapter"):
                sections = list(self.converter.iter_chapter(title_or_code, chapter))

        elif self.state == "tx" and title_or_code:
            # Texas uses iter_chapter(code, chapter)
            if hasattr(self.converter, "iter_chapter"):
                sections = list(self.converter.iter_chapter(title_or_code, chapter))

        elif hasattr(self.converter, "iter_chapter"):
            # FL and other states: iter_chapter(chapter) with single arg
            # Convert chapter to int if it's a string number
            ch = int(chapter) if isinstance(chapter, str) and chapter.isdigit() else chapter
            sections = list(self.converter.iter_chapter(ch))

        elif hasattr(self.converter, "fetch_chapter"):
            result = self.converter.fetch_chapter(chapter)
            if isinstance(result, dict):
                sections = list(result.values())
            elif result:
                sections = list(result)

        return sections

    def run(self) -> dict[str, int]:
        """Run the pipeline for this state.

        Returns:
            Stats dict with sections_found, raw_uploaded, akn_uploaded, errors
        """
        print(f"\n{'='*60}")
        print(f"Processing {self.state.upper()}")
        print(f"{'='*60}")

        if self.dry_run:
            print("DRY RUN - no uploads will be performed")

        # Load converter
        try:
            self.converter = self._load_converter()
        except Exception as e:
            print(f"ERROR: Could not load converter: {e}")
            return self.stats

        print(f"Converter: {type(self.converter).__name__}")

        # Get chapters to process
        chapters = self._get_chapters()
        print(f"Found {len(chapters)} chapters/titles to process")

        if not chapters:
            print("No chapters found - check converter configuration")
            return self.stats

        # Process each chapter
        for chapter_num, title_or_code in chapters:
            display_name = (
                f"{title_or_code}-{chapter_num}" if title_or_code else str(chapter_num)
            )
            print(f"\n  Chapter {display_name}...", end=" ", flush=True)

            try:
                # 1. Get chapter URL and fetch raw HTML
                url = self._get_chapter_url(chapter_num, title_or_code)
                raw_html = self._fetch_raw_html(url)

                # 2. Archive raw HTML to R2 arch bucket (chapter level)
                safe_chapter = display_name.replace("/", "-").replace(".", "-")
                raw_key = f"us/statutes/states/{self.state}/raw/chapter-{safe_chapter}.html"

                if raw_html and not self.dry_run:
                    self.r2_arch.upload_raw(
                        raw_key,
                        raw_html,
                        metadata={
                            "source-url": url[:256],
                            "state": self.state,
                            "chapter": display_name,
                            "fetched-at": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                    self.stats["raw_uploaded"] += 1

                # 3. Parse into sections
                sections = self._get_sections(chapter_num, title_or_code)

                if not sections:
                    print("no sections")
                    continue

                print(f"{len(sections)} sections")
                self.stats["sections_found"] += len(sections)

                # 4. Convert each section to AKN and upload
                for section in sections:
                    section_id = (
                        section.citation.section
                        if hasattr(section.citation, "section")
                        else str(section.citation)
                    )
                    safe_id = section_id.replace("/", "-").replace(".", "-")

                    try:
                        # Convert to AKN
                        akn_xml = section_to_akn_xml(section, self.state)

                        # Upload AKN to rules-xml bucket
                        akn_key = f"us/statutes/states/{self.state}/{safe_id}.xml"

                        if not self.dry_run:
                            self.r2_rules.upload_raw(
                                akn_key,
                                akn_xml,
                                metadata={
                                    "raw-key": raw_key,
                                    "state": self.state,
                                    "section-id": section_id,
                                    "chapter": display_name,
                                },
                            )
                        self.stats["akn_uploaded"] += 1

                    except Exception as e:
                        print(f"    ERROR {section_id}: {e}")
                        self.stats["errors"] += 1

                # Rate limiting between chapters
                time.sleep(0.5)

            except Exception as e:
                print(f"ERROR: {e}")
                self.stats["errors"] += 1

        return self.stats
