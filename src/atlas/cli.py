"""Command-line interface for the law archive."""

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from atlas.archive import Atlas
from atlas.parsers.uslm import download_title

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
    archive = Atlas(db_path=ctx.obj["db"])
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
    archive = Atlas(db_path=ctx.obj["db"])
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
    archive = Atlas(db_path=ctx.obj["db"])
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
    archive = Atlas(db_path=ctx.obj["db"])
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
    archive = Atlas(db_path=ctx.obj["db"])
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
    from atlas.encoder import encode_and_save
    from atlas.models import Citation

    archive = Atlas(db_path=ctx.obj["db"])

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
    from atlas.verifier import (
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


if __name__ == "__main__":
    main()
