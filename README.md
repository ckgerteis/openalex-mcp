# openalex-mcp

MCP stdio server for the OpenAlex API (global scholarly graph).

Data via OpenAlex, OurResearch.

## What this is for

OpenAlex maps roughly 240 million works and the relations between them, and this is the instrument for questions about circulation rather than content.

Ask who cites a given work and from which countries and institutions; assemble an author's full output across the name variants that defeat a title search; find which institutions cluster around a problem; identify the journals and repositories where a field actually publishes. Open-access status and PDF links come back with each record.

For a historian, the useful move is tracing whether an argument travelled — out of its language, out of its discipline, out of the decade that produced it — which is a question a bibliographic catalogue cannot answer and a citation graph can.

## Install

Flat layout, matching how the server is deployed: `server.py` and `ledger.py`
side by side, run by path.

```bash
python -m venv .venv && .venv/bin/pip install -e .
```

Then point Claude Desktop at `python server.py` (see below).

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

```json
{
  "mcpServers": {
    "openalex": {
      "command": "C:\\path\\to\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\openalex_mcp\\server.py"],
      "env": {
        "OPENALEX_API_KEY": "your_openalex_api_key"
      }
    }
  }
}
```

## Query receipts

Every query can be deposited to an append-only, hash-chained JSONL log by
`openalex_mcp.ledger`. It is **off unless `MCP_RECEIPT_LOG` is set**, and a
logging failure is swallowed rather than raised — a search matters more than
the record of it. Secrets are redacted before a line is composed.

```
MCP_RECEIPT_LOG=C:\path\to\receipts.jsonl
MCP_RECEIPT_SESSION=project-or-article-slug
MCP_RECEIPT_STRICT=1        # optional: make logging failure raise
```

Verify a deposited log's hash chain:

```bash
python ledger.py verify receipts.jsonl
```

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
