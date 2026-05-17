#!/usr/bin/env python3
"""Search arXiv papers via API. Returns JSON."""

import sys
import json
import argparse
import time
import xml.etree.ElementTree as ET

try:
    import requests
except ImportError:
    print(json.dumps({"error": "pip install requests"}))
    sys.exit(1)

ARXIV_API = "http://export.arxiv.org/api/query"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "sci-search/1.0 (academic tool)"})
NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def search(query, max_results=10, sortby="relevance"):
    sort_map = {
        "relevance": "relevance",
        "recent": "submittedDate",
        "lastUpdatedDate": "lastUpdatedDate",
    }
    params = {
        "search_query": f"all:{query}",
        "max_results": max_results,
        "sortBy": sort_map.get(sortby, "relevance"),
        "sortOrder": "descending",
    }
    for attempt in range(3):
        try:
            resp = SESSION.get(ARXIV_API, params=params, timeout=30)
            if resp.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            resp.raise_for_status()
            break
        except requests.exceptions.HTTPError:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))

    root = ET.fromstring(resp.text)
    papers = []
    for entry in root.findall("atom:entry", NS):
        title = entry.findtext("atom:title", "", NS).strip().replace("\n", " ")
        summary = entry.findtext("atom:summary", "", NS).strip().replace("\n", " ")
        eid = entry.findtext("atom:id", "", NS)
        arxiv_id = eid.split("/abs/")[-1] if "/abs/" in eid else eid
        published = entry.findtext("atom:published", "", NS)[:10]
        updated = entry.findtext("atom:updated", "", NS)[:10]

        authors = [
            a.findtext("atom:name", "", NS)
            for a in entry.findall("atom:author", NS)
        ]

        categories = [
            c.get("term", "")
            for c in entry.findall("atom:category", NS)
        ]

        pdf_url = ""
        for link in entry.findall("atom:link", NS):
            if link.get("title") == "pdf":
                pdf_url = link.get("href", "")
                break

        papers.append({
            "source": "arxiv",
            "arxiv_id": arxiv_id,
            "title": title,
            "authors": authors[:5],
            "abstract": summary[:2000],
            "published": published,
            "updated": updated,
            "url": eid,
            "pdf_url": pdf_url,
            "categories": categories,
        })

    return papers


def main():
    p = argparse.ArgumentParser(description="Search arXiv")
    p.add_argument("query")
    p.add_argument("-n", "--max-results", type=int, default=10)
    p.add_argument("-s", "--sort", default="relevance",
                   choices=["relevance", "recent"])
    args = p.parse_args()
    results = search(args.query, args.max_results, args.sort)
    print(json.dumps({"query": args.query, "count": len(results),
                       "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
