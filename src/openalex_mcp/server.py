"""
OpenAlex MCP Server
====================
An MCP server providing access to the OpenAlex API for searching and exploring
scholarly works, authors, sources (journals), institutions, and topics across
240M+ works in the global scholarly graph.

Data source: OpenAlex API (https://api.openalex.org)
API key (free): https://openalex.org/settings/api
Set via environment variable OPENALEX_API_KEY.
Contact email set via OPENALEX_EMAIL (used as mailto parameter for polite pool).
"""

import json
import os
from typing import Optional, List, Dict, Any
from enum import Enum

import httpx
from pydantic import BaseModel, Field, ConfigDict, field_validator
try:  # mcp SDK 1.x
    from mcp.server.fastmcp import FastMCP as _MCPServer
except ModuleNotFoundError:  # mcp SDK 2.x removed mcp.server.fastmcp
    from mcp.server.mcpserver import MCPServer as _MCPServer

from . import ledger

# ==============================================================================
# Configuration
# ==============================================================================

API_BASE = "https://api.openalex.org"
API_KEY = os.environ.get("OPENALEX_API_KEY", "")
EMAIL = os.environ.get("OPENALEX_EMAIL", "")
TIMEOUT = 30

# ==============================================================================
# HTTP Client
# ==============================================================================


async def _oa_request(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Make a request to the OpenAlex API."""
    if params is None:
        params = {}

    # Authentication: API key takes precedence, otherwise use polite email
    if API_KEY:
        params["api_key"] = API_KEY
    elif EMAIL:
        params["mailto"] = EMAIL

    url = f"{API_BASE}/{endpoint}"

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(url, params=params)

    if resp.status_code == 404:
        out = {"error": "Not found. Check the ID or query."}
    elif resp.status_code == 429:
        out = {"error": "Rate limit exceeded. Wait and retry."}
    elif resp.status_code >= 400:
        out = {"error": f"OpenAlex API error {resp.status_code}: {resp.text[:500]}"}
    else:
        out = resp.json()

    # Query receipt. Records what was sent to OpenAlex, not what was displayed.
    ledger.record_request(
        server="openalex", operation=endpoint, endpoint=url,
        params=params, response=out,
    )
    return out


def _format_work(w: Dict) -> str:
    """Format an OpenAlex work into readable text."""
    parts = []
    title = w.get("display_name") or w.get("title") or "Untitled"
    year = w.get("publication_year", "n.d.")
    parts.append(f"**{title}** ({year})")

    # Authors
    authorships = w.get("authorships", [])
    if authorships:
        names = []
        for a in authorships[:5]:
            name = a.get("author", {}).get("display_name", "?")
            names.append(name)
        if len(authorships) > 5:
            names.append(f"… +{len(authorships)-5} more")
        parts.append(f"  Authors: {', '.join(names)}")

    # Source / journal
    primary = w.get("primary_location", {})
    if primary:
        source = primary.get("source", {})
        if source:
            parts.append(f"  Source: {source.get('display_name', '?')}")

    # Citations
    cited = w.get("cited_by_count")
    if cited is not None:
        parts.append(f"  Citations: {cited}")

    # Type
    wtype = w.get("type_crossref") or w.get("type")
    if wtype:
        parts.append(f"  Type: {wtype}")

    # Open Access
    oa = w.get("open_access", {})
    if oa.get("is_oa"):
        oa_url = oa.get("oa_url")
        parts.append(f"  Open Access: Yes{' — ' + oa_url if oa_url else ''}")

    # DOI
    doi = w.get("doi")
    if doi:
        parts.append(f"  DOI: {doi}")

    # OpenAlex ID
    oa_id = w.get("id")
    if oa_id:
        parts.append(f"  OpenAlex: {oa_id}")

    # Abstract
    abstract_idx = w.get("abstract_inverted_index")
    if abstract_idx:
        try:
            # Reconstruct abstract from inverted index
            pos_word = []
            for word, positions in abstract_idx.items():
                for pos in positions:
                    pos_word.append((pos, word))
            pos_word.sort()
            abstract = " ".join(w for _, w in pos_word)
            if len(abstract) > 400:
                abstract = abstract[:400] + "…"
            parts.append(f"  Abstract: {abstract}")
        except Exception:
            pass

    # Topics
    topics = w.get("topics", [])
    if topics:
        topic_names = [t.get("display_name", "?") for t in topics[:3]]
        parts.append(f"  Topics: {', '.join(topic_names)}")

    return "\n".join(parts)


def _format_author(a: Dict) -> str:
    """Format an OpenAlex author into readable text."""
    name = a.get("display_name", "?")
    works = a.get("works_count", "?")
    cited = a.get("cited_by_count", "?")
    h_index = a.get("summary_stats", {}).get("h_index", "?")

    affils = a.get("affiliations", [])
    current_affil = "No affiliation listed"
    if affils:
        current = [af for af in affils if af.get("years") and max(af["years"]) >= 2023]
        if current:
            current_affil = current[0].get("institution", {}).get("display_name", "?")
        else:
            current_affil = affils[0].get("institution", {}).get("display_name", "?")

    oa_id = a.get("id", "")
    orcid = a.get("orcid") or ""

    return (
        f"**{name}** — {current_affil}\n"
        f"  Works: {works} | Citations: {cited} | h-index: {h_index}\n"
        f"  OpenAlex: {oa_id}"
        + (f"\n  ORCID: {orcid}" if orcid else "")
    )


def _format_source(s: Dict) -> str:
    """Format an OpenAlex source (journal/repo) into readable text."""
    name = s.get("display_name", "?")
    stype = s.get("type", "?")
    works = s.get("works_count", "?")
    cited = s.get("cited_by_count", "?")
    is_oa = s.get("is_oa", False)
    issn = s.get("issn_l", "")
    url = s.get("homepage_url", "")
    oa_id = s.get("id", "")

    return (
        f"**{name}** ({stype})\n"
        f"  Works: {works} | Citations: {cited} | Open Access: {'Yes' if is_oa else 'No'}\n"
        + (f"  ISSN: {issn}\n" if issn else "")
        + (f"  Homepage: {url}\n" if url else "")
        + f"  OpenAlex: {oa_id}"
    )


# ==============================================================================
# Server
# ==============================================================================

__version__ = "1.1.0"

# mcp 1.x's FastMCP takes no `version`; 2.x's MCPServer does. Passed where it is
# accepted, because a server that answers `initialize` with an empty version
# string cannot be cited by the disclosure that has to name the build it ran.
try:
    mcp = _MCPServer("openalex_mcp", version=__version__)
except TypeError:  # mcp SDK 1.x
    mcp = _MCPServer("openalex_mcp")

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


@mcp.tool(
    name="oa_search_works",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def oa_search_works(params: WorkSearchInput) -> str:
    """Search OpenAlex for scholarly works (articles, books, datasets, theses) across 240M+ records. Supports filtering by year, author, institution, source/journal, and open access status. Returns titles, authors, abstracts, citation counts, DOIs, and topics."""
    qp: Dict[str, Any] = {"search": params.query, "per-page": params.per_page, "page": params.page}

    filters = []
    if params.year_from and params.year_to:
        filters.append(f"publication_year:{params.year_from}-{params.year_to}")
    elif params.year_from:
        filters.append(f"publication_year:>{params.year_from - 1}")
    elif params.year_to:
        filters.append(f"publication_year:<{params.year_to + 1}")

    if params.author_id:
        filters.append(f"authorships.author.id:{params.author_id}")
    if params.institution_id:
        filters.append(f"authorships.institutions.id:{params.institution_id}")
    if params.source_id:
        filters.append(f"primary_location.source.id:{params.source_id}")
    if params.open_access is True:
        filters.append("is_oa:true")

    if filters:
        qp["filter"] = ",".join(filters)

    if params.sort_by:
        qp["sort"] = f"{params.sort_by}:desc"

    data = await _oa_request("works", qp)
    if "error" in data:
        return f"Error: {data['error']}"

    results = data.get("results", [])
    total = data.get("meta", {}).get("count", 0)

    if not results:
        return f"No works found for '{params.query}'."

    lines = [f"**OpenAlex works: '{params.query}'** — {total:,} total, page {params.page}\n"]
    for i, w in enumerate(results, 1):
        lines.append(f"---\n{i}. {_format_work(w)}")

    if total > params.page * params.per_page:
        lines.append(f"\n→ More results available. Use page={params.page + 1} to continue.")

    return "\n".join(lines)


@mcp.tool(
    name="oa_get_work",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def oa_get_work(params: WorkLookupInput) -> str:
    """Look up a specific work by its OpenAlex ID, DOI, or PMID. Returns full metadata including abstract, citation counts, open access links, and topics."""
    work_id = params.work_id
    # Handle DOI format
    if work_id.startswith("10."):
        work_id = f"https://doi.org/{work_id}"

    data = await _oa_request(f"works/{work_id}")
    if "error" in data:
        return f"Error: {data['error']}"

    return _format_work(data)


@mcp.tool(
    name="oa_search_authors",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def oa_search_authors(params: AuthorSearchInput) -> str:
    """Search OpenAlex for authors by name. Returns disambiguated author profiles with affiliations, work counts, citation counts, and h-index."""
    qp: Dict[str, Any] = {"search": params.query, "per-page": params.per_page, "page": params.page}

    if params.institution_id:
        qp["filter"] = f"affiliations.institution.id:{params.institution_id}"

    data = await _oa_request("authors", qp)
    if "error" in data:
        return f"Error: {data['error']}"

    results = data.get("results", [])
    total = data.get("meta", {}).get("count", 0)

    if not results:
        return f"No authors found for '{params.query}'."

    lines = [f"**OpenAlex authors: '{params.query}'** — {total:,} total\n"]
    for i, a in enumerate(results, 1):
        lines.append(f"---\n{i}. {_format_author(a)}")

    return "\n".join(lines)


@mcp.tool(
    name="oa_get_author",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def oa_get_author(params: AuthorLookupInput) -> str:
    """Look up a specific author by OpenAlex ID or ORCID. Returns full profile with affiliations, work count, citation count, and h-index."""
    data = await _oa_request(f"authors/{params.author_id}")
    if "error" in data:
        return f"Error: {data['error']}"

    return _format_author(data)


@mcp.tool(
    name="oa_search_sources",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def oa_search_sources(params: SourceSearchInput) -> str:
    """Search OpenAlex for sources: journals, repositories, and conferences. Returns work counts, citation data, and open access status."""
    qp: Dict[str, Any] = {"search": params.query, "per-page": params.per_page, "page": params.page}

    if params.type:
        qp["filter"] = f"type:{params.type}"

    data = await _oa_request("sources", qp)
    if "error" in data:
        return f"Error: {data['error']}"

    results = data.get("results", [])
    total = data.get("meta", {}).get("count", 0)

    if not results:
        return f"No sources found for '{params.query}'."

    lines = [f"**OpenAlex sources: '{params.query}'** — {total:,} total\n"]
    for i, s in enumerate(results, 1):
        lines.append(f"---\n{i}. {_format_source(s)}")

    return "\n".join(lines)


@mcp.tool(
    name="oa_search_institutions",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def oa_search_institutions(params: InstitutionSearchInput) -> str:
    """Search OpenAlex for institutions (universities, research organizations). Useful for finding institution IDs to use as filters in work searches."""
    qp: Dict[str, Any] = {"search": params.query, "per-page": params.per_page, "page": params.page}

    if params.country_code:
        qp["filter"] = f"country_code:{params.country_code}"

    data = await _oa_request("institutions", qp)
    if "error" in data:
        return f"Error: {data['error']}"

    results = data.get("results", [])
    total = data.get("meta", {}).get("count", 0)

    if not results:
        return f"No institutions found for '{params.query}'."

    lines = [f"**OpenAlex institutions: '{params.query}'** — {total:,} total\n"]
    for i, inst in enumerate(results, 1):
        name = inst.get("display_name", "?")
        country = inst.get("country_code", "?")
        itype = inst.get("type", "?")
        works = inst.get("works_count", "?")
        cited = inst.get("cited_by_count", "?")
        oa_id = inst.get("id", "")
        ror = inst.get("ror", "")
        lines.append(
            f"{i}. **{name}** ({country}, {itype})\n"
            f"   Works: {works} | Citations: {cited}\n"
            f"   OpenAlex: {oa_id}"
            + (f"\n   ROR: {ror}" if ror else "")
        )

    return "\n".join(lines)


@mcp.tool(
    name="oa_cited_by",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def oa_cited_by(params: CitedByInput) -> str:
    """Get works that cite a specific work. Forward citation traversal for exploring a paper's impact and downstream research."""
    work_id = params.work_id
    if work_id.startswith("10."):
        work_id = f"https://doi.org/{work_id}"

    qp: Dict[str, Any] = {
        "filter": f"cites:{work_id}",
        "per-page": params.per_page,
        "page": params.page,
        "sort": "cited_by_count:desc",
    }

    data = await _oa_request("works", qp)
    if "error" in data:
        return f"Error: {data['error']}"

    results = data.get("results", [])
    total = data.get("meta", {}).get("count", 0)

    if not results:
        return "No citing works found."

    lines = [f"**Works citing {params.work_id}** — {total:,} total\n"]
    for i, w in enumerate(results, 1):
        lines.append(f"---\n{i}. {_format_work(w)}")

    return "\n".join(lines)


@mcp.tool(
    name="oa_author_works",
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def oa_author_works(params: AuthorWorksInput) -> str:
    """Get all works by a specific author. Supports year filtering and sorting by citation count or publication date."""
    filters = [f"authorships.author.id:{params.author_id}"]

    if params.year_from and params.year_to:
        filters.append(f"publication_year:{params.year_from}-{params.year_to}")
    elif params.year_from:
        filters.append(f"publication_year:>{params.year_from - 1}")
    elif params.year_to:
        filters.append(f"publication_year:<{params.year_to + 1}")

    qp: Dict[str, Any] = {
        "filter": ",".join(filters),
        "per-page": params.per_page,
        "page": params.page,
    }

    if params.sort_by:
        qp["sort"] = f"{params.sort_by}:desc"

    data = await _oa_request("works", qp)
    if "error" in data:
        return f"Error: {data['error']}"

    results = data.get("results", [])
    total = data.get("meta", {}).get("count", 0)

    if not results:
        return "No works found for this author."

    lines = [f"**Works by {params.author_id}** — {total:,} total\n"]
    for i, w in enumerate(results, 1):
        lines.append(f"---\n{i}. {_format_work(w)}")

    return "\n".join(lines)


# ==============================================================================
# Entry point
# ==============================================================================

def main() -> None:
    """Console-script entry point (`openalex-mcp`)."""
    mcp.run()


if __name__ == "__main__":
    main()
