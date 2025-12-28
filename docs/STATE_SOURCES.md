# State Statute Sources

## Priority Tiers

### Tier 1: Large Income Tax States (implement first)
| State | Pop (M) | Source | Format | Status |
|-------|---------|--------|--------|--------|
| CA | 39.0 | leginfo.legislature.ca.gov | HTML scrape | ✅ Done |
| NY | 19.5 | legislation.nysenate.gov | JSON API | ✅ Done |
| TX | 30.0 | statutes.capitol.texas.gov | HTML | ✅ Done |
| FL | 22.6 | leg.state.fl.us | HTML | ✅ Done |
| PA | 12.9 | palegis.us | HTML scrape | ✅ Done |
| IL | 12.6 | ilga.gov | HTML | 🔨 TODO |
| OH | 11.8 | codes.ohio.gov | HTML scrape | ✅ Done |
| GA | 10.9 | legis.ga.gov | PDF/complex | 🔨 TODO |
| NC | 10.7 | ncleg.gov | HTML scrape | ✅ Done |
| MI | 10.0 | legislature.mi.gov | HTML | 🔨 TODO |

### Tier 2: Medium Income Tax States
| State | Pop (M) | Source | Format | Status |
|-------|---------|--------|--------|--------|
| NJ | 9.3 | njleg.state.nj.us | HTML | TODO |
| VA | 8.6 | law.lis.virginia.gov | HTML | TODO |
| WA | 7.8 | leg.wa.gov | HTML | TODO |
| AZ | 7.4 | azleg.gov | HTML | TODO |
| MA | 7.0 | malegislature.gov | HTML | TODO |
| CO | 5.8 | leg.colorado.gov | HTML | TODO |
| MD | 6.2 | mgaleg.maryland.gov | HTML | TODO |
| MN | 5.7 | revisor.mn.gov | HTML | TODO |
| WI | 5.9 | docs.legis.wisconsin.gov | HTML | TODO |
| MO | 6.2 | revisor.mo.gov | HTML | TODO |

### Tier 3: Smaller States & No Income Tax
| State | Notes |
|-------|-------|
| NV, WY, SD, AK | No income tax |
| NH, TN | Limited income tax (investment only) |
| Remaining 20+ states | Lower priority |

## Data Sources by Type

### Official Bulk Downloads
- **CA**: downloads.leginfo.legislature.ca.gov (ZIP archives, SQL database)
- **TX**: statutes.capitol.texas.gov (PDF, RTF, HTML bulk)

### Official APIs
- **NY**: legislation.nysenate.gov/api/3 (JSON, free API key)

### Web Scraping Required
- Most other states require HTML parsing from legislature websites

### Third-Party Sources
- **LegiScan**: legiscan.com/datasets (all 50 states, JSON/XML, free registration)
- **Open States**: open.pluralpolicy.com/data (bills, not codified statutes)
- **Justia**: law.justia.com/codes (readable, but TOS may restrict scraping)

## Implementation Notes

### Common Patterns
Many state legislatures use similar CMS platforms:
- Some use LegiStar
- Many have similar URL structures for sections

### Key Codes to Prioritize
For each state, focus on:
1. **Tax Code** (Revenue & Taxation, Tax Law, etc.)
2. **Welfare/Benefits Code** (Human Services, Social Services, etc.)
3. **Unemployment Insurance Code**
4. **Labor Code**

## Progress Tracking

- [x] Federal US Code (USLM parser)
- [x] CA (HTML scraper) - 28 codes including RTC, WIC
- [x] NY (Open Legislation API)
- [x] FL (HTML scraper)
- [x] TX (HTML scraper)
- [x] PA (generic scraper)
- [x] OH (generic scraper)
- [x] NC (generic scraper)
- [ ] IL (complex URL structure)
- [ ] GA (PDF-based, harder)
- [ ] MI
- [ ] ... (remaining ~40 states)
