#!/usr/bin/env python3
"""
Unified academic paper search. Combines arXiv + Semantic Scholar + web search.
Returns deduplicated, ranked results as JSON.
"""

import sys
import json
import argparse
import subprocess
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def run_script(script, args, timeout=30):
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(SCRIPT_DIR, script)] + args,
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip()[:200], "source": script}
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "source": script}
    except Exception as e:
        return {"error": str(e)[:200], "source": script}


def search_arxiv(query, max_results=10):
    return run_script("arxiv_search.py", [query, "-n", str(max_results)])


def search_s2(query, limit=10, year_from=None, year_to=None):
    args = [query, "-n", str(limit)]
    if year_from:
        args += ["--year-from", str(year_from)]
    if year_to:
        args += ["--year-to", str(year_to)]
    return run_script("semantic_scholar.py", args, timeout=30)


def search_web(query, count=10):
    return run_script(
        os.path.join(os.path.dirname(SCRIPT_DIR), "..", "web-search", "scripts", "search.py"),
        [query, "-n", str(count)],
        timeout=20,
    )


def normalize_title(title):
    import re
    return re.sub(r"[^a-z0-9]", "", title.lower())


def deduplicate(all_papers):
    seen = {}
    for p in all_papers:
        key = normalize_title(p.get("title", ""))
        if not key or len(key) < 10:
            seen[id(p)] = p
            continue
        if key not in seen:
            seen[key] = p
        else:
            existing = seen[key]
            if p.get("abstract") and not existing.get("abstract"):
                seen[key] = p
            elif p.get("citations", 0) > existing.get("citations", 0):
                seen[key] = p
    return list(seen.values())


def rank_papers(papers):
    def score(p):
        s = 0
        if p.get("abstract"):
            s += 10
        if p.get("open_access_pdf"):
            s += 5
        if p.get("arxiv_id"):
            s += 3
        s += min(p.get("citations", 0) / 100, 10)
        if p.get("year"):
            s += min(max(0, p["year"] - 2015), 5)
        return s

    papers.sort(key=score, reverse=True)
    return papers


def search(query, sources="all", max_per_source=10, year_from=None, year_to=None):
    all_papers = []
    errors = []

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {}
        if sources in ("all", "arxiv"):
            futures[pool.submit(search_arxiv, query, max_per_source)] = "arxiv"
        if sources in ("all", "s2"):
            futures[pool.submit(search_s2, query, max_per_source, year_from, year_to)] = "semantic_scholar"
        if sources in ("all", "web"):
            futures[pool.submit(search_web, f"{query} site:arxiv.org OR site:semanticscholar.org", max_per_source)] = "web"

        for future in as_completed(futures):
            src = futures[future]
            try:
                data = future.result()
                if "error" in data:
                    errors.append(f"{src}: {data['error']}")
                    continue
                results = data.get("results", [])
                for r in results:
                    r["_source_engine"] = src
                all_papers.extend(results)
            except Exception as e:
                errors.append(f"{src}: {str(e)[:100]}")

    papers = deduplicate(all_papers)
    papers = rank_papers(papers)

    return {
        "query": query,
        "total_found": len(papers),
        "returned": min(len(papers), max_per_source),
        "errors": errors,
        "results": papers[:max_per_source],
    }


def main():
    p = argparse.ArgumentParser(description="Unified academic paper search")
    p.add_argument("query", help="Search query")
    p.add_argument("-n", "--max-results", type=int, default=10)
    p.add_argument("-s", "--sources", default="all",
                   choices=["all", "arxiv", "s2", "web"])
    p.add_argument("--year-from", type=int, default=None)
    p.add_argument("--year-to", type=int, default=None)
    args = p.parse_args()

    result = search(args.query, args.sources, args.max_results,
                    args.year_from, args.year_to)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
