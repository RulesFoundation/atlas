"""Command-line interface for the law archive."""

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from lawarchive.archive import LawArchive
from lawarchive.parsers.uslm import download_title

console = Console()


@click.group()
@click.option("--db", default="lawarchive.db", help="Path to database file")
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
        lawarchive get "26 USC 32"
        lawarchive get "26 USC 32(a)(1)"
    """
    archive = LawArchive(db_path=ctx.obj["db"])
    section = archive.get(citation)

    if not section:
        console.print(f"[red]Not found:[/red] {citation}")
        raise SystemExit(1)

    if as_json:
        console.print_json(section.model_dump_json())
    else:
        console.print(Panel(
            f"[bold]{section.citation.usc_cite}[/bold]\n"
            f"[dim]{section.title_name}[/dim]\n\n"
            f"[bold blue]{section.section_title}[/bold blue]\n\n"
            f"{section.text[:2000]}{'...' if len(section.text) > 2000 else ''}\n\n"
            f"[dim]Source: {section.source_url}[/dim]",
            title=section.citation.usc_cite,
        ))


@main.command()
@click.argument("query")
@click.option("--title", "-t", type=int, help="Limit to specific title")
@click.option("--limit", "-n", default=10, help="Maximum results")
@click.pass_context
def search(ctx: click.Context, query: str, title: int | None, limit: int):
    """Search for sections matching a query.

    Examples:
        lawarchive search "earned income"
        lawarchive search "child tax credit" --title 26
    """
    archive = LawArchive(db_path=ctx.obj["db"])
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
    archive = LawArchive(db_path=ctx.obj["db"])
    title_list = archive.list_titles()

    if not title_list:
        console.print("[yellow]No titles loaded. Use 'lawarchive ingest' to add titles.[/yellow]")
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
        lawarchive ingest data/uscode/usc26.xml
    """
    archive = LawArchive(db_path=ctx.obj["db"])
    with console.status(f"Ingesting {xml_path}..."):
        count = archive.ingest_title(xml_path)
    console.print(f"[green]Successfully ingested {count} sections[/green]")


@main.command()
@click.argument("title_num", type=int)
@click.option("--output", "-o", type=click.Path(path_type=Path), default=Path("data/uscode"),
              help="Output directory")
def download(title_num: int, output: Path):
    """Download a US Code title from uscode.house.gov.

    Example:
        lawarchive download 26 -o data/uscode
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
        lawarchive serve --host 0.0.0.0 --port 8080
    """
    import uvicorn


    console.print(f"[green]Starting server at http://{host}:{port}[/green]")
    console.print(f"[dim]API docs at http://{host}:{port}/docs[/dim]")

    # We need to pass the db path to the app
    # For now, use environment variable or default
    uvicorn.run(
        "lawarchive.api.main:app",
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
        lawarchive refs "26 USC 32"
    """
    archive = LawArchive(db_path=ctx.obj["db"])
    refs = archive.get_references(citation)

    console.print(Panel(
        f"[bold]References from {citation}:[/bold]\n" +
        "\n".join(f"  → {r}" for r in refs["references_to"]) or "  (none)" +
        "\n\n[bold]Referenced by:[/bold]\n" +
        "\n".join(f"  ← {r}" for r in refs["referenced_by"]) or "  (none)",
        title=f"Cross-references: {citation}",
    ))


if __name__ == "__main__":
    main()
