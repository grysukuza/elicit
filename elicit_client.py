"""
Elicit API client.
Wraps the search and reports endpoints at https://elicit.com/api/v1/
"""

import os
import time
from typing import Optional, List
import requests
from requests import RequestException
from requests.exceptions import JSONDecodeError
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ.get("ELICIT_API_BASE_URL", "https://elicit.com/api/v1").rstrip("/")
DEFAULT_TIMEOUT = 30  # seconds


def _headers() -> dict:
    key = os.environ.get("ELICIT_API_KEY", "").strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in ("'", '"'):
        key = key[1:-1].strip()
    if not key:
        raise EnvironmentError("ELICIT_API_KEY not set in environment / .env")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _raise_api_error(resp: requests.Response, operation: str) -> None:
    """Raise a readable error for failed Elicit requests."""
    try:
        body = resp.json()
        detail = body.get("error") or body.get("message") or "No detail provided."
        detail = str(detail).strip()[:120]
    except JSONDecodeError:
        detail = "Unexpected non-JSON error response."
    raise RuntimeError(
        f"Elicit API {operation} failed ({resp.status_code}): {detail}"
    )


def search_papers(
    query: str,
    max_results: int = 20,
    type_tags: Optional[List[str]] = None,
    pubmed_only: bool = False,
    min_year: Optional[int] = None,
    max_year: Optional[int] = None,
) -> List[dict]:
    """
    Search Elicit for academic papers.

    Returns a list of paper dicts with keys:
        title, authors, year, abstract, doi, pmid, venue,
        citedByCount, urls, elicitId
    """
    payload: dict = {
        "query": query,
        "maxResults": max(1, min(max_results, 5000)),
    }

    filters: dict = {}
    if type_tags:
        filters["typeTags"] = type_tags
    if pubmed_only:
        filters["pubmedOnly"] = True
    if min_year is not None:
        filters["minYear"] = min_year
    if max_year is not None:
        filters["maxYear"] = max_year
    filters["retracted"] = "exclude_retracted"
    payload["filters"] = filters

    try:
        resp = requests.post(
            f"{BASE_URL}/search",
            json=payload,
            headers=_headers(),
            timeout=DEFAULT_TIMEOUT,
        )
    except RequestException as exc:
        raise RuntimeError(f"Elicit API search request failed: {exc}") from exc

    if resp.status_code == 429:
        reset = resp.headers.get("X-RateLimit-Reset", "unknown")
        raise RuntimeError(f"Elicit rate limit exceeded. Resets at: {reset}")
    if not resp.ok:
        _raise_api_error(resp, "search")

    data = resp.json()
    papers = data.get("papers", [])
    return papers


def create_report(
    research_question: str,
    max_search_papers: int = 50,
    max_extract_papers: int = 10,
    is_public: bool = False,
) -> dict:
    """
    Submit an asynchronous Elicit report.
    Returns the initial report dict including reportId and status URL.
    """
    payload = {
        "researchQuestion": research_question,
        "maxSearchPapers": max_search_papers,
        "maxExtractPapers": max_extract_papers,
        "isPublic": is_public,
    }
    try:
        resp = requests.post(
            f"{BASE_URL}/reports",
            json=payload,
            headers=_headers(),
            timeout=DEFAULT_TIMEOUT,
        )
    except RequestException as exc:
        raise RuntimeError(f"Elicit API report creation failed: {exc}") from exc
    if not resp.ok:
        _raise_api_error(resp, "create_report")
    return resp.json()


def get_report(report_id: str, include_body: bool = True) -> dict:
    """
    Poll a single report by ID.
    Pass include_body=True to retrieve the full markdown report body.
    """
    params = {}
    if include_body:
        params["include"] = "reportBody"
    try:
        resp = requests.get(
            f"{BASE_URL}/reports/{report_id}",
            params=params,
            headers=_headers(),
            timeout=DEFAULT_TIMEOUT,
        )
    except RequestException as exc:
        raise RuntimeError(f"Elicit API report fetch failed: {exc}") from exc
    if not resp.ok:
        _raise_api_error(resp, "get_report")
    return resp.json()


def wait_for_report(
    report_id: str,
    poll_interval: int = 30,
    max_wait: int = 900,
) -> dict:
    """
    Poll a report until completed/failed or timeout.

    Args:
        report_id: UUID of the report.
        poll_interval: Seconds between polls (default 30).
        max_wait: Maximum total seconds to wait (default 900 = 15 min).

    Returns:
        Completed report dict.

    Raises:
        RuntimeError if report fails or times out.
    """
    elapsed = 0
    while elapsed < max_wait:
        report = get_report(report_id, include_body=True)
        status = report.get("status")
        if status == "completed":
            return report
        if status == "failed":
            raise RuntimeError(f"Elicit report {report_id} failed.")
        time.sleep(poll_interval)
        elapsed += poll_interval
    raise RuntimeError(
        f"Elicit report {report_id} did not complete within {max_wait}s."
    )
