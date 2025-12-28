# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

Cosilico Arch is the foundational archive for ALL raw government source files. It downloads, parses, and stores legal and regulatory documents from official sources, enabling programmatic access with full-text search.

### Scope

Cosilico Arch archives:
- **Statutes**: US Code (USLM XML), state statutes (NY, CA, etc.)
- **IRS Guidance**: Revenue Procedures, Revenue Rulings, Notices, Publications
- **Microdata**: CPS Annual Social and Economic Supplement (ASEC), ACS, SCF
- **Crosstabs**: Tax Statistics of Income (SOI), Census tables
- **Parameters**: Policy parameters, thresholds, brackets by tax year

This repo is part of the Cosilico ecosystem (see parent CLAUDE.md for full repo architecture). Its role is **source document archive** - storing PDFs, HTML, XML, and structured text that feeds into the rules encoding pipeline.

## Commands

```bash
# Install dependencies
uv sync                          # Or: pip install -e ".[dev,verify]"

# CLI usage
arch download 26           # Download US Code Title 26 (IRC)
arch ingest data/uscode/usc26.xml  # Ingest into SQLite
arch get "26 USC 32"       # Get a specific section
arch search "earned income" --title 26  # Full-text search
arch serve                 # Start REST API at localhost:8000

# AI encoding pipeline
arch encode "26 USC 32"    # Encode statute into Cosilico DSL
arch validate ~/.cosilico/workspace/federal/statute/26/32
arch verify ~/.cosilico/workspace/federal/statute/26/32 -v eitc

# Testing
pytest                           # Run all tests
pytest tests/test_models.py -v   # Run specific test file
pytest -k "test_parse"           # Run tests matching pattern

# Linting
ruff check src/                  # Lint
ruff format src/                 # Format
mypy src/arch/                   # Type check
```

## Architecture

### Core Pipeline

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Official XML   │────▶│  USLM Parser    │────▶│  SQLite/FTS5   │
│  (uscode.gov)   │     │  parsers/uslm.py│     │  arch.db       │
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

- **`archive.py`** - Main `Arch` class (public API)
- **`models.py`** - Pydantic models: `Citation`, `Section`, `Subsection`, `SearchResult`
- **`models_guidance.py`** - IRS guidance document models (Rev. Procs, Rulings)
- **`parsers/uslm.py`** - USLM XML parser for US Code
- **`storage/sqlite.py`** - SQLite backend with FTS5 full-text search
- **`encoder.py`** - AI pipeline: statute -> Cosilico DSL
- **`verifier.py`** - Compare DSL outputs vs PolicyEngine
- **`cli.py`** - Click CLI commands

### Data Flow

1. **Download**: `arch download 26` fetches XML from uscode.house.gov
2. **Ingest**: Parser extracts sections, subsections, cross-references -> SQLite
3. **Query**: FTS5-powered search, citation lookup, cross-reference graph
4. **Encode**: Claude generates DSL code from statute text
5. **Verify**: Compare DSL test cases against PolicyEngine calculations

### Directory Structure

```
data/           # Downloaded/ingested data (gitignored)
  uscode/       # Raw USLM XML files
  federal/      # Processed federal statutes
  microdata/    # CPS, ACS microdata files
  crosstabs/    # SOI, Census tabulations
catalog/        # Structured statute catalog
  guidance/     # IRS guidance documents
  statute/      # Statute extracts
  parameters/   # Policy parameters by year
sources/        # Source document archives (state codes, etc.)
output/         # Generated outputs (DSL, verification reports)
schema/         # SQL migration files
```

## Key Patterns

### Citation Parsing

Citations follow USC format and convert to filesystem paths:
- `"26 USC 32"` -> `Citation(title=26, section="32")`
- `"26 USC 32(a)(1)"` -> subsection `"a/1"`, path `"statute/26/32/a/1"`

### Storage Backend Interface

`StorageBackend` abstract class (storage/base.py) defines the interface. SQLite implementation uses FTS5 for search with triggers to keep index in sync.

### DSL Encoding Output

`arch encode` generates four files per section:
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

## Session Continuation Notes (2024-12-28)

### Completed This Session
- ✅ Renamed GitHub repo: `cosilico-atlas` → `arch` (CosilicoAI/arch)
- ✅ Renamed source: `src/atlas` → `src/arch`
- ✅ Updated all imports and class names (`Atlas` → `Arch`)
- ✅ Updated README with expanded scope
- ✅ Git remote updated to `https://github.com/CosilicoAI/arch.git`

### Next Steps (see beads issues)
1. **CosilicoAI-uj0**: Update cosilico.ai stack pages for Arch
   - Add `/stack/arch` route
   - Update StackPage.tsx grid
   - Create ArchPage.tsx with hero, features, data sources

2. **CosilicoAI-jtu**: Create arch PostgreSQL schema in cosilico-db
   - Schema already drafted (previous session created migration file)
   - Tables: sources, files, fetch_log, content, cross_references
   - Full-text search with tsvector

3. **CosilicoAI-4en**: Set up Cloudflare R2 bucket for raw files
   - Bucket: `cosilico-arch` or just `arch`
   - Structure: `sources/{statutes,guidance,microdata,crosstabs}/`

4. **CosilicoAI-yf6**: Rename other repos
   - `cosilico-engine` → `rac` (the core DSL)
   - `cosilico-us` → `rac-us` (US federal rules)
   - `cosilico-compile` → `rac-compile`

### Folder Rename Required
After exiting Claude Code, rename local folder:
```bash
cd ~/CosilicoAI
mv cosilico-arch arch
cd arch
```

### Naming Convention Decided
```
CosilicoAI/
├── rac                 # Core DSL engine
├── rac-compile         # Multi-target compiler
├── rac-us              # US federal rules
├── arch                # Source document archive (this repo)
├── microplex           # Microdata library
├── cosilico-db         # Infrastructure (PostgreSQL)
├── cosilico-api        # Infrastructure (API)
└── cosilico.ai         # Website
```
