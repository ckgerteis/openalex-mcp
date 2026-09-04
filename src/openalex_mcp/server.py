"""
OpenAlex MCP Server (v2.0.0)
============================
An MCP server for the OpenAlex API — the open scholarly graph maintained by
OurResearch, covering works, authors, sources (journals), and institutions.

v2.0.0 — clean replacement of the response format. Every tool now emits the
unified response envelope shared across the server family (see mediation.py /
response-schema.json): typed query/script, matching_mode, graduated breadth,
per-item matched_in, typed diagnostics, a loggable receipt, and attribution.
This is a breaking change from v1.x, which returned formatted markdown text.

Data source: OpenAlex API (https://api.openalex.org)
API key (free): https://openalex.org/settings/api — set via OPENALEX_API_KEY.
OPENALEX_EMAIL is sent as `mailto` only when no key is set; OpenAlex itself no
longer reads it, but mirrors of the API may.
"""
from __future__ import annotations

import logging
import os
import re
import sys
from typing import Any, Dict, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field
try:  # mcp SDK 1.x
    from mcp.server.fastmcp import FastMCP as _MCPServer
except ModuleNotFoundError:  # mcp SDK 2.x removed mcp.server.fastmcp
    from mcp.server.mcpserver import MCPServer as _MCPServer

from . import mediation as M

__version__ = "2.0.0"

# ==============================================================================
# Configuration
# ==============================================================================

API_BASE = "https://api.openalex.org"
API_KEY = os.environ.get("OPENALEX_API_KEY", "")
EMAIL = os.environ.get("OPENALEX_EMAIL", "")
TIMEOUT = 30.0
ATTRIBUTION = "Data via OpenAlex (https://openalex.org), OurResearch. CC0."

# OpenAlex's `search` parameter matches title, abstract and (where indexed)
# full text, with stemming and stop-word removal. A high total is therefore a
# loose match, not a catalogued one; the mode name says so.
MODE_SEARCH = "full_text_stemmed"
# Lists produced by `filter=` alone (citations of a work, works of an author)
# match an identifier exactly and choose no term.
MODE_FILTER = "filter_exact"
MODE_LOOKUP = "identifier_lookup"

_SECRET_PARAMS = ("api_key", "mailto")


def _silence_http_logging() -> None:
    """Two reasons, either sufficient on its own.

    httpx logs every request at INFO with the full URL — and the OpenAlex key
    travels in the query string, so a default logging setup writes the
    credential into whatever stream the client is capturing.

    Second, this is a stdio server: stdout carries JSON-RPC and nothing else.
    Any handler that defaults to stdout corrupts the protocol frame.
    """
    for name in ("httpx", "httpcore", "httpx._client"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.WARNING)
        lg.propagate = False
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "stream", None) is sys.stdout:
            root.removeHandler(h)
    if not root.handlers:
        root.addHandler(logging.StreamHandler(sys.stderr))


_silence_http_logging()

# mcp 1.x's FastMCP takes no `version`; 2.x's MCPServer does. Passed where it is
# accepted, because a server that answers `initialize` with an empty version
# string cannot be cited by the disclosure that has to name the build it ran.
try:
    mcp = _MCPServer("openalex_mcp", version=__version__)
except TypeError:  # mcp SDK 1.x
    mcp = _MCPServer("openalex_mcp")


# ==============================================================================
# HTTP client
# ==============================================================================


def _redact(text: str) -> str:
    """Strip the key from any text that might reach a diagnostic."""
    if API_KEY and API_KEY in text:
        text = text.replace(API_KEY, "[redacted]")
    return text


async def _oa_request(
    endpoint: str, params: Optional[Dict[str, Any]] = None
) -> tuple[Optional[Any], Optional[dict]]:
    """Call one OpenAlex endpoint.

    Returns (data, error_diag). Exactly one is non-None. The caller's `params`
    is never mutated: the credential is added to a copy, so the dict the caller
    goes on to place in the envelope carries no secret.
    """
    sent: Dict[str, Any] = dict(params or {})
    if API_KEY:
        sent["api_key"] = API_KEY
    elif EMAIL:
        sent["mailto"] = EMAIL
    url = f"{API_BASE}/{endpoint}"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
            resp = await client.get(url, params=sent)
    except httpx.HTTPError as exc:
        return None, M.diag(
            "error", "TRANSPORT_ERROR",
            f"Could not reach OpenAlex: {_redact(type(exc).__name__ + ': ' + str(exc))[:300]}",
            "The result of this search is unknown, not empty. Retry before "
            "concluding anything about the literature.",
        )

    if resp.status_code == 404:
        return None, M.diag(
            "warning", "NOT_FOUND",
            "OpenAlex has no record for this identifier.",
            "Check the ID form: W…, A…, S…, I… OpenAlex IDs, a bare DOI, an "
            "ORCID, or a PMID.",
        )
    if resp.status_code == 429:
        return None, M.diag(
            "error", "RATE_LIMITED",
            "OpenAlex answered 429: the request rate was exceeded.",
            "Wait and retry. An API key raises the daily and per-second allowance.",
        )
    if resp.status_code >= 400:
        return None, M.diag(
            "error", "API_ERROR",
            f"OpenAlex answered {resp.status_code}: {_redact(resp.text[:300])}",
            None,
        )
    try:
        return resp.json(), None
    except ValueError:
        return None, M.diag(
            "error", "API_ERROR",
            "OpenAlex answered 200 with a body that is not JSON.",
            "Retry; if it persists the API or an intermediary is misbehaving.",
        )


# ==============================================================================
# Record builders
# ==============================================================================


def _bare_doi(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.I) or None


def _short_id(oa_id: Optional[str]) -> Optional[str]:
    """'https://openalex.org/W123' -> 'W123'. The full URL stays in ids.url_en."""
    if not oa_id:
        return None
    return oa_id.rsplit("/", 1)[-1]


def _abstract(w: dict) -> Optional[str]:
    idx = w.get("abstract_inverted_index")
    if not isinstance(idx, dict):
        return None
    try:
        pos_word = [(p, word) for word, positions in idx.items() for p in positions]
    except (TypeError, AttributeError):
        return None
    pos_word.sort()
    text = " ".join(word for _, word in pos_word)
    return text[:400] + "…" if len(text) > 400 else (text or None)


def _place_title(text: Optional[str], language: Optional[str]) -> dict:
    """Route a display name into the typed title slots.

    OpenAlex reports a `language` on works; where it does, that decides. Where
    it does not, a Latin-script title is placed in `en` (the family's slot for
    non-CJK text) and a CJK title is left out of the typed slots altogether —
    a han-only string could be Chinese or Japanese, and the server will not
    guess. The untyped text is always kept in `extra.title`.
    """
    out = {"title_ja": None, "title_ko": None, "title_en": None}
    if not text:
        return out
    script = M.detect_script(text)
    if language == "ja" or (not language and script in ("kana", "han_kana")):
        out["title_ja"] = text
    elif language == "ko" or (not language and script in ("hangul", "han_hangul")):
        out["title_ko"] = text
    elif script == "latin":
        # `en` is the family's slot for non-CJK text. A Latin-script title in
        # another language still lands here, as it does in the sibling servers;
        # the language code is kept beside it in extra.language.
        out["title_en"] = text
    # A CJK title that OpenAlex marks neither ja nor ko (e.g. zh), or a han-only
    # string with no language, stays untyped: extra.title carries it.
    return out


def _item_from_work(w: dict, matched_in: str) -> dict:
    title = w.get("display_name") or w.get("title")
    language = w.get("language")
    authors = []
    for a in (w.get("authorships") or [])[:12]:
        au = a.get("author") or {}
        insts = [i.get("display_name") for i in (a.get("institutions") or []) if i.get("display_name")]
        authors.append({
            "name": au.get("display_name"),
            "orcid": au.get("orcid"),
            "openalex_id": _short_id(au.get("id")),
            "affiliation": "; ".join(insts) or None,
        })
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    biblio = w.get("biblio") or {}
    fp, lp = biblio.get("first_page"), biblio.get("last_page")
    pages = f"{fp}-{lp}" if fp and lp else (fp or None)
    oa = w.get("open_access") or {}
    best = w.get("best_oa_location") or {}
    ids = w.get("ids") or {}

    return M.make_item(
        **_place_title(title, language),
        authors=authors,
        journal_en=src.get("display_name"),
        volume=biblio.get("volume"),
        issue=biblio.get("issue"),
        pages=pages,
        year=w.get("publication_year"),
        doi=_bare_doi(w.get("doi")),
        issn=src.get("issn_l"),
        url_en=loc.get("landing_page_url") or w.get("id"),
        fulltext_url=oa.get("oa_url") or best.get("pdf_url"),
        matched_in=matched_in,
        record_type=w.get("type") or "article",
        extra={
            "title": title,
            "language": language,
            "openalex_id": _short_id(w.get("id")),
            "pmid": _short_id(ids.get("pmid")),
            "type_crossref": w.get("type_crossref"),
            "cited_by_count": w.get("cited_by_count"),
            "is_oa": oa.get("is_oa"),
            "publication_date": w.get("publication_date"),
            "topics": [t.get("display_name") for t in (w.get("topics") or [])[:3]],
            "abstract": _abstract(w),
        },
    )


def _item_from_author(a: dict, matched_in: str) -> dict:
    affils = []
    for af in a.get("affiliations") or []:
        inst = af.get("institution") or {}
        years = af.get("years") or []
        affils.append({"name": inst.get("display_name"), "years": sorted(years)})
    stats = a.get("summary_stats") or {}
    return M.make_item(
        title_en=a.get("display_name"),
        url_en=a.get("id"),
        matched_in=matched_in,
        record_type="author",
        extra={
            "openalex_id": _short_id(a.get("id")),
            "orcid": a.get("orcid"),
            "works_count": a.get("works_count"),
            "cited_by_count": a.get("cited_by_count"),
            "h_index": stats.get("h_index"),
            "affiliations": affils,
        },
    )


def _item_from_source(s: dict, matched_in: str) -> dict:
    return M.make_item(
        title_en=s.get("display_name"),
        issn=s.get("issn_l"),
        url_en=s.get("homepage_url") or s.get("id"),
        matched_in=matched_in,
        record_type="source",
        extra={
            "openalex_id": _short_id(s.get("id")),
            "type": s.get("type"),
            "publisher": s.get("host_organization_name"),
            "works_count": s.get("works_count"),
            "cited_by_count": s.get("cited_by_count"),
            "is_oa": s.get("is_oa"),
            "is_in_doaj": s.get("is_in_doaj"),
            "issns": s.get("issn"),
        },
    )


def _item_from_institution(i: dict, matched_in: str) -> dict:
    return M.make_item(
        title_en=i.get("display_name"),
        url_en=i.get("homepage_url") or i.get("id"),
        matched_in=matched_in,
        record_type="institution",
        extra={
            "openalex_id": _short_id(i.get("id")),
            "ror": i.get("ror"),
            "country_code": i.get("country_code"),
            "type": i.get("type"),
            "works_count": i.get("works_count"),
            "cited_by_count": i.get("cited_by_count"),
        },
    )


# ==============================================================================
# Envelope assembly
# ==============================================================================


def _envelope(
    *,
    operation: str,
    term: str,
    params: dict,
    matching_mode: str,
    data: Optional[Any],
    err: Optional[dict],
    build,
    matched_in: str,
    single: bool = False,
    coverage_note: Optional[str] = None,
) -> str:
    """Assemble and emit one envelope from an OpenAlex response.

    `single` marks a lookup, whose body is the record itself rather than a
    {meta, results} page; total is then 1 or 0. `params` is what the caller
    chose; the credential never enters it.
    """
    items: list[dict] = []
    total = 0
    start = 1
    ds: list[dict] = []
    if err:
        ds.append(err)
    elif single:
        if isinstance(data, dict):
            items = [build(data, matched_in)]
            total = 1
    elif isinstance(data, dict):
        results = data.get("results") or []
        items = [build(r, matched_in) for r in results if isinstance(r, dict)]
        meta = data.get("meta") or {}
        try:
            total = int(meta.get("count", len(items)))
        except (TypeError, ValueError):
            total = len(items)
        per_page = int(meta.get("per_page") or params.get("per-page") or len(items) or 1)
        page = int(meta.get("page") or params.get("page") or 1)
        start = (page - 1) * per_page + 1

    if not err and not items:
        ds.append(M.diag(
            "warning", "ZERO_RESULTS",
            "No records. OpenAlex matched nothing for this term and filter set.",
            "Vary the rendering or loosen the filters. Non-English titles are "
            "indexed as supplied by the publisher, often without translation, "
            "so an English rendering of a Japanese or Korean title may not match.",
        ))
    if not ds:
        ds.append(M.diag("info", "OK", f"{total} record(s) reported by OpenAlex.", None))

    clean = {k: v for k, v in params.items() if k not in _SECRET_PARAMS and v is not None}
    env = M.build_envelope(
        server="openalex", operation=operation,
        input_terms=term, normalized=term, params=clean,
        matching_mode=matching_mode, total=total, start=start,
        items=items, diagnostics=ds, attribution=ATTRIBUTION,
        coverage_note=coverage_note,
    )
    return M.emit(env)


def _year_filter(year_from: Optional[int], year_to: Optional[int]) -> Optional[str]:
    if year_from and year_to:
        return f"publication_year:{year_from}-{year_to}"
    if year_from:
        return f"publication_year:>{year_from - 1}"
    if year_to:
        return f"publication_year:<{year_to + 1}"
    return None


def _as_work_id(work_id: str) -> str:
    return f"https://doi.org/{work_id}" if work_id.startswith("10.") else work_id


# ==============================================================================
# Input Models
# ==============================================================================


class WorkSearchInput(BaseModel):
    """Search OpenAlex for scholarly works."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(..., description="Search query (searches title, abstract, fulltext)", min_length=1)
    year_from: Optional[int] = Field(default=None, description="Start year filter")
    year_to: Optional[int] = Field(default=None, description="End year filter")
    author_id: Optional[str] = Field(default=None, description="OpenAlex author ID filter (e.g., 'A1234567890')")
    institution_id: Optional[str] = Field(default=None, description="OpenAlex institution ID filter")
    source_id: Optional[str] = Field(default=None, description="OpenAlex source/journal ID filter")
    open_access: Optional[bool] = Field(default=None, description="Filter for open access works only")
    sort_by: Optional[str] = Field(default=None, description="Sort: 'cited_by_count', 'publication_date', 'relevance_score'")
    per_page: int = Field(default=10, description="Results per page (1-200)", ge=1, le=200)
    page: int = Field(default=1, description="Page number", ge=1)


class WorkLookupInput(BaseModel):
    """Look up a specific work by ID or DOI."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    work_id: str = Field(
        ...,
        description="OpenAlex work ID (e.g., 'W1234567890'), DOI URL, or PMID",
        min_length=1,
    )


class AuthorSearchInput(BaseModel):
    """Search OpenAlex for authors."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(..., description="Author name to search", min_length=1)
    institution_id: Optional[str] = Field(default=None, description="Filter by institution OpenAlex ID")
    per_page: int = Field(default=10, ge=1, le=200)
    page: int = Field(default=1, ge=1)


class AuthorLookupInput(BaseModel):
    """Look up a specific author."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    author_id: str = Field(..., description="OpenAlex author ID (e.g., 'A1234567890') or ORCID", min_length=1)


class SourceSearchInput(BaseModel):
    """Search OpenAlex for sources (journals, repositories, conferences)."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(..., description="Source name to search", min_length=1)
    type: Optional[str] = Field(default=None, description="Filter by type: 'journal', 'repository', 'conference'")
    per_page: int = Field(default=10, ge=1, le=200)
    page: int = Field(default=1, ge=1)


class InstitutionSearchInput(BaseModel):
    """Search OpenAlex for institutions."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(..., description="Institution name to search", min_length=1)
    country_code: Optional[str] = Field(default=None, description="ISO country code filter (e.g., 'JP', 'GB', 'US')")
    per_page: int = Field(default=10, ge=1, le=200)
    page: int = Field(default=1, ge=1)


class CitedByInput(BaseModel):
    """Get works that cite a specific work."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    work_id: str = Field(..., description="OpenAlex work ID or DOI", min_length=1)
    per_page: int = Field(default=20, ge=1, le=200)
    page: int = Field(default=1, ge=1)


class AuthorWorksInput(BaseModel):
    """Get works by a specific author."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    author_id: str = Field(..., description="OpenAlex author ID or ORCID", min_length=1)
    year_from: Optional[int] = Field(default=None, description="Start year filter")
    year_to: Optional[int] = Field(default=None, description="End year filter")
    sort_by: Optional[str] = Field(default=None, description="Sort: 'cited_by_count', 'publication_date'")
    per_page: int = Field(default=20, ge=1, le=200)
    page: int = Field(default=1, ge=1)


# ==============================================================================
# Tools
# ==============================================================================

_ANN = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}


@mcp.tool(name="oa_search_works", annotations=_ANN)
async def oa_search_works(params: WorkSearchInput) -> str:
    """Search OpenAlex for scholarly works (articles, books, datasets, theses). Returns the unified envelope.

    OpenAlex matches title, abstract and indexed full text with stemming, so
    result.total is a loose count (matching_mode full_text_stemmed) and a high
    breadth is expected. Titles are typed by OpenAlex's own language field;
    where that is absent, a CJK title is kept only in extra.title rather than
    guessed into ja or ko. Filters by year, author, institution, source and
    open-access status narrow the set exactly.
    """
    qp: Dict[str, Any] = {"search": params.query, "per-page": params.per_page, "page": params.page}
    filters = [f for f in (
        _year_filter(params.year_from, params.year_to),
        f"authorships.author.id:{params.author_id}" if params.author_id else None,
        f"authorships.institutions.id:{params.institution_id}" if params.institution_id else None,
        f"primary_location.source.id:{params.source_id}" if params.source_id else None,
        "is_oa:true" if params.open_access is True else None,
    ) if f]
    if filters:
        qp["filter"] = ",".join(filters)
    if params.sort_by:
        qp["sort"] = f"{params.sort_by}:desc"
    data, err = await _oa_request("works", qp)
    return _envelope(operation="search_works", term=params.query, params=qp,
                     matching_mode=MODE_SEARCH, data=data, err=err,
                     build=_item_from_work, matched_in="title_abstract_fulltext")


@mcp.tool(name="oa_get_work", annotations=_ANN)
async def oa_get_work(params: WorkLookupInput) -> str:
    """Look up one work by OpenAlex ID, DOI, or PMID. Returns the unified envelope with a single item, or NOT_FOUND."""
    data, err = await _oa_request(f"works/{_as_work_id(params.work_id)}")
    return _envelope(operation="get_work", term=params.work_id, params={"work_id": params.work_id},
                     matching_mode=MODE_LOOKUP, data=data, err=err,
                     build=_item_from_work, matched_in="identifier", single=True)


@mcp.tool(name="oa_search_authors", annotations=_ANN)
async def oa_search_authors(params: AuthorSearchInput) -> str:
    """Search OpenAlex for authors by name. Returns the unified envelope; each item is an author record (record_type author) with affiliations, work and citation counts, and h-index in extra."""
    qp: Dict[str, Any] = {"search": params.query, "per-page": params.per_page, "page": params.page}
    if params.institution_id:
        qp["filter"] = f"affiliations.institution.id:{params.institution_id}"
    data, err = await _oa_request("authors", qp)
    return _envelope(operation="search_authors", term=params.query, params=qp,
                     matching_mode=MODE_SEARCH, data=data, err=err,
                     build=_item_from_author, matched_in="display_name")


@mcp.tool(name="oa_get_author", annotations=_ANN)
async def oa_get_author(params: AuthorLookupInput) -> str:
    """Look up one author by OpenAlex ID or ORCID. Returns the unified envelope with a single author item, or NOT_FOUND."""
    data, err = await _oa_request(f"authors/{params.author_id}")
    return _envelope(operation="get_author", term=params.author_id, params={"author_id": params.author_id},
                     matching_mode=MODE_LOOKUP, data=data, err=err,
                     build=_item_from_author, matched_in="identifier", single=True)


@mcp.tool(name="oa_search_sources", annotations=_ANN)
async def oa_search_sources(params: SourceSearchInput) -> str:
    """Search OpenAlex for sources: journals, repositories, conferences. Returns the unified envelope (record_type source)."""
    qp: Dict[str, Any] = {"search": params.query, "per-page": params.per_page, "page": params.page}
    if params.type:
        qp["filter"] = f"type:{params.type}"
    data, err = await _oa_request("sources", qp)
    return _envelope(operation="search_sources", term=params.query, params=qp,
                     matching_mode=MODE_SEARCH, data=data, err=err,
                     build=_item_from_source, matched_in="display_name")


@mcp.tool(name="oa_search_institutions", annotations=_ANN)
async def oa_search_institutions(params: InstitutionSearchInput) -> str:
    """Search OpenAlex for institutions. Returns the unified envelope (record_type institution); useful for finding institution IDs to filter work searches."""
    qp: Dict[str, Any] = {"search": params.query, "per-page": params.per_page, "page": params.page}
    if params.country_code:
        qp["filter"] = f"country_code:{params.country_code}"
    data, err = await _oa_request("institutions", qp)
    return _envelope(operation="search_institutions", term=params.query, params=qp,
                     matching_mode=MODE_SEARCH, data=data, err=err,
                     build=_item_from_institution, matched_in="display_name")


@mcp.tool(name="oa_cited_by", annotations=_ANN)
async def oa_cited_by(params: CitedByInput) -> str:
    """Works that cite a given work, most-cited first. Returns the unified envelope. This is a filter on an identifier, not a term search, so no searched_for headline is set."""
    qp: Dict[str, Any] = {
        "filter": f"cites:{_as_work_id(params.work_id)}",
        "per-page": params.per_page, "page": params.page, "sort": "cited_by_count:desc",
    }
    data, err = await _oa_request("works", qp)
    return _envelope(operation="cited_by", term=params.work_id, params=qp,
                     matching_mode=MODE_FILTER, data=data, err=err,
                     build=_item_from_work, matched_in="referenced_works")


@mcp.tool(name="oa_author_works", annotations=_ANN)
async def oa_author_works(params: AuthorWorksInput) -> str:
    """Works by one author, with optional year filter and sort. Returns the unified envelope. A filter on an identifier, not a term search."""
    filters = [f"authorships.author.id:{params.author_id}"]
    yf = _year_filter(params.year_from, params.year_to)
    if yf:
        filters.append(yf)
    qp: Dict[str, Any] = {"filter": ",".join(filters), "per-page": params.per_page, "page": params.page}
    if params.sort_by:
        qp["sort"] = f"{params.sort_by}:desc"
    data, err = await _oa_request("works", qp)
    return _envelope(operation="author_works", term=params.author_id, params=qp,
                     matching_mode=MODE_FILTER, data=data, err=err,
                     build=_item_from_work, matched_in="authorships")


# ==============================================================================
# Entry point
# ==============================================================================

def main() -> None:
    """Console-script entry point (`openalex-mcp`)."""
    mcp.run()


if __name__ == "__main__":
    main()
