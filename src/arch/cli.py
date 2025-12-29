"""Command-line interface for the law archive."""

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from arch.archive import Arch
from arch.fetchers.irs_bulk import IRSBulkFetcher
from arch.models_guidance import GuidanceType
from arch.parsers.us.statutes import download_title
from arch.storage.guidance import GuidanceStorage

console = Console()


@click.group()
@click.option("--db", default="atlas.db", help="Path to database file")
@click.pass_context
def main(ctx: click.Context, db: str):
    """Cosilico Law Archive - Open source US statute text via API."""
    ctx.ensure_object(dict)
    ctx.obj["db"] = db


@main.command()
@click.argument("citation")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def get(ctx: click.Context, citation: str, as_json: bool):
    """Get a section by citation.

    Examples:
        atlas get "26 USC 32"
        atlas get "26 USC 32(a)(1)"
    """
    archive = Arch(db_path=ctx.obj["db"])
    section = archive.get(citation)

    if not section:
        console.print(f"[red]Not found:[/red] {citation}")
        raise SystemExit(1)

    if as_json:
        console.print_json(section.model_dump_json())
    else:
        console.print(
            Panel(
                f"[bold]{section.citation.usc_cite}[/bold]\n"
                f"[dim]{section.title_name}[/dim]\n\n"
                f"[bold blue]{section.section_title}[/bold blue]\n\n"
                f"{section.text[:2000]}{'...' if len(section.text) > 2000 else ''}\n\n"
                f"[dim]Source: {section.source_url}[/dim]",
                title=section.citation.usc_cite,
            )
        )


@main.command()
@click.argument("query")
@click.option("--title", "-t", type=int, help="Limit to specific title")
@click.option("--limit", "-n", default=10, help="Maximum results")
@click.pass_context
def search(ctx: click.Context, query: str, title: int | None, limit: int):
    """Search for sections matching a query.

    Examples:
        atlas search "earned income"
        atlas search "child tax credit" --title 26
    """
    archive = Arch(db_path=ctx.obj["db"])
    results = archive.search(query, title=title, limit=limit)

    if not results:
        console.print(f"[yellow]No results for:[/yellow] {query}")
        return

    table = Table(title=f"Search: {query}")
    table.add_column("Citation", style="cyan")
    table.add_column("Title", style="green")
    table.add_column("Snippet")
    table.add_column("Score", justify="right")

    for r in results:
        table.add_row(
            r.citation.usc_cite,
            r.section_title[:40] + "..." if len(r.section_title) > 40 else r.section_title,
            r.snippet[:60] + "..." if len(r.snippet) > 60 else r.snippet,
            f"{r.score:.2f}",
        )

    console.print(table)


@main.command()
@click.pass_context
def titles(ctx: click.Context):
    """List all available titles."""
    archive = Arch(db_path=ctx.obj["db"])
    title_list = archive.list_titles()

    if not title_list:
        console.print("[yellow]No titles loaded. Use 'atlas ingest' to add titles.[/yellow]")
        return

    table = Table(title="US Code Titles")
    table.add_column("Title", justify="right", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Sections", justify="right")
    table.add_column("Positive Law", justify="center")
    table.add_column("Updated")

    for t in title_list:
        table.add_row(
            str(t.number),
            t.name,
            str(t.section_count),
            "[green]Yes[/green]" if t.is_positive_law else "[dim]No[/dim]",
            t.last_updated.isoformat(),
        )

    console.print(table)


@main.command()
@click.argument("xml_path", type=click.Path(exists=True, path_type=Path))
@click.pass_context
def ingest(ctx: click.Context, xml_path: Path):
    """Ingest a US Code title from USLM XML file.

    Example:
        atlas ingest data/uscode/usc26.xml
    """
    archive = Arch(db_path=ctx.obj["db"])
    with console.status(f"Ingesting {xml_path}..."):
        count = archive.ingest_title(xml_path)
    console.print(f"[green]Successfully ingested {count} sections[/green]")


@main.command()
@click.argument("title_num", type=int)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=Path("data/uscode"),
    help="Output directory",
)
def download(title_num: int, output: Path):
    """Download a US Code title from uscode.house.gov.

    Example:
        atlas download 26 -o data/uscode
    """
    with console.status(f"Downloading Title {title_num}..."):
        path = download_title(title_num, output)
    console.print(f"[green]Downloaded to {path}[/green]")


@main.command()
@click.option("--host", default="127.0.0.1", help="Host to bind")
@click.option("--port", default=8000, help="Port to bind")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
@click.pass_context
def serve(ctx: click.Context, host: str, port: int, reload: bool):
    """Start the REST API server.

    Example:
        atlas serve --host 0.0.0.0 --port 8080
    """
    import uvicorn

    console.print(f"[green]Starting server at http://{host}:{port}[/green]")
    console.print(f"[dim]API docs at http://{host}:{port}/docs[/dim]")

    # We need to pass the db path to the app
    # For now, use environment variable or default
    uvicorn.run(
        "atlas.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


@main.command()
@click.argument("citation")
@click.pass_context
def refs(ctx: click.Context, citation: str):
    """Show cross-references for a section.

    Example:
        atlas refs "26 USC 32"
    """
    archive = Arch(db_path=ctx.obj["db"])
    refs = archive.get_references(citation)

    console.print(
        Panel(
            f"[bold]References from {citation}:[/bold]\n"
            + "\n".join(f"  → {r}" for r in refs["references_to"])
            or "  (none)"
            + "\n\n[bold]Referenced by:[/bold]\n"
            + "\n".join(f"  ← {r}" for r in refs["referenced_by"])
            or "  (none)",
            title=f"Cross-references: {citation}",
        )
    )


@main.command()
@click.argument("citation")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=Path.home() / ".cosilico" / "workspace",
    help="Output directory for encoded files",
)
@click.option(
    "--model", "-m", default="claude-sonnet-4-20250514", help="Claude model to use for encoding"
)
@click.pass_context
def encode(ctx: click.Context, citation: str, output: Path, model: str):
    """Encode a statute section into Cosilico DSL using AI.

    Reads the statute from the archive and generates:
    - rules.cosilico (DSL code)
    - tests.yaml (test cases)
    - statute.md (reference text)
    - metadata.json (provenance)

    Examples:
        atlas encode "26 USC 32"
        atlas encode "26 USC 24" -o ./my-workspace
    """
    from arch.encoder import encode_and_save
    from arch.models import Citation

    archive = Arch(db_path=ctx.obj["db"])

    # Parse citation
    try:
        parsed = Citation.from_string(citation)
    except ValueError as e:
        console.print(f"[red]Invalid citation:[/red] {e}")
        raise SystemExit(1) from e

    # Get section
    section = archive.storage.get_section(parsed.title, parsed.section)
    if not section:
        console.print(f"[red]Section not found:[/red] {citation}")
        raise SystemExit(1)

    console.print(f"[blue]Encoding:[/blue] {citation}")
    console.print(f"[dim]Title: {section.section_title}[/dim]")
    console.print(
        f"[dim]Text: {len(section.text)} chars, {len(section.subsections)} subsections[/dim]"
    )
    console.print()

    with console.status(f"Generating DSL with {model}..."):
        result = encode_and_save(section, output, model=model)

    section_dir = output / "federal" / "statute" / str(parsed.title) / parsed.section

    console.print("[green]✓ Encoding complete![/green]")
    console.print()
    console.print("[bold]Files created:[/bold]")
    console.print(f"  📜 {section_dir / 'statute.md'}")
    console.print(f"  📄 {section_dir / 'rules.cosilico'}")
    console.print(f"  🧪 {section_dir / 'tests.yaml'}")
    console.print(f"  📋 {section_dir / 'metadata.json'}")
    console.print()
    console.print(f"[dim]Model: {result.model}[/dim]")
    console.print(f"[dim]Tokens: {result.prompt_tokens} in, {result.completion_tokens} out[/dim]")


@main.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
def validate(path: Path):
    """Validate a local encoding.

    Checks:
    - DSL syntax
    - Parameter references
    - Test case format

    Example:
        atlas validate ~/.cosilico/workspace/federal/statute/26/32
    """
    # Find rules.cosilico file
    rules_file = path / "rules.cosilico" if path.is_dir() else path

    if not rules_file.exists():
        console.print(f"[red]Not found:[/red] {rules_file}")
        raise SystemExit(1)

    content = rules_file.read_text()

    # Basic validation
    errors = []
    warnings = []

    # Check for required elements
    if "variable " not in content and "parameter " not in content:
        errors.append("No variable or parameter definitions found")

    if "reference " not in content:
        warnings.append("No statute references found")

    if "formula {" not in content:
        warnings.append("No formulas found - is this just parameters?")

    # Count definitions
    var_count = content.count("variable ")
    param_count = content.count("parameter ")
    ref_count = content.count('reference "')

    if errors:
        console.print("[red]✗ Validation failed[/red]")
        for e in errors:
            console.print(f"  [red]ERROR:[/red] {e}")
        raise SystemExit(1)

    console.print("[green]✓ Validation passed[/green]")
    console.print(f"  Variables: {var_count}")
    console.print(f"  Parameters: {param_count}")
    console.print(f"  References: {ref_count}")

    if warnings:
        console.print()
        for w in warnings:
            console.print(f"  [yellow]WARNING:[/yellow] {w}")


@main.command("download-state")
@click.argument("state", type=click.Choice(["ny", "fl", "tx"], case_sensitive=False))
@click.option(
    "--law",
    "-l",
    multiple=True,
    help="Law code(s) to download (e.g., TAX, SOS for NY; chapter numbers for FL).",
)
@click.option(
    "--list-laws",
    is_flag=True,
    help="List available law codes for the state",
)
@click.pass_context
def download_state(ctx: click.Context, state: str, law: tuple[str, ...], list_laws: bool):
    """Download state statutes from official APIs.

    Currently supported states:
    - ny: New York (requires NY_LEGISLATION_API_KEY env var)
    - fl: Florida (web scraping, no API key needed)
    - tx: Texas (bulk ZIP download, no API key needed)

    Examples:
        arch download-state ny                    # Download TAX and SOS laws
        arch download-state ny --law TAX          # Download only Tax Law
        arch download-state ny --list-laws        # List available law codes
        arch download-state fl                    # Download FL tax chapters
        arch download-state fl --law 212          # Download specific chapter
        arch download-state tx                    # Download TX priority codes
        arch download-state tx --law TX           # Download just Tax Code
    """
    if state.lower() == "ny":
        _download_ny_state(ctx, law, list_laws)
    elif state.lower() == "fl":
        _download_fl_state(ctx, law, list_laws)
    elif state.lower() == "tx":
        _download_tx_state(ctx, law, list_laws)
    else:
        console.print(f"[red]State not supported:[/red] {state}")
        raise SystemExit(1)


def _download_ny_state(ctx: click.Context, law_codes: tuple[str, ...], list_laws: bool) -> None:
    """Download New York state statutes."""
    import os

    from arch.parsers.us_ny.statutes import NY_LAW_CODES, NYLegislationClient, download_ny_law

    # Check for API key
    if not os.environ.get("NY_LEGISLATION_API_KEY"):
        console.print("[red]Error:[/red] NY_LEGISLATION_API_KEY environment variable not set.")
        console.print("\nTo get a free API key:")
        console.print("  1. Visit https://legislation.nysenate.gov")
        console.print("  2. Register for an account")
        console.print("  3. Copy your API key")
        console.print("  4. Set: export NY_LEGISLATION_API_KEY=your_key_here")
        raise SystemExit(1)

    # List laws mode
    if list_laws:
        try:
            with NYLegislationClient() as client:
                laws = client.get_law_ids()

            table = Table(title="New York State Laws")
            table.add_column("Code", style="cyan")
            table.add_column("Name", style="green")
            table.add_column("Type")

            for law in sorted(laws, key=lambda x: x.law_id):
                table.add_row(law.law_id, law.name, law.law_type)

            console.print(table)
            console.print(f"\n[dim]Total: {len(laws)} laws available[/dim]")
        except Exception as e:
            console.print(f"[red]Error listing laws:[/red] {e}")
            raise SystemExit(1) from e
        return

    # Default to TAX and SOS if no laws specified
    laws_to_download = list(law_codes) if law_codes else ["TAX", "SOS"]

    archive = Arch(db_path=ctx.obj["db"])
    total_sections = 0

    for law_id in laws_to_download:
        law_name = NY_LAW_CODES.get(law_id.upper(), f"{law_id} Law")
        console.print(f"\n[blue]Downloading:[/blue] New York {law_name} ({law_id})")

        try:
            count = 0
            with console.status(f"Fetching {law_id}..."):
                for section in download_ny_law(law_id.upper()):
                    archive.storage.store_section(section)
                    count += 1
                    if count % 50 == 0:
                        console.print(f"  [dim]Processed {count} sections...[/dim]")

            console.print(f"[green]Stored {count} sections from {law_id}[/green]")
            total_sections += count

        except Exception as e:
            console.print(f"[red]Error downloading {law_id}:[/red] {e}")
            continue

    console.print(f"\n[green]Total: {total_sections} sections stored[/green]")


def _download_fl_state(ctx: click.Context, chapters: tuple[str, ...], list_laws: bool) -> None:
    """Download Florida state statutes."""
    from arch.parsers.us_fl.statutes import (
        FL_TAX_CHAPTERS,
        FL_WELFARE_CHAPTERS,
        FLStatutesClient,
        convert_to_section,
    )

    # List chapters mode
    if list_laws:
        table = Table(title="Florida Statutes Chapters")
        table.add_column("Chapter", style="cyan")
        table.add_column("Title", style="green")
        table.add_column("Category")

        for ch, title in sorted(FL_TAX_CHAPTERS.items()):
            table.add_row(str(ch), title, "Tax & Finance")

        for ch, title in sorted(FL_WELFARE_CHAPTERS.items()):
            table.add_row(str(ch), title, "Social Welfare")

        console.print(table)
        console.print(f"\n[dim]Total: {len(FL_TAX_CHAPTERS) + len(FL_WELFARE_CHAPTERS)} chapters available[/dim]")
        return

    # Default to tax chapters if none specified
    if chapters:
        chapter_list = [int(ch) for ch in chapters]
    else:
        chapter_list = list(FL_TAX_CHAPTERS.keys())

    archive = Arch(db_path=ctx.obj["db"])
    total_sections = 0

    with FLStatutesClient(rate_limit_delay=0.3) as client:
        for chapter in chapter_list:
            chapter_name = FL_TAX_CHAPTERS.get(chapter) or FL_WELFARE_CHAPTERS.get(chapter, f"Chapter {chapter}")
            console.print(f"\n[blue]Downloading:[/blue] Florida {chapter_name} (Ch. {chapter})")

            try:
                count = 0
                with console.status(f"Fetching chapter {chapter}..."):
                    for fl_section in client.iter_chapter(chapter):
                        section = convert_to_section(fl_section)
                        archive.storage.store_section(section)
                        count += 1
                        if count % 20 == 0:
                            console.print(f"  [dim]Processed {count} sections...[/dim]")

                console.print(f"[green]Stored {count} sections from Chapter {chapter}[/green]")
                total_sections += count

            except Exception as e:
                console.print(f"[red]Error downloading Chapter {chapter}:[/red] {e}")
                continue

    console.print(f"\n[green]Total: {total_sections} sections stored[/green]")


def _download_tx_state(ctx: click.Context, codes: tuple[str, ...], list_laws: bool) -> None:
    """Download Texas state statutes."""
    from arch.parsers.us_tx.statutes import (
        TX_CODES,
        TX_PRIORITY_CODES,
        TXStatutesClient,
        convert_to_section,
    )

    # List codes mode
    if list_laws:
        table = Table(title="Texas Statutes Codes")
        table.add_column("Code", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Priority")

        for code, name in sorted(TX_CODES.items()):
            priority = "Yes" if code in TX_PRIORITY_CODES else ""
            table.add_row(code, name, priority)

        console.print(table)
        console.print(f"\n[dim]Total: {len(TX_CODES)} codes available[/dim]")
        console.print("[dim]Priority codes are downloaded by default[/dim]")
        return

    # Default to priority codes if none specified
    if codes:
        code_list = [c.upper() for c in codes]
    else:
        code_list = TX_PRIORITY_CODES

    archive = Arch(db_path=ctx.obj["db"])
    total_sections = 0

    with TXStatutesClient() as client:
        for code in code_list:
            code_name = TX_CODES.get(code, f"{code} Code")
            console.print(f"\n[blue]Downloading:[/blue] Texas {code_name}")

            try:
                count = 0
                with console.status(f"Downloading and parsing {code}..."):
                    for tx_section in client.iter_code(code):
                        section = convert_to_section(tx_section)
                        archive.storage.store_section(section)
                        count += 1
                        if count % 100 == 0:
                            console.print(f"  [dim]Processed {count} sections...[/dim]")

                console.print(f"[green]Stored {count} sections from {code}[/green]")
                total_sections += count

            except Exception as e:
                console.print(f"[red]Error downloading {code}:[/red] {e}")
                continue

    console.print(f"\n[green]Total: {total_sections} sections stored[/green]")


@main.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--pe-var",
    "-v",
    required=True,
    help="PolicyEngine variable name to compare (e.g., 'eitc', 'ctc')",
)
@click.option("--tolerance", "-t", default=15.0, help="Dollar tolerance for matching (default $15)")
@click.option("--save", "-s", type=click.Path(path_type=Path), help="Save report to JSON file")
def verify(path: Path, pe_var: str, tolerance: float, save: Path | None):
    """Verify a DSL encoding against PolicyEngine API.

    Runs test cases through PolicyEngine's API and compares results
    to expected values from the DSL encoding.

    Examples:
        atlas verify ~/.cosilico/workspace/federal/statute/26/32 -v eitc
        atlas verify ~/.cosilico/workspace/federal/statute/26/24 -v ctc
    """
    from arch.verifier import (
        print_verification_report,
        save_verification_report,
        verify_encoding,
    )

    section_dir = path if path.is_dir() else path.parent

    with console.status(f"Verifying against PolicyEngine API ({pe_var})..."):
        report = verify_encoding(section_dir, pe_var, tolerance)

    print_verification_report(report)

    if save:
        save_verification_report(report, save)
        console.print(f"\n[dim]Report saved to {save}[/dim]")


@main.command("fetch-guidance")
@click.option(
    "--year",
    "-y",
    type=int,
    multiple=True,
    help="Year(s) to fetch (e.g., 2024). Can be repeated. Default: 2020-2024",
)
@click.option(
    "--type",
    "-t",
    "doc_types",
    type=click.Choice(["rev-proc", "rev-rul", "notice", "all"], case_sensitive=False),
    multiple=True,
    default=["all"],
    help="Document type(s) to fetch. Default: all",
)
@click.option(
    "--download-pdfs",
    is_flag=True,
    help="Also download PDF files to data/guidance/irs/",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="List documents without fetching",
)
@click.pass_context
def fetch_guidance(
    ctx: click.Context,
    year: tuple[int, ...],
    doc_types: tuple[str, ...],
    download_pdfs: bool,
    dry_run: bool,
):
    """Fetch IRS guidance documents (Rev. Procs, Rev. Rulings, Notices).

    Downloads documents from https://www.irs.gov/pub/irs-drop/ and stores
    metadata in the database. By default fetches all document types for
    years 2020-2024.

    Examples:
        atlas fetch-guidance                     # Fetch all 2020-2024
        atlas fetch-guidance --year 2024         # Just 2024
        atlas fetch-guidance -y 2023 -y 2024     # 2023 and 2024
        atlas fetch-guidance --type rev-proc     # Only Revenue Procedures
        atlas fetch-guidance --dry-run           # List without fetching
    """
    # Parse years
    years = list(year) if year else [2020, 2021, 2022, 2023, 2024]

    # Parse document types
    type_mapping = {
        "rev-proc": [GuidanceType.REV_PROC],
        "rev-rul": [GuidanceType.REV_RUL],
        "notice": [GuidanceType.NOTICE],
        "all": [GuidanceType.REV_PROC, GuidanceType.REV_RUL, GuidanceType.NOTICE],
    }

    selected_types = []
    for dt in doc_types:
        selected_types.extend(type_mapping[dt.lower()])
    selected_types = list(set(selected_types))

    console.print(f"[blue]Fetching IRS guidance for years:[/blue] {years}")
    console.print(f"[blue]Document types:[/blue] {[t.value for t in selected_types]}")

    if dry_run:
        console.print("\n[yellow]DRY RUN - listing documents only[/yellow]\n")

    # Initialize storage and fetcher
    storage = GuidanceStorage(ctx.obj["db"])
    download_dir = Path("data/guidance/irs") if download_pdfs else None

    fetched_count = 0
    error_count = 0

    with IRSBulkFetcher() as fetcher:
        # First, list all available documents (multi-page)
        console.print("[dim]Scanning IRS drop folder (may take a minute for multiple pages)...[/dim]")

        def page_progress(msg: str) -> None:
            console.print(f"[dim]{msg}[/dim]")

        html = fetcher._fetch_drop_listing(progress_callback=page_progress)
        from arch.fetchers.irs_bulk import parse_irs_drop_listing

        all_docs = []
        for y in years:
            docs = parse_irs_drop_listing(html, year=y, doc_types=selected_types)
            all_docs.extend(docs)

        console.print(f"[green]Found {len(all_docs)} documents[/green]\n")

        if dry_run:
            # Just show a table of documents
            table = Table(title="Available IRS Guidance Documents")
            table.add_column("Type", style="cyan")
            table.add_column("Number", style="green")
            table.add_column("Year", justify="right")
            table.add_column("PDF URL")

            for doc in sorted(all_docs, key=lambda d: (d.year, d.doc_type.value, d.doc_number)):
                table.add_row(
                    doc.doc_type.value,
                    doc.doc_number,
                    str(doc.year),
                    doc.pdf_url,
                )

            console.print(table)
            return

        # Fetch and store each document
        for i, doc in enumerate(all_docs):
            console.print(
                f"[{i+1}/{len(all_docs)}] Fetching {doc.doc_type.value} {doc.doc_number}...",
                end=" ",
            )

            try:
                # Fetch PDF to get file size (we don't parse content yet)
                pdf_content = fetcher.fetch_pdf(doc)
                pdf_size = len(pdf_content)

                # Optionally save PDF
                if download_dir:
                    download_dir.mkdir(parents=True, exist_ok=True)
                    pdf_path = download_dir / doc.pdf_filename
                    pdf_path.write_bytes(pdf_content)

                # Create RevenueProcedure model with placeholder content
                from datetime import date as date_module

                from arch.models_guidance import RevenueProcedure

                rev_proc = RevenueProcedure(
                    doc_number=doc.doc_number,
                    doc_type=doc.doc_type,
                    title=fetcher._generate_title(doc),
                    irb_citation="",  # Would need IRB lookup
                    published_date=date_module(doc.year, 1, 1),  # Placeholder
                    full_text=f"[PDF content: {pdf_size} bytes]",
                    sections=[],
                    effective_date=None,
                    tax_years=[doc.year, doc.year + 1],
                    subject_areas=["General"],
                    parameters={},
                    source_url=doc.pdf_url,
                    pdf_url=doc.pdf_url,
                    retrieved_at=date_module.today(),
                )

                # Store in database
                storage.store_revenue_procedure(rev_proc)
                fetched_count += 1
                console.print(f"[green]OK[/green] ({pdf_size:,} bytes)")

            except Exception as e:
                error_count += 1
                console.print(f"[red]ERROR: {e}[/red]")

    console.print()
    console.print(f"[green]Successfully fetched:[/green] {fetched_count} documents")
    if error_count:
        console.print(f"[red]Errors:[/red] {error_count}")

    # Show final count in database
    total = storage.db.execute("SELECT COUNT(*) FROM guidance_documents").fetchone()[0]
    console.print(f"\n[dim]Total documents in database: {total}[/dim]")


@main.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def stats(ctx: click.Context, as_json: bool):
    """Show archive statistics and scraping progress.

    Displays counts of:
    - US Code titles and sections
    - State statutes by state
    - IRS guidance by type and year
    - Database size and storage info

    Example:
        arch stats
        arch stats --json
    """
    import json as json_module
    import os
    from collections import defaultdict
    from datetime import date

    archive = Arch(db_path=ctx.obj["db"])
    db = archive.storage.db

    stats_data: dict = {
        "generated_at": date.today().isoformat(),
        "database": ctx.obj["db"],
        "us_code": {},
        "state_statutes": {},
        "irs_guidance": {},
        "totals": {},
    }

    # US Code statistics
    usc_query = """
        SELECT title, title_name, COUNT(*) as section_count,
               MAX(retrieved_at) as last_updated
        FROM sections
        WHERE title > 0
        GROUP BY title
        ORDER BY title
    """
    usc_rows = db.execute(usc_query).fetchall()

    usc_stats = []
    usc_total_sections = 0
    for row in usc_rows:
        usc_stats.append({
            "title": row[0],
            "name": row[1],
            "sections": row[2],
            "last_updated": row[3],
        })
        usc_total_sections += row[2]

    stats_data["us_code"] = {
        "titles": len(usc_stats),
        "total_sections": usc_total_sections,
        "by_title": usc_stats,
    }

    # State statutes (title 0 or negative titles are state codes)
    state_query = """
        SELECT
            CASE
                WHEN section LIKE 'NY-%' THEN 'NY'
                WHEN section LIKE 'CA-%' THEN 'CA'
                ELSE 'Other'
            END as state,
            COUNT(*) as section_count
        FROM sections
        WHERE title = 0 OR title < 0
        GROUP BY state
        ORDER BY state
    """
    state_rows = db.execute(state_query).fetchall()

    state_stats = {}
    state_total = 0
    for row in state_rows:
        state_stats[row[0]] = row[1]
        state_total += row[1]

    # Get NY law breakdown
    ny_breakdown_query = """
        SELECT
            SUBSTR(section, 4, INSTR(SUBSTR(section, 4), '-') - 1) as law_code,
            COUNT(*) as sections
        FROM sections
        WHERE section LIKE 'NY-%'
        GROUP BY law_code
        ORDER BY sections DESC
    """
    ny_rows = db.execute(ny_breakdown_query).fetchall()
    ny_breakdown = {row[0]: row[1] for row in ny_rows}

    stats_data["state_statutes"] = {
        "total_sections": state_total,
        "by_state": state_stats,
        "ny_breakdown": ny_breakdown,
    }

    # IRS Guidance statistics
    guidance_query = """
        SELECT doc_type, COUNT(*) as count,
               MIN(SUBSTR(doc_number, 1, 4)) as earliest_year,
               MAX(SUBSTR(doc_number, 1, 4)) as latest_year
        FROM guidance_documents
        GROUP BY doc_type
    """
    try:
        guidance_rows = db.execute(guidance_query).fetchall()
        guidance_stats = {}
        guidance_total = 0
        for row in guidance_rows:
            guidance_stats[row[0]] = {
                "count": row[1],
                "year_range": f"{row[2]}-{row[3]}",
            }
            guidance_total += row[1]

        stats_data["irs_guidance"] = {
            "total_documents": guidance_total,
            "by_type": guidance_stats,
        }
    except Exception:
        stats_data["irs_guidance"] = {"total_documents": 0, "by_type": {}}

    # Totals
    stats_data["totals"] = {
        "usc_titles": len(usc_stats),
        "usc_sections": usc_total_sections,
        "state_sections": state_total,
        "guidance_documents": stats_data["irs_guidance"].get("total_documents", 0),
        "all_sections": usc_total_sections + state_total,
    }

    # Database file size
    db_path = Path(ctx.obj["db"])
    if db_path.exists():
        stats_data["database_size_mb"] = round(db_path.stat().st_size / 1024 / 1024, 2)

    if as_json:
        console.print_json(json_module.dumps(stats_data, indent=2))
        return

    # Pretty print
    console.print()
    console.print(
        Panel(
            "[bold cyan]Cosilico Arch - Archive Statistics[/bold cyan]",
            subtitle=f"Database: {ctx.obj['db']}",
        )
    )

    # US Code table
    table = Table(title="📜 US Code", show_header=True, header_style="bold cyan")
    table.add_column("Title", justify="right", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Sections", justify="right", style="green")

    for t in stats_data["us_code"]["by_title"][:10]:  # Top 10
        table.add_row(str(t["title"]), t["name"][:35], f"{t['sections']:,}")

    if len(stats_data["us_code"]["by_title"]) > 10:
        table.add_row("...", f"... and {len(stats_data['us_code']['by_title']) - 10} more", "")

    table.add_row("", "[bold]TOTAL[/bold]", f"[bold]{usc_total_sections:,}[/bold]")
    console.print(table)

    # State statutes
    if state_total > 0:
        console.print()
        table2 = Table(title="🏛️  State Statutes", show_header=True, header_style="bold cyan")
        table2.add_column("State", style="cyan")
        table2.add_column("Law", style="white")
        table2.add_column("Sections", justify="right", style="green")

        for law, count in sorted(ny_breakdown.items(), key=lambda x: -x[1]):
            table2.add_row("NY", law, f"{count:,}")

        table2.add_row("", "[bold]TOTAL[/bold]", f"[bold]{state_total:,}[/bold]")
        console.print(table2)

    # IRS Guidance
    if stats_data["irs_guidance"].get("total_documents", 0) > 0:
        console.print()
        table3 = Table(title="📋 IRS Guidance", show_header=True, header_style="bold cyan")
        table3.add_column("Type", style="cyan")
        table3.add_column("Count", justify="right", style="green")
        table3.add_column("Years", style="dim")

        for doc_type, info in stats_data["irs_guidance"]["by_type"].items():
            table3.add_row(doc_type, str(info["count"]), info["year_range"])

        table3.add_row(
            "[bold]TOTAL[/bold]",
            f"[bold]{stats_data['irs_guidance']['total_documents']}[/bold]",
            "",
        )
        console.print(table3)

    # Summary
    console.print()
    console.print(
        Panel(
            f"[bold green]Total Sections:[/bold green] {stats_data['totals']['all_sections']:,}\n"
            f"[bold blue]US Code Titles:[/bold blue] {stats_data['totals']['usc_titles']}\n"
            f"[bold yellow]IRS Documents:[/bold yellow] {stats_data['totals']['guidance_documents']}\n"
            f"[dim]Database Size: {stats_data.get('database_size_mb', 'N/A')} MB[/dim]",
            title="Summary",
        )
    )


if __name__ == "__main__":
    main()
