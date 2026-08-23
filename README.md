# openalex-mcp

MCP stdio server for the OpenAlex API (global scholarly graph).

Data via OpenAlex, OurResearch.

## What this is for

OpenAlex maps roughly 240 million works and the relations between them, and this is the instrument for questions about circulation rather than content.

Ask who cites a given work and from which countries and institutions; assemble an author's full output across the name variants that defeat a title search; find which institutions cluster around a problem; identify the journals and repositories where a field actually publishes. Open-access status and PDF links come back with each record.

For a historian, the useful move is tracing whether an argument travelled — out of its language, out of its discipline, out of the decade that produced it — which is a question a bibliographic catalogue cannot answer and a citation graph can.

## Install

The package installs a `openalex-mcp` console script. It is namespaced, so it can
share one environment with the rest of this server family.

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

### The whole family at once

`install.ps1` — vendored byte-identical into all six repositories — installs any
or all of `cinii`, `jstage`, `ndl`, `korea_scholarship`, `openalex` and
`semantic_scholar` into one environment, asks once for a receipts folder, and
registers them all against it.

```powershell
.\install.ps1                                   # all six
.\install.ps1 -Servers openalex -ReceiptsDir "D:\research\receipts"
```

It reads a sibling checkout where one exists and fetches the rest from GitHub,
carries across any credentials already registered rather than asking again, and
stops rather than guessing if the servers already registered disagree about where
the receipts go.

## Tools

| Tool |
| --- |
| `oa_author_works` |
| `oa_cited_by` |
| `oa_get_author` |
| `oa_get_work` |
| `oa_search_authors` |
| `oa_search_institutions` |
| `oa_search_sources` |
| `oa_search_works` |

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

**Changed in 1.1.0.** Earlier versions were registered by path —
`"command": "…\\python.exe", "args": ["…\\server.py"]`. That entry will not
start this version, because `server.py` is now a module inside a package rather
than a script beside its imports. Replace it with the console script above.

Restart Claude Desktop. The eight tools should appear under "openalex" in the
tool list.

## Query receipts

Every query can be deposited to an append-only, hash-chained JSONL log by
`openalex_mcp.ledger`. It is **off unless `MCP_RECEIPT_LOG` is set**, and a
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
