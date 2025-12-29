"""Ingest parsed statutes into Supabase rules table.

This module pushes parsed statute sections to the PostgreSQL `rules` table
via the Supabase REST API.

Usage:
    from arch.ingest.supabase import SupabaseIngestor

    ingestor = SupabaseIngestor()
    ingestor.ingest_canada_act("I-3.3")
"""

import os
from datetime import date
from pathlib import Path
from typing import Iterator
from uuid import uuid4

import httpx

from arch.parsers.canada import CanadaStatuteParser
from arch.models_canada import CanadaSection, CanadaSubsection


class SupabaseIngestor:
    """Ingest parsed statutes into Supabase rules table."""

    def __init__(
        self,
        url: str | None = None,
        key: str | None = None,
    ):
        """Initialize with Supabase credentials.

        Args:
            url: Supabase project URL (or COSILICO_SUPABASE_URL env var)
            key: Supabase service role key (or from Management API)
        """
        self.url = url or os.environ.get(
            "COSILICO_SUPABASE_URL",
            "https://nsupqhfchdtqclomlrgs.supabase.co",
        )
        # Get service role key from Management API if not provided
        self.key = key or self._get_service_key()
        self.rest_url = f"{self.url}/rest/v1"

    def _get_service_key(self) -> str:
        """Get service role key from Supabase Management API."""
        access_token = os.environ.get("SUPABASE_ACCESS_TOKEN")
        if not access_token:
            raise ValueError(
                "SUPABASE_ACCESS_TOKEN env var required to get service key"
            )

        # Extract project ref from URL
        project_ref = self.url.split("//")[1].split(".")[0]

        with httpx.Client() as client:
            response = client.get(
                f"https://api.supabase.com/v1/projects/{project_ref}/api-keys",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            keys = response.json()

            # Find service_role key
            for key in keys:
                if key.get("name") == "service_role" and key.get("api_key"):
                    return key["api_key"]

        raise ValueError("Could not find service_role key")

    def _insert_rules(self, rules: list[dict]) -> int:
        """Insert rules into Supabase.

        Args:
            rules: List of rule dictionaries

        Returns:
            Number of rows inserted
        """
        if not rules:
            return 0

        with httpx.Client() as client:
            response = client.post(
                f"{self.rest_url}/rules",
                headers={
                    "apikey": self.key,
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json=rules,
            )
            response.raise_for_status()

        return len(rules)

    def _section_to_rules(
        self,
        section: CanadaSection,
        parent_id: str | None = None,
    ) -> Iterator[dict]:
        """Convert a CanadaSection to rule dictionaries.

        Yields rule dicts for the section and all its subsections.
        """
        section_id = str(uuid4())

        # Section-level rule
        yield {
            "id": section_id,
            "jurisdiction": "canada",
            "doc_type": "statute",
            "parent_id": parent_id,
            "level": 0,
            "ordinal": int(section.section_number.split(".")[0]) if section.section_number.replace(".", "").isdigit() else None,
            "heading": section.marginal_note,
            "body": section.text,
            "effective_date": section.in_force_date.isoformat() if section.in_force_date else None,
            "source_url": section.source_url,
            "source_path": section.source_path,
            "rac_path": None,
            "has_rac": False,
        }

        # Recursively yield subsections
        yield from self._subsections_to_rules(
            section.subsections,
            parent_id=section_id,
            level=1,
        )

    def _subsections_to_rules(
        self,
        subsections: list[CanadaSubsection],
        parent_id: str,
        level: int,
    ) -> Iterator[dict]:
        """Convert subsections to rule dictionaries recursively."""
        for i, sub in enumerate(subsections):
            sub_id = str(uuid4())

            yield {
                "id": sub_id,
                "jurisdiction": "canada",
                "doc_type": "statute",
                "parent_id": parent_id,
                "level": level,
                "ordinal": i + 1,
                "heading": sub.marginal_note,
                "body": sub.text,
                "effective_date": None,
                "source_url": None,
                "source_path": None,
                "rac_path": None,
                "has_rac": False,
            }

            # Recursively handle children
            if sub.children:
                yield from self._subsections_to_rules(
                    sub.children,
                    parent_id=sub_id,
                    level=level + 1,
                )

    def ingest_canada_act(
        self,
        consolidated_number: str,
        arch_path: Path | None = None,
        batch_size: int = 100,
    ) -> int:
        """Ingest a Canadian federal act into the rules table.

        Args:
            consolidated_number: e.g., "I-3.3" for Income Tax Act
            arch_path: Path to arch directory (default ~/.arch)
            batch_size: Number of rules to insert per batch

        Returns:
            Total number of rules inserted
        """
        if arch_path is None:
            arch_path = Path.home() / ".arch"

        xml_path = arch_path / "canada" / f"{consolidated_number}.xml"
        if not xml_path.exists():
            raise FileNotFoundError(f"Not found: {xml_path}")

        parser = CanadaStatuteParser(xml_path)
        total_inserted = 0
        batch: list[dict] = []

        print(f"Ingesting {consolidated_number}...")

        for section in parser.iter_sections():
            for rule in self._section_to_rules(section):
                batch.append(rule)

                if len(batch) >= batch_size:
                    inserted = self._insert_rules(batch)
                    total_inserted += inserted
                    print(f"  Inserted {total_inserted} rules...")
                    batch = []

        # Insert remaining
        if batch:
            inserted = self._insert_rules(batch)
            total_inserted += inserted

        print(f"Done! Inserted {total_inserted} rules for {consolidated_number}")
        return total_inserted

    def ingest_all_canada(
        self,
        arch_path: Path | None = None,
        limit: int | None = None,
    ) -> int:
        """Ingest all Canadian federal acts.

        Args:
            arch_path: Path to arch directory
            limit: Max number of acts to process (for testing)

        Returns:
            Total number of rules inserted
        """
        if arch_path is None:
            arch_path = Path.home() / ".arch"

        canada_path = arch_path / "canada"
        xml_files = sorted(canada_path.glob("*.xml"))

        if limit:
            xml_files = xml_files[:limit]

        total = 0
        for xml_file in xml_files:
            cons_num = xml_file.stem
            try:
                count = self.ingest_canada_act(cons_num, arch_path)
                total += count
            except Exception as e:
                print(f"Error ingesting {cons_num}: {e}")

        return total
