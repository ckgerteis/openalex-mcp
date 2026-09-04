# openalex-mcp

MCP stdio server for the OpenAlex API (global scholarly graph).

Data via OpenAlex, OurResearch.

## What this is for

OpenAlex maps roughly 240 million works and the relations between them, and this is the instrument for questions about circulation rather than content.

Ask who cites a given work and from which countries and institutions; assemble an author's full output across the name variants that defeat a title search; find which institutions cluster around a problem; identify the journals and repositories where a field actually publishes. Open-access status and PDF links come back with each record.

For a historian, the useful move is tracing whether an argument travelled — out of its language, out of its discipline, out of the decade that produced it — which is a question a bibliographic catalogue cannot answer and a citation graph can.

## Install

Three routes. All three give you the same server; pick by how much you want to see of it.

### One click: the Claude Desktop bundle

Download the `.mcpb` for your platform (Windows x64, Apple Silicon, Linux x64; Intel Macs use the pip route below) from the [latest release](https://github.com/ckgerteis/openalex-mcp/releases/latest) and open it; Claude Desktop installs it. Claude Desktop asks for OpenAlex API key and Contact email (legacy mailto) and a receipts folder at install time; the key is stored in the OS keychain. The bundle carries every library it needs, but not Python itself: a Python 3.10+ interpreter must be on the machine (`python` on Windows, `python3` on macOS and Linux).

### From GitHub, pinned to a release

```bash
pip install "git+https://github.com/ckgerteis/openalex-mcp@v2.0.0"
# or, without an environment of your own:
uvx --from "git+https://github.com/ckgerteis/openalex-mcp@v2.0.0" openalex-mcp
```

installs the `openalex-mcp` console script and `openalex-mcp-ledger`. The tag is the thing to cite; `@main` gets whatever is current. Then register it in Claude Desktop (below), or let `install.py` do that.

### The whole family

```bash
pip install "git+https://github.com/ckgerteis/bibliograph-mcp@v1.0.0" && bibliograph install
```

installs all six servers and registers them together — one receipts folder, credentials asked for once. See [bibliograph-mcp](https://github.com/ckgerteis/bibliograph-mcp). From a checkout of this repository, `python install.py` does the same for this server alone, `python install.py --all` for the six, on Windows, macOS and Linux; `install.ps1` remains for Windows.

### From source

```bash
python3 -m venv .venv
.venv/bin/pip install .
```

On Windows:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\pip.exe install .
```

Or straight from the repository, without cloning:

```bash
uvx --from "git+https://github.com/ckgerteis/openalex-mcp" openalex-mcp
```

Verify the install:

```bash
.venv/bin/python -c "import openalex_mcp; print(openalex_mcp.__version__)"
```

That fails loudly if the package or one of its vendored modules is missing. Do
not use `openalex-mcp --help` as the check: unknown arguments are ignored, the
server starts, reads end-of-input and exits 0, so it reports success whatever
the state of the code.

### Installing more than this one

Six independent packages. None imports another, none depends on another, and
each installs and answers on its own — `pip install .` in this directory is a
complete install of this server and nothing else.

They do share three things: a response envelope, a query ledger, and — if you
run more than one — a receipts folder. `install.ps1` is vendored byte-identical
into all six and handles that on Windows; `install.py` is its cross-platform port. **Both install this server by default**, because
cloning one repository is not a request for five more.

```powershell
.\install.ps1                        # this server
.\install.ps1 -All                   # all six
.\install.ps1 -Servers openalex,cinii      # a chosen subset
```

Whatever subset you name is registered against one receipts folder, asked for
once. The script prefers a sibling checkout to the network, carries across
credentials already registered rather than asking again, leaves servers it was
not asked about alone, and stops rather than guessing where the servers already
registered disagree about the folder or the session slug. It also asserts that
`ledger.py` and `mediation.py` are byte-identical across everything it
installed, so two envelope versions cannot end up in one environment unnoticed.

## Tools

| Tool | Purpose |
| --- | --- |
| `oa_search_works` | Works (articles, books, datasets, theses) by term, with year, author, institution, source and open-access filters |
| `oa_get_work` | One work by OpenAlex ID, DOI or PMID |
| `oa_search_authors` | Authors by name, optionally within an institution |
| `oa_get_author` | One author by OpenAlex ID or ORCID |
| `oa_search_sources` | Journals, repositories and conferences by name |
| `oa_search_institutions` | Institutions by name, optionally by country |
| `oa_cited_by` | Works citing a given work, most-cited first |
| `oa_author_works` | An author's works, with year filter and sort |

All eight return one typed JSON response envelope — see [Response format](#response-format). (Releases before 2.0.0 returned formatted markdown text; that is a breaking change, not a formatting preference.)

## Response format

Every tool returns one JSON response envelope, built by `mediation.py` and defined in [`response-schema.json`](response-schema.json). Schema version 2.3.0. The same module and schema are vendored byte-identically across the server family, so an envelope from one server can be read by a consumer written for another.

The envelope reports how the search was made, not only what it found:

- **`searched_for`** — on search operations, the term actually sent, its detected script, and the matching mode, hoisted to the top of the envelope so a relaying client cannot drop it. Lookups (`oa_get_work`, `oa_get_author`) and identifier filters (`oa_cited_by`, `oa_author_works`) omit it: they were handed an identifier and chose no term.
- **`query`** — `input_terms` as supplied, `normalized` as sent, and the detected `script`. The credential never enters `params`.
- **`matching_mode`** — `full_text_stemmed` for term searches: OpenAlex matches title, abstract and indexed full text with stemming, so `result.total` is a loose count and a high breadth is expected. `filter_exact` for identifier filters; `identifier_lookup` for single-record fetches.
- **`result.breadth`** — `none`, `narrow` (1–50), `broad` (51–1000), `very_broad` (>1000).
- **`items[]`** — the family's item shape. OpenAlex's own `language` field decides which typed title slot a work's title lands in (`ja`, `ko`; Latin-script titles in any other language go to `en`). A CJK title OpenAlex marks neither `ja` nor `ko`, or a han-only title with no language, is left untyped rather than guessed; `extra.title` always carries the text and `extra.language` the code. OpenAlex identifiers, citation counts, open-access flags, topics and the reconstructed abstract sit in `extra`; the DOI (bare, without the `https://doi.org/` prefix) in `ids.doi`; the landing page in `ids.url_en`; an open-access copy in `ids.fulltext_url`. Author, source and institution records use `record_type` `author`, `source` and `institution` with their metrics in `extra`.
- **`receipt`** — an ISO 8601 timestamp, a SHA-256 over the normalised query and its parameters, and the DOIs returned. Works without a DOI are identified only in `extra.openalex_id`, which the receipt's `result_ids` does not yet read.
- **`attribution`** — the required credit line, in every response.

### Diagnostic codes

Typed and closed. A diagnostic is never prose the client has to parse.

| Code | Level | Meaning |
| --- | --- | --- |
| `OK` | info | Records returned; nothing to flag. |
| `ZERO_RESULTS` | warning | No records for this term and filter set. Non-English titles are indexed as the publisher supplied them, so an English rendering of a Japanese or Korean title may not match. |
| `NOT_FOUND` | warning | A lookup by identifier answered 404. |
| `RATE_LIMITED` | error | OpenAlex answered 429. Since 2026 OpenAlex meters keyless access by a per-IP daily budget as well as per-second rate; a key raises both. |
| `API_ERROR` | error | The API answered, and answered with an error (or with a 200 that was not JSON). |
| `TRANSPORT_ERROR` | error | The request did not complete. Kept distinct from `API_ERROR` because a failed search has an unknown result and must never be written up as an absence. |
| `RECEIPT_NOT_DEPOSITED` | info | The response was not written to the query ledger, because no receipts destination is configured. |
| `RECEIPT_WRITE_FAILED` | warning | A receipts destination is set, the write was attempted, and it did not land. |

## Configuration

```
OPENALEX_API_KEY=your_openalex_api_key
OPENALEX_EMAIL=your_email        # legacy; see below
```

OpenAlex retired the polite pool on 13 February 2026 and replaced it with an API
key regime; the `mailto` parameter it depended on is now ignored. `OPENALEX_API_KEY`
is the access route. `OPENALEX_EMAIL` is kept only as a fallback for anyone running
against a mirror that still honours `mailto`, and sends nothing OpenAlex reads.

### Claude Desktop

Add an entry to `%APPDATA%\Claude\claude_desktop_config.json` under
`mcpServers`, pointing at the console script in the environment you installed
into. On macOS or Linux use the absolute path to `.venv/bin/openalex-mcp`.

```json
{
  "mcpServers": {
    "openalex": {
      "command": "C:\\path\\to\\.venv\\Scripts\\openalex-mcp.exe",
      "env": {
        "OPENALEX_API_KEY": "your_openalex_api_key"
      }
    }
  }
}
```

**Changed in 2.0.0.** Tools return the JSON envelope rather than markdown; any consumer that parsed the 1.x text must be rewritten.

**Changed in 1.1.0.** Earlier versions were registered by path —
`"command": "…\\python.exe", "args": ["…\\server.py"]`. That entry will not
start this version, because `server.py` is now a module inside a package rather
than a script beside its imports. Replace it with the console script above.

Restart Claude Desktop. The eight tools should appear under "openalex" in the
tool list.

## Query receipts

Every envelope can be deposited to an append-only, hash-chained JSONL log by
`openalex_mcp.ledger`. Since 2.0.0 the envelope says whether that happened: `RECEIPT_NOT_DEPOSITED` when no destination is set, `RECEIPT_WRITE_FAILED` when one is set and the write did not land. It is **off unless `MCP_RECEIPT_DIR` (or the legacy `MCP_RECEIPT_LOG`) is set**, and a
logging failure is swallowed rather than raised — a search matters more than
the record of it. Secrets are redacted before a line is composed.

```
MCP_RECEIPT_DIR=C:\path\to\receipts        # a folder, not a file
MCP_RECEIPT_SESSION=project-or-article-slug
MCP_RECEIPT_STRICT=1                         # optional: make logging failure raise
MCP_RECEIPT_LOG=C:\path\to\receipts.jsonl  # legacy single file; ignored when _DIR is set
```

**A folder, and one file per server.** `MCP_RECEIPT_DIR` points at a directory
and each server writes its own `<server>.jsonl` inside it. That is not tidiness.
Appending is read-the-last-hash-then-write, and the lock around it is a threading
lock, which holds within one process and not between several — six servers are
six processes, and two answering at the same moment will both read the same
predecessor and both claim it. Measured, not theorised: six processes writing 150
lines to one file produced fourteen forks. `MCP_RECEIPT_LOG` still works and is
still correct for a single server; it is the wrong shape for a family.

`install.ps1` sets this up for all six and writes a README into the folder.

Verify one chain, or the whole folder:

```bash
openalex-mcp-ledger verify      receipts/openalex.jsonl
openalex-mcp-ledger verify-dir  receipts
openalex-mcp-ledger manifest    receipts        # writes receipts/manifest.json
```

`verify` exits non-zero on failure and says which kind it found: a **fork**
(concurrent writers — a configuration fault, and every line is still there), a
**missing** line, a **reordering**, or **tamper** (a line that does not hash to
its own content). Only the last is a claim about honesty, and reporting them
alike would invite a reader to mistake one for the other. The manifest is the
object to cite: one description of the whole deposit — per-file line counts,
first and last timestamps, terminal hashes, and combined totals by server,
script and session.

## Tests

```bash
.venv/bin/pip install pytest jsonschema
.venv/bin/python -m pytest -q tests
```

The suite runs against recorded OpenAlex responses under `tests/fixtures/` (captured 2026-09-04) and validates every envelope against `response-schema.json`; it needs no network and no key. `RUN_LIVE=1` adds one request to the live API.

## MCP SDK compatibility

Runs on both `mcp` 1.x and 2.x. Version 2.0.0 of the SDK removed
`mcp.server.fastmcp`; this server imports `FastMCP` where it exists and falls
back to `MCPServer` where it does not.

## License

MIT © 2026 Christopher Gerteis. Covers the server code only; it grants no
rights over OpenAlex, OurResearch data, which remains governed by that provider's
terms.

## Author

[Dr Christopher Gerteis](https://www.christophergerteis.net), SOAS University
of London.
