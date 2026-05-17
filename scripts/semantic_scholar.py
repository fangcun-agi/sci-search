#!/usr/bin/env python3
"""Search Semantic Scholar papers via API. Returns JSON."""

import sys
import json
import argparse
import time

try:
    import requests
except ImportError:
    print(json.dumps({"error": "pip install requests"}))
    sys.exit(1)

S2_API = "https://api.semanticscholar.org/graph/v1"
FIELDS = "title,abstract,url,year,authors,citationCount,venue,externalIds,openAccessPdf"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "sci-search/1.0 (academic tool)"})


def search(query, limit=10, year_from=None, year_to=None):
    params = {
        "query": query,
        "limit": limit,
        "fields": FIELDS,
    }
    if year_from or year_to:
        yf = year_from or "1900"
        yt = year_to or "2099"
        params["year"] = f"{yf}-{yt}"

    for attempt in range(3):
        resp = SESSION.get(f"{S2_API}/paper/search", params=params, timeout=30)
        if resp.status_code == 429:
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            return {"error": "Semantic Scholar rate limit after retries", "results": []}
        resp.raise_for_status()
        break

    data = resp.json()

    papers = []
    for item in data.get("data", []):
        ext = item.get("externalIds") or {}
        authors = [
            a.get("name", "")
            for a in (item.get("authors") or [])
        ]
        oa_pdf = item.get("openAccessPdf") or {}

        papers.append({
            "source": "semantic_scholar",
            "paper_id": item.get("paperId", ""),
            "title": item.get("title", ""),
            "authors": authors[:5],
            "abstract": (item.get("abstract") or "")[:2000],
            "year": item.get("year"),
            "venue": item.get("venue", ""),
            "citations": item.get("citationCount", 0),
            "url": item.get("url", ""),
            "doi": ext.get("DOI", ""),
            "arxiv_id": ext.get("ArXiv", ""),
            "pmid": ext.get("PubMed", ""),
            "open_access_pdf": oa_pdf.get("url", ""),
        })

    return {
        "query": query,
        "total": data.get("total", len(papers)),
        "count": len(papers),
        "results": papers,
    }


def main():
    p = argparse.ArgumentParser(description="Search Semantic Scholar")
    p.add_argument("query")
    p.add_argument("-n", "--limit", type=int, default=10)
    p.add_argument("--year-from", type=int, default=None)
    p.add_argument("--year-to", type=int, default=None)
    args = p.parse_args()
    result = search(args.query, args.limit, args.year_from, args.year_to)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
