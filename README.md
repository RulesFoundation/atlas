# Cosilico Atlas

**Structured policy document API — statutes, regulations, and guidance.**

Policy documents are public domain, but no open source project provides structured access via API with historical versions. Atlas fills that gap.

## Features

- **Federal statutes** — All 54 titles of the US Code from official USLM XML
- **IRS guidance** — Revenue Procedures, Revenue Rulings, Notices
- **Historical versions** — Track changes over time
- **REST API** — Query documents by citation, keyword, or path
- **Structured data** — JSON output with section hierarchy, cross-references, and metadata
- **State codes** — Incremental rollout (starting with CA, NY, TX)

## Quick Start

```bash
# Install
pip install cosilico-atlas

# Run the API server
atlas serve

# Or use the CLI
atlas get "26 USC 32"        # Get IRC § 32 (EITC)
atlas search "earned income" # Search across documents
```

## API Usage

```python
from atlas import Atlas

archive = Atlas()

# Get a specific section
eitc = archive.get("26 USC 32")
print(eitc.title)        # "Earned income"
print(eitc.text)         # Full section text
print(eitc.subsections)  # Hierarchical structure

# Search
results = archive.search("child tax credit", title=26)
for section in results:
    print(f"{section.citation}: {section.title}")

# Get historical version
eitc_2020 = archive.get("26 USC 32", as_of="2020-01-01")
```

## REST API

```bash
# Get section by citation
curl http://localhost:8000/v1/sections/26/32

# Search
curl "http://localhost:8000/v1/search?q=earned+income&title=26"

# Get specific subsection
curl http://localhost:8000/v1/sections/26/32/a/1

# Historical version
curl "http://localhost:8000/v1/sections/26/32?as_of=2020-01-01"
```

## Data Sources

| Source | Content | Format | Update Frequency |
|--------|---------|--------|------------------|
| [uscode.house.gov](https://uscode.house.gov/download/download.shtml) | US Code | USLM XML | Continuous |
| [IRS.gov](https://www.irs.gov/) | Revenue Procedures, Rulings | HTML/PDF | Weekly |
| [eCFR](https://www.ecfr.gov/) | Code of Federal Regulations | XML | Daily |
| State legislatures | State codes | Varies | Varies |

## Architecture

```
cosilico-atlas/
├── src/atlas/
│   ├── __init__.py
│   ├── archive.py       # Main Atlas class
│   ├── models.py        # Pydantic models for statutes
│   ├── models_guidance.py # Models for IRS guidance
│   ├── parsers/
│   │   ├── uslm.py      # USLM XML parser
│   │   ├── ecfr.py      # eCFR XML parser
│   │   └── state/       # State-specific parsers
│   ├── fetchers/
│   │   └── irs_guidance.py # IRS guidance fetcher
│   ├── api/
│   │   ├── main.py      # FastAPI app
│   │   └── routes.py    # API routes
│   ├── cli.py           # Command-line interface
│   └── storage/
│       ├── base.py      # Storage interface
│       ├── sqlite.py    # SQLite backend
│       └── postgres.py  # PostgreSQL backend
├── data/
│   └── .gitkeep         # Downloaded/parsed data (gitignored)
├── tests/
└── scripts/
    └── ingest.py        # Data ingestion scripts
```

## Why This Exists

From [DESIGN.md](https://github.com/CosilicoAI/cosilico-engine/blob/main/docs/DESIGN.md#1571-existing-statute-apis-and-why-we-need-our-own):

> No open source project provides structured statute text via API with historical versions.
>
> - OpenLaws.us is closest but proprietary
> - Free Law Project covers case law only
> - Cornell LII prohibits scraping
> - Official sources require self-hosting

We're building this for [Cosilico](https://cosilico.ai)'s rules engine but open-sourcing it as a public good.

## License

Apache 2.0 — Use it for anything.

## Contributing

We welcome contributions! Priority areas:

1. State code parsers (50 states to cover)
2. IRS guidance extraction
3. Historical version tracking
4. Cross-reference resolution
5. Full-text search improvements

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
