# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

Cosilico Atlas provides a structured policy document API. It downloads, parses, and stores legal and regulatory documents from official sources (US Code, state statutes, IRS guidance), enabling programmatic access to statute text with full-text search.

This repo is part of the Cosilico ecosystem (see parent CLAUDE.md for full repo architecture). Its role is **source document archive** - storing PDFs, HTML, and structured statute text that feeds into the rules encoding pipeline.

## Commands

```bash
# Install dependencies
uv sync                          # Or: pip install -e ".[dev,verify]"

# CLI usage
atlas download 26           # Download US Code Title 26 (IRC)
atlas ingest data/uscode/usc26.xml  # Ingest into SQLite
atlas get "26 USC 32"       # Get a specific section
atlas search "earned income" --title 26  # Full-text search
atlas serve                 # Start REST API at localhost:8000

# AI encoding pipeline
atlas encode "26 USC 32"    # Encode statute into Cosilico DSL
atlas validate ~/.cosilico/workspace/federal/statute/26/32
atlas verify ~/.cosilico/workspace/federal/statute/26/32 -v eitc

# Testing
pytest                           # Run all tests
pytest tests/test_models.py -v   # Run specific test file
pytest -k "test_parse"           # Run tests matching pattern

# Linting
ruff check src/                  # Lint
ruff format src/                 # Format
mypy src/atlas/                  # Type check
```

## Architecture

### Core Pipeline

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Official XML   │────▶│  USLM Parser    │────▶│  SQLite/FTS5   │
│  (uscode.gov)   │     │  parsers/uslm.py│     │  atlas.db      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                       │
┌─────────────────┐     ┌─────────────────┐            │
│  Claude AI      │◀────│  Encoder        │◀───────────┘
│  (DSL gen)      │     │  encoder.py     │
└─────────────────┘     └─────────────────┘
        │
        ▼
┌─────────────────┐     ┌─────────────────┐
│  .cosilico      │────▶│  Verifier       │────▶ PolicyEngine
│  rules + tests  │     │  verifier.py    │      comparison
└─────────────────┘     └─────────────────┘
```

### Key Modules

- **`atlas.py`** - Main `Atlas` class (public API)
- **`models.py`** - Pydantic models: `Citation`, `Section`, `Subsection`, `SearchResult`
- **`models_guidance.py`** - IRS guidance document models (Rev. Procs, Rulings)
- **`parsers/uslm.py`** - USLM XML parser for US Code
- **`storage/sqlite.py`** - SQLite backend with FTS5 full-text search
- **`encoder.py`** - AI pipeline: statute → Cosilico DSL
- **`verifier.py`** - Compare DSL outputs vs PolicyEngine
- **`cli.py`** - Click CLI commands

### Data Flow

1. **Download**: `atlas download 26` fetches XML from uscode.house.gov
2. **Ingest**: Parser extracts sections, subsections, cross-references → SQLite
3. **Query**: FTS5-powered search, citation lookup, cross-reference graph
4. **Encode**: Claude generates DSL code from statute text
5. **Verify**: Compare DSL test cases against PolicyEngine calculations

### Directory Structure

```
data/           # Downloaded/ingested data (gitignored)
  uscode/       # Raw USLM XML files
  federal/      # Processed federal statutes
catalog/        # Structured statute catalog
  guidance/     # IRS guidance documents
  statute/      # Statute extracts
sources/        # Source document archives (state codes, etc.)
output/         # Generated outputs (DSL, verification reports)
schema/         # SQL migration files
```

## Key Patterns

### Citation Parsing

Citations follow USC format and convert to filesystem paths:
- `"26 USC 32"` → `Citation(title=26, section="32")`
- `"26 USC 32(a)(1)"` → subsection `"a/1"`, path `"statute/26/32/a/1"`

### Storage Backend Interface

`StorageBackend` abstract class (storage/base.py) defines the interface. SQLite implementation uses FTS5 for search with triggers to keep index in sync.

### DSL Encoding Output

`atlas encode` generates four files per section:
- `rules.cosilico` - Executable DSL code
- `tests.yaml` - Test cases for verification
- `statute.md` - Original statute text
- `metadata.json` - Provenance (model, tokens, timestamp)

## Testing

Tests use pytest with async support. Key test files:
- `test_models.py` - Citation parsing, model validation
- `test_storage.py` - SQLite backend operations
- `test_uslm_parser.py` - XML parsing
- `test_document_writer.py` - Output generation

Run a single test:
```bash
pytest tests/test_models.py::TestCitation::test_parse_simple_citation -v
```
