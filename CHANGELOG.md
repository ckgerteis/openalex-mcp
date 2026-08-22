# Changelog

Versions are the thing to cite. A count produced under one release is not
reproducible against another, so the release actually used should be named in
the text and, where a version DOI exists, cited by it.

Releases earlier than those below are on the repository's releases page; this
file begins where the record is precise enough to be worth writing down.

## 1.0.0 — 2026-08-22

First tagged release.

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
