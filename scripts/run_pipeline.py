#!/usr/bin/env python3
"""Run the full statute pipeline: fetch → R2 arch → convert → R2 rules-xml.

Usage:
    python scripts/run_pipeline.py --state ak
    python scripts/run_pipeline.py --state ak --dry-run
    python scripts/run_pipeline.py --all-states
"""

import argparse
import asyncio
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

from atlas.storage.r2 import get_r2_arch, get_r2_rules_xml


# State converter imports - we'll dynamically import based on state
STATE_CONVERTERS = {
    'ak': 'arch.converters.us_states.ak',
    'al': 'arch.converters.us_states.al',
    'ar': 'arch.converters.us_states.ar',
    'az': 'arch.converters.us_states.az',
    'ca': 'arch.converters.us_states.ca',
    'co': 'arch.converters.us_states.co',
    'ct': 'arch.converters.us_states.ct',
    'fl': 'arch.converters.us_states.fl',
    'hi': 'arch.converters.us_states.hi',
    'id': 'arch.converters.us_states.id_',
    'il': 'arch.converters.us_states.il',
    'in': 'arch.converters.us_states.in_',
    'ks': 'arch.converters.us_states.ks',
    'ky': 'arch.converters.us_states.ky',
    'la': 'arch.converters.us_states.la',
    'ma': 'arch.converters.us_states.ma',
    'md': 'arch.converters.us_states.md',
    'me': 'arch.converters.us_states.me',
    'mi': 'arch.converters.us_states.mi',
    'mn': 'arch.converters.us_states.mn',
    'mo': 'arch.converters.us_states.mo',
    'ms': 'arch.converters.us_states.ms',
    'mt': 'arch.converters.us_states.mt',
    'nc': 'arch.converters.us_states.nc',
    'nd': 'arch.converters.us_states.nd',
    'ne': 'arch.converters.us_states.ne',
    'nh': 'arch.converters.us_states.nh',
    'nj': 'arch.converters.us_states.nj',
    'nm': 'arch.converters.us_states.nm',
    'nv': 'arch.converters.us_states.nv',
    'ny': 'arch.converters.us_states.ny',
    'oh': 'arch.converters.us_states.oh',
    'ok': 'arch.converters.us_states.ok',
    'or': 'arch.converters.us_states.or_',
    'pa': 'arch.converters.us_states.pa',
    'ri': 'arch.converters.us_states.ri',
    'sc': 'arch.converters.us_states.sc',
    'sd': 'arch.converters.us_states.sd',
    'tn': 'arch.converters.us_states.tn',
    'tx': 'arch.converters.us_states.tx',
    'ut': 'arch.converters.us_states.ut',
    'va': 'arch.converters.us_states.va',
    'vt': 'arch.converters.us_states.vt',
    'wa': 'arch.converters.us_states.wa',
    'wi': 'arch.converters.us_states.wi',
    'wv': 'arch.converters.us_states.wv',
    'wy': 'arch.converters.us_states.wy',
}


def section_to_akn_xml(section, state: str) -> str:
    """Convert a Section model to Akoma Ntoso XML."""
    from xml.etree import ElementTree as ET
    from xml.dom import minidom
    from datetime import date

    AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
    ET.register_namespace("", AKN_NS)

    # Get section identifier
    section_id = section.citation.section if hasattr(section.citation, 'section') else str(section.citation)

    # Create root
    akomaNtoso = ET.Element(f"{{{AKN_NS}}}akomaNtoso")
    act = ET.SubElement(akomaNtoso, f"{{{AKN_NS}}}act")
    act.set("name", "section")

    # Meta
    meta = ET.SubElement(act, f"{{{AKN_NS}}}meta")
    identification = ET.SubElement(meta, f"{{{AKN_NS}}}identification")
    identification.set("source", f"#{state}-legislature")

    # FRBRWork
    work = ET.SubElement(identification, f"{{{AKN_NS}}}FRBRWork")
    work_this = ET.SubElement(work, f"{{{AKN_NS}}}FRBRthis")
    work_this.set("value", f"/akn/us-{state}/act/statute/sec-{section_id}")
    work_uri = ET.SubElement(work, f"{{{AKN_NS}}}FRBRuri")
    work_uri.set("value", f"/akn/us-{state}/act/statute/sec-{section_id}")
    work_date = ET.SubElement(work, f"{{{AKN_NS}}}FRBRdate")
    work_date.set("date", str(date.today()))
    work_date.set("name", "enacted")
    work_author = ET.SubElement(work, f"{{{AKN_NS}}}FRBRauthor")
    work_author.set("href", f"#{state}-legislature")
    work_country = ET.SubElement(work, f"{{{AKN_NS}}}FRBRcountry")
    work_country.set("value", f"us-{state}")

    # FRBRExpression
    expr = ET.SubElement(identification, f"{{{AKN_NS}}}FRBRExpression")
    expr_this = ET.SubElement(expr, f"{{{AKN_NS}}}FRBRthis")
    expr_this.set("value", f"/akn/us-{state}/act/statute/sec-{section_id}/eng@{date.today().isoformat()}")
    expr_uri = ET.SubElement(expr, f"{{{AKN_NS}}}FRBRuri")
    expr_uri.set("value", f"/akn/us-{state}/act/statute/sec-{section_id}/eng@{date.today().isoformat()}")
    expr_date = ET.SubElement(expr, f"{{{AKN_NS}}}FRBRdate")
    expr_date.set("date", str(date.today()))
    expr_date.set("name", "publication")
    expr_author = ET.SubElement(expr, f"{{{AKN_NS}}}FRBRauthor")
    expr_author.set("href", "#rules-foundation")
    expr_lang = ET.SubElement(expr, f"{{{AKN_NS}}}FRBRlanguage")
    expr_lang.set("language", "eng")

    # FRBRManifestation
    manif = ET.SubElement(identification, f"{{{AKN_NS}}}FRBRManifestation")
    manif_this = ET.SubElement(manif, f"{{{AKN_NS}}}FRBRthis")
    manif_this.set("value", f"/akn/us-{state}/act/statute/sec-{section_id}/eng@{date.today().isoformat()}/main.xml")
    manif_uri = ET.SubElement(manif, f"{{{AKN_NS}}}FRBRuri")
    manif_uri.set("value", f"/akn/us-{state}/act/statute/sec-{section_id}/eng@{date.today().isoformat()}/main.xml")
    manif_date = ET.SubElement(manif, f"{{{AKN_NS}}}FRBRdate")
    manif_date.set("date", str(date.today()))
    manif_date.set("name", "generation")
    manif_author = ET.SubElement(manif, f"{{{AKN_NS}}}FRBRauthor")
    manif_author.set("href", "#rules-foundation")

    # References
    references = ET.SubElement(meta, f"{{{AKN_NS}}}references")
    references.set("source", "#rules-foundation")
    org = ET.SubElement(references, f"{{{AKN_NS}}}TLCOrganization")
    org.set("eId", "rules-foundation")
    org.set("href", "https://rules.foundation")
    org.set("showAs", "Rules Foundation")

    # Body
    body = ET.SubElement(act, f"{{{AKN_NS}}}body")
    sec_elem = ET.SubElement(body, f"{{{AKN_NS}}}section")
    sec_elem.set("eId", f"sec_{section_id.replace('.', '_').replace('-', '_')}")

    # Section number
    num = ET.SubElement(sec_elem, f"{{{AKN_NS}}}num")
    num.text = section_id

    # Section heading
    if section.section_title:
        heading = ET.SubElement(sec_elem, f"{{{AKN_NS}}}heading")
        heading.text = section.section_title

    # Content
    if section.text:
        content = ET.SubElement(sec_elem, f"{{{AKN_NS}}}content")
        for para in section.text.split("\n\n"):
            if para.strip():
                p = ET.SubElement(content, f"{{{AKN_NS}}}p")
                p.text = para.strip()[:10000]

    # Pretty print
    xml_str = ET.tostring(akomaNtoso, encoding="unicode")
    try:
        dom = minidom.parseString(xml_str)
        pretty = dom.toprettyxml(indent="  ", encoding="UTF-8")
        lines = pretty.decode("utf-8").split("\n")
        return "\n".join(line for line in lines if line.strip())
    except:
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str


class StatePipeline:
    """Pipeline for processing a single state's statutes."""

    def __init__(self, state: str, dry_run: bool = False):
        self.state = state.lower()
        self.dry_run = dry_run
        self.r2_arch = get_r2_arch()
        self.r2_rules = get_r2_rules_xml()
        self.converter = None
        self.stats = {
            'sections_found': 0,
            'raw_uploaded': 0,
            'akn_uploaded': 0,
            'errors': 0,
        }

    def _load_converter(self):
        """Dynamically load the state converter."""
        import importlib
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
            if name.endswith('Converter') and name != 'Converter':
                return getattr(module, name)()

        raise ValueError(f"No converter class found in {module_path}")

    def process_section(self, section, raw_html: str, source_url: str) -> bool:
        """Process a single section: archive raw + convert + upload AKN."""
        section_id = section.citation.section if hasattr(section.citation, 'section') else str(section.citation)
        safe_id = section_id.replace('/', '-').replace('.', '-')

        try:
            # 1. Upload raw HTML to arch bucket
            raw_key = f"us/statutes/states/{self.state}/raw/{safe_id}.html"
            raw_hash = hashlib.sha256(raw_html.encode()).hexdigest()[:16]

            if not self.dry_run:
                self.r2_arch.upload_raw(
                    raw_key,
                    raw_html,
                    metadata={
                        'source-url': source_url[:256],
                        'state': self.state,
                        'section-id': section_id,
                        'fetched-at': datetime.now(timezone.utc).isoformat(),
                    }
                )
            self.stats['raw_uploaded'] += 1

            # 2. Convert to AKN XML
            akn_xml = section_to_akn_xml(section, self.state)
            akn_hash = hashlib.sha256(akn_xml.encode()).hexdigest()[:16]

            # 3. Upload AKN to rules-xml bucket
            akn_key = f"us/statutes/states/{self.state}/{safe_id}.xml"

            if not self.dry_run:
                self.r2_rules.upload_raw(
                    akn_key,
                    akn_xml,
                    metadata={
                        'raw-key': raw_key,
                        'raw-hash': raw_hash,
                        'state': self.state,
                        'section-id': section_id,
                    }
                )
            self.stats['akn_uploaded'] += 1

            return True

        except Exception as e:
            print(f"    ERROR processing {section_id}: {e}")
            self.stats['errors'] += 1
            return False

    def _get_chapter_url(self, chapter, title: int | None = None) -> str:
        """Get the URL for a chapter."""
        if hasattr(self.converter, '_build_chapter_url'):
            # Check how many arguments the method takes
            import inspect
            sig = inspect.signature(self.converter._build_chapter_url)
            params = list(sig.parameters.keys())
            if len(params) == 2 and title is not None:
                # AK-style: _build_chapter_url(title, chapter)
                return self.converter._build_chapter_url(title, chapter)
            elif len(params) == 1:
                return self.converter._build_chapter_url(chapter)
            else:
                # Fall back to just chapter if title not provided
                return self.converter._build_chapter_url(chapter) if len(params) == 1 else f"https://{self.state}.gov/statute/chapter/{chapter}"
        elif hasattr(self.converter, 'base_url'):
            return f"{self.converter.base_url}/chapter/{chapter}"
        else:
            return f"https://{self.state}.gov/statute/chapter/{chapter}"

    def _fetch_raw_html(self, url: str) -> str:
        """Fetch raw HTML from URL using converter's HTTP client."""
        if hasattr(self.converter, '_get'):
            return self.converter._get(url)
        elif hasattr(self.converter, 'client'):
            response = self.converter.client.get(url)
            return response.text
        else:
            import httpx
            response = httpx.get(url, follow_redirects=True, timeout=30)
            return response.text

    def run(self):
        """Run the pipeline for this state."""
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

        # Get sections to process
        module = type(self.converter).__module__
        import importlib
        mod = importlib.import_module(module)

        # chapters will be list of (chapter, title) tuples for states like AK that need both
        # or just (chapter, None) for simpler states
        chapters = []

        # Check for state-specific chapter dicts that map to titles/codes
        if self.state == 'ak':
            # Alaska uses separate dicts per title
            if hasattr(mod, 'AK_TAX_CHAPTERS'):
                for ch in getattr(mod, 'AK_TAX_CHAPTERS').keys():
                    chapters.append((ch, 43))  # Title 43 = Revenue and Taxation
            if hasattr(mod, 'AK_WELFARE_CHAPTERS'):
                for ch in getattr(mod, 'AK_WELFARE_CHAPTERS').keys():
                    chapters.append((ch, 47))  # Title 47 = Welfare
        elif self.state == 'tx':
            # Texas uses code + chapter: TX_TAX_CHAPTERS are Tax Code, TX_WELFARE_CHAPTERS are HR Code
            if hasattr(mod, 'TX_TAX_CHAPTERS'):
                for ch in getattr(mod, 'TX_TAX_CHAPTERS').keys():
                    chapters.append((ch, 'TX'))  # TX = Tax Code
            if hasattr(mod, 'TX_WELFARE_CHAPTERS'):
                for ch in getattr(mod, 'TX_WELFARE_CHAPTERS').keys():
                    chapters.append((ch, 'HR'))  # HR = Human Resources Code
        else:
            # Standard pattern for other states
            for attr in ['TAX_CHAPTERS', 'WELFARE_CHAPTERS', f'{self.state.upper()}_TAX_CHAPTERS', f'{self.state.upper()}_WELFARE_CHAPTERS']:
                if hasattr(mod, attr):
                    for ch in getattr(mod, attr).keys():
                        chapters.append((ch, None))

            if not chapters:
                print("No chapters found, trying title-based approach...")
                for attr in ['TITLES', f'{self.state.upper()}_TITLES', 'TAX_TITLES']:
                    if hasattr(mod, attr):
                        for t in getattr(mod, attr).keys():
                            chapters.append((str(t), None))

        print(f"Found {len(chapters)} chapters/titles to process")

        # Process each chapter
        for chapter_tuple in chapters:
            chapter_num, title_or_code = chapter_tuple
            display_name = f"{title_or_code}-{chapter_num}" if title_or_code else str(chapter_num)
            print(f"\n  Chapter {display_name}...", end=" ", flush=True)

            try:
                # 1. Get chapter URL and fetch raw HTML
                url = self._get_chapter_url(chapter_num, title_or_code)
                raw_html = self._fetch_raw_html(url)

                # 2. Archive raw HTML to R2 arch bucket (chapter level)
                safe_chapter = display_name.replace('/', '-').replace('.', '-')
                raw_key = f"us/statutes/states/{self.state}/raw/chapter-{safe_chapter}.html"

                if not self.dry_run:
                    self.r2_arch.upload_raw(
                        raw_key,
                        raw_html,
                        metadata={
                            'source-url': url[:256],
                            'state': self.state,
                            'chapter': display_name,
                            'fetched-at': datetime.now(timezone.utc).isoformat(),
                        }
                    )
                self.stats['raw_uploaded'] += 1

                # 3. Parse into sections - AK/TX use iter_chapter(title/code, chapter)
                if self.state == 'ak' and title_or_code:
                    # Alaska converter uses iter_chapter(title, chapter)
                    sections = list(self.converter.iter_chapter(title_or_code, chapter_num))
                elif self.state == 'tx' and title_or_code:
                    # Texas converter uses iter_chapter(code, chapter) not fetch_chapter
                    sections = list(self.converter.iter_chapter(title_or_code, chapter_num))
                elif hasattr(self.converter, 'fetch_chapter'):
                    sections = self.converter.fetch_chapter(chapter_num)
                    if isinstance(sections, dict):
                        sections = list(sections.values())
                else:
                    print("SKIP (no fetch_chapter method)")
                    continue

                if not sections:
                    print("no sections")
                    continue

                print(f"{len(sections)} sections")
                self.stats['sections_found'] += len(sections)

                # 4. Convert each section to AKN and upload
                for section in sections:
                    section_id = section.citation.section if hasattr(section.citation, 'section') else str(section.citation)
                    safe_id = section_id.replace('/', '-').replace('.', '-')

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
                                    'raw-key': raw_key,
                                    'state': self.state,
                                    'section-id': section_id,
                                    'chapter': display_name,
                                }
                            )
                        self.stats['akn_uploaded'] += 1

                    except Exception as e:
                        print(f"    ERROR {section_id}: {e}")
                        self.stats['errors'] += 1

                # Rate limiting between chapters
                time.sleep(0.5)

            except Exception as e:
                print(f"ERROR: {e}")
                self.stats['errors'] += 1

        return self.stats


def main():
    parser = argparse.ArgumentParser(description="Run statute pipeline")
    parser.add_argument("--state", help="State code (e.g., ak, ny)")
    parser.add_argument("--all-states", action="store_true", help="Process all states")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually upload")
    args = parser.parse_args()

    if args.all_states:
        states = list(STATE_CONVERTERS.keys())
    elif args.state:
        states = [args.state.lower()]
    else:
        print("Specify --state or --all-states")
        return

    total_stats = {
        'sections_found': 0,
        'raw_uploaded': 0,
        'akn_uploaded': 0,
        'errors': 0,
    }

    for state in states:
        pipeline = StatePipeline(state, dry_run=args.dry_run)
        stats = pipeline.run()

        for k, v in stats.items():
            total_stats[k] += v

        print(f"\n  {state.upper()} Stats:")
        print(f"    Sections found: {stats['sections_found']}")
        print(f"    Raw uploaded:   {stats['raw_uploaded']}")
        print(f"    AKN uploaded:   {stats['akn_uploaded']}")
        print(f"    Errors:         {stats['errors']}")

    print(f"\n{'='*60}")
    print("TOTAL STATS:")
    print(f"  Sections found: {total_stats['sections_found']}")
    print(f"  Raw uploaded:   {total_stats['raw_uploaded']}")
    print(f"  AKN uploaded:   {total_stats['akn_uploaded']}")
    print(f"  Errors:         {total_stats['errors']}")


if __name__ == "__main__":
    main()
