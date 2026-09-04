# Changelog

Versions are the thing to cite. A count produced under one release is not
reproducible against another, so the release actually used should be named in
the text and, where a version DOI exists, cited by it.

Releases earlier than those below are on the repository's releases page; this
file begins where the record is precise enough to be worth writing down.

## 2.0.0 — 2026-09-04

**Breaking: every tool now returns the family's JSON response envelope.** 1.x
returned formatted markdown. Any consumer that parsed that text must be
rewritten; the input models and tool names are unchanged.

- **`mediation.py` and `response-schema.json` vendored**, byte-identical to the
  copies in cinii-mcp, jstage-mcp, ndl-mcp and korea-scholarship-mcp. The
  README's claim that the family shares one envelope is now true of this
  server. Every response carries `searched_for` on term searches, a typed
  `query`, `matching_mode`, graduated `result.breadth`, per-item `matched_in`,
  typed diagnostics, a receipt and the attribution line.
- **Receipts go through `emit()`.** The per-request `ledger.record_request`
  call is gone; the envelope itself is deposited, so the log and the answer
  cannot drift apart, and the envelope reports `RECEIPT_NOT_DEPOSITED` or
  `RECEIPT_WRITE_FAILED` when a deposit did not happen.
- **Matching modes named for what OpenAlex does.** `full_text_stemmed` for
  `search=` (title, abstract, indexed full text, stemmed), `filter_exact` for
  identifier filters, `identifier_lookup` for single fetches.
- **Titles typed by OpenAlex's `language` field**, not by guess. `ja` and `ko`
  land in their slots; Latin-script titles in `en`; a `zh` title or a han-only
  title with no language stays untyped in `extra.title`.
- **Typed diagnostics** replace `"Error: …"` strings: `ZERO_RESULTS`,
  `NOT_FOUND`, `RATE_LIMITED`, `API_ERROR`, `TRANSPORT_ERROR`. A 200 whose
  body is not JSON is `API_ERROR` rather than an uncaught exception.
- **The credential never touches the caller's parameters.** `_oa_request`
  adds the key to a copy; the dict that reaches the envelope and the receipt
  is the one the caller built. Error text is redacted before it becomes a
  diagnostic. httpx request logging is silenced, since the key travels in the
  query string and httpx logs the full URL at INFO.
- **Hard-coded "current affiliation" heuristic removed.** 1.x called an
  affiliation current if its years reached 2023. Affiliations are now passed
  through with their year lists and no judgement.
- **Tests.** `tests/test_server.py` runs against recorded OpenAlex responses
  and validates every envelope against the schema. No network, no key.
- Known limit: the receipt's `result_ids` reads DOIs only, so a work without
  one is fixed by the receipt hash and `extra.openalex_id` but not listed.
  Extending `make_receipt` is a family-wide schema change and is deferred.

## 1.1.0 — 2026-08-23

**Not released.** No tag was cut and no Zenodo record exists for this version, so
it is citable by commit alone. Tagging waits on confirmation that this
repository's Zenodo webhook is live: a release that mints nothing spends a
version number and returns nothing citable for it.

- **A receipts folder, and one chain per server.** `ledger.py` 1.1.0 adds
  `MCP_RECEIPT_DIR`: point it at a directory and each server writes its own
  `<server>.jsonl` inside it. `MCP_RECEIPT_LOG` still names a single file and is
  honoured when `MCP_RECEIPT_DIR` is unset, so nothing existing breaks.
- **Why, precisely.** Appending is read-the-last-hash-then-write and `_LOCK` is a
  `threading.Lock`, which holds within one process and not between several. Six
  servers are six processes. Six of them writing 150 lines to one file produced
  **fourteen forks** — two lines claiming the same predecessor, over and over.
  That was measured, not inferred, and it means the family's shared log was never
  safe to verify as one chain. One writer per file removes the race rather than
  mitigating it.
- **`verify_chain()` now types its failures.** It reported everything as
  `prev_hash mismatch`. It distinguishes a **fork** (concurrent writers; every
  line still present, and the file is several chains rather than one), a
  **missing** line, a **reordering**, and **tamper** (a line that does not hash to
  its own content). Only the last is a claim about honesty, and a reader given one
  label for all four cannot tell a misconfiguration from interference.
- **`verify_dir()` and a manifest.** One pass over a receipts folder returns
  per-file verdicts, line counts, first and last timestamps and terminal hashes,
  plus combined totals by server, script and session. `<dist>-ledger manifest
  <dir>` writes it to `manifest.json`. That file is what a disclosure cites: one
  description of the deposit rather than six assertions to reconcile.
- `<dist>-ledger` gains `verify-dir` and `manifest`, and `verify` now exits
  non-zero when a chain does not verify.
- **`install.ps1` installs this server by default, not the family.** These are
  six independent packages — none imports another, none depends on another, and
  each installs alone. The installer defaulted to all six, so cloning one
  repository and running it would have registered five servers nobody asked for
  and fetched them from GitHub. It now resolves the default from the repository
  it sits in; `-All` opts into the family and `-Servers` names a subset.
- The verification step now **asserts that `ledger.py` and `mediation.py` are
  byte-identical across everything it installed** and stops if they are not.
  Nothing else enforces that invariant at install time, and two envelope
  versions in one environment is precisely the sort of thing that would be found
  later, in a deposit.
- **`install.ps1` installs the family.** Vendored byte-identical into all six
  repositories: it installs any or all of the six into one environment, asks once
  for the receipts folder and the session slug, and registers every server against
  the same pair. It prefers a sibling checkout to the network, carries across
  credentials already registered rather than asking again, and stops rather than
  guessing where the registered servers disagree about either value.
- **`src/` layout. Breaking: the server is started by console script, not by
  path.** `server.py` and `ledger.py` move to `src/openalex_mcp/` and install as a
  package. The flat layout installed them as *top-level* modules, so any two
  servers of this family in one environment overwrote each other — and
  `pip check` reported nothing wrong. The later install simply won, silently,
  and the survivor answered under the wrong server's name. All six now coexist:
  verified by installing every wheel into one environment and driving each
  through `initialize` and `tools/list`.
- **Claude Desktop entries must change.** Replace
  `"command": "…\\python.exe", "args": ["…\\server.py"]` with
  `"command": "…\\Scripts\\openalex-mcp.exe"`. An existing entry keeps working
  against an existing flat deployment and will fail against this one.
- `python -m openalex_mcp` and a `openalex-mcp-ledger` console script are installed
  alongside it.
- **The server reports its build.** `initialize` was answered with an empty
  `serverInfo.version`. It now carries `__version__` where the SDK accepts one
  (mcp 2.x `MCPServer`). Under mcp 1.x, whose `FastMCP` takes no `version`, the
  field still reports the SDK's version rather than the server's — the argument
  is passed only where it is accepted.
- The `[tool.hatch.build.targets.wheel]` comment claimed a `src` layout the
  repository did not have. It does now.

## 1.0.0 — 2026-08-22

**Never tagged.** This version was merged to `main` and no release was cut for
it; it has no tag and no DOI.

- MCP stdio server for the OpenAlex API: eight tools over works, authors,
  sources, institutions and citation relations.
- Append-only, hash-chained query receipts via `ledger.py`, recorded from inside
  the HTTP helper so what is logged is what was sent. **Off unless
  `MCP_RECEIPT_LOG` is set**, and a logging failure is swallowed rather than
  raised.
- Sends `OPENALEX_API_KEY` under the regime that replaced the polite pool in
  February 2026; `mailto` is ignored by OpenAlex and `OPENALEX_EMAIL` survives
  only for mirrors that still honour it.
- Runs on `mcp` 1.x and 2.x.

Note for anyone citing this server as an instrument: it does not vendor
`mediation.py`, so its receipts carry no `searched_for` headline and no typed
envelope, and it has no equivalent of the `RECEIPT_NOT_DEPOSITED` diagnostic
that the envelope servers gained in schema 2.3.0.
