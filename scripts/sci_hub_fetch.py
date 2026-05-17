#!/usr/bin/env python3
"""Fetch paper full text via Sci-Hub.

Uses curl subprocess to bypass Cloudflare TLS fingerprint detection.

Usage:
    python3 sci_hub_fetch.py --doi 10.1038/nature12373
    python3 sci_hub_fetch.py --doi 10.1038/nature12373 --text
    python3 sci_hub_fetch.py --title "Attention Is All You Need"
    python3 sci_hub_fetch.py --doi 10.1038/nature12373 --output /tmp/paper.pdf
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    import requests
except ImportError:
    sys.exit("Error: requests not installed. Run: pip install requests")

MIRRORS = [
    "https://sci-hub.et-fine.com",
    "https://sci-hub.ren",
]

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

S2_API = "https://api.semanticscholar.org/graph/v1/paper/search"


def search_doi_by_title(title):
    """Search Semantic Scholar for a paper title and return its DOI."""
    try:
        resp = requests.get(
            S2_API,
            params={"query": title, "limit": 3, "fields": "title,externalIds"},
            timeout=15,
            headers={"User-Agent": UA},
        )
        if resp.status_code != 200:
            return None
        data = resp.json().get("data", [])
        if not data:
            return None
        for paper in data:
            eids = paper.get("externalIds", {})
            doi = eids.get("DOI")
            if doi:
                return doi
    except Exception:
        pass
    return None


def curl_get(url, cookies=None, timeout=20):
    """HTTP GET via curl subprocess to bypass Cloudflare."""
    cmd = [
        "curl", "-s", "-L",
        "--connect-timeout", str(timeout),
        "-A", UA,
    ]
    if cookies:
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        cmd += ["-b", cookie_str]
    cmd.append(url)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        return result.stdout
    except Exception:
        return None


def curl_download(url, output_path, timeout=60):
    """Download file via curl subprocess."""
    cmd = [
        "curl", "-s", "-L", "-o", output_path,
        "--connect-timeout", str(timeout),
        "-A", UA,
        url,
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=timeout + 10)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
            with open(output_path, "rb") as f:
                magic = f.read(5)
            return magic.startswith(b"%PDF")
    except Exception:
        pass
    return False


def fetch_scihub_page(doi, mirror):
    """Fetch the Sci-Hub page for a DOI and return the HTML."""
    url = f"{mirror}/{doi}"
    cookies = None
    if "ren" in mirror:
        cookies = {"scihub_verified": "1"}
    return curl_get(url, cookies=cookies)


def extract_pdf_url(html):
    """Extract the PDF URL from a Sci-Hub page."""
    patterns = [
        r'<embed[^>]+src\s*=\s*"(https?://[^"]*\.pdf[^"]*)"',
        r'<iframe[^>]+src\s*=\s*"(https?://[^"]*\.pdf[^"]*)"',
        r'href\s*=\s*"(https?://[^"]*\.pdf[^"]*)"',
        r'(https?://[^\s"\'<>)]+\.pdf[^\s"\'<>)]*)',
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return None


def check_paper_not_found(html):
    """Check if the page indicates the paper is not found."""
    indicators = [
        "please try searching the corresponding DOI again",
        "How to quickly find the DOI",
    ]
    lower = html.lower()
    return any(ind.lower() in lower for ind in indicators)


def extract_title(html):
    """Extract paper title from the page title."""
    m = re.search(r"<title>([^<]+)</title>", html)
    if m:
        title = m.group(1)
        if "|" in title:
            parts = title.split("|")
            if len(parts) >= 2:
                return parts[1].strip()
        return title
    return None


def extract_text_from_pdf(pdf_path):
    """Extract text from PDF using PyMuPDF."""
    if fitz is None:
        return None
    try:
        doc = fitz.open(pdf_path)
        texts = []
        for page in doc:
            texts.append(page.get_text())
        doc.close()
        return "\n".join(texts)
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="Fetch paper via Sci-Hub")
    parser.add_argument("--doi", help="Paper DOI (e.g. 10.1038/nature12373)")
    parser.add_argument("--title", help="Paper title (will search for DOI)")
    parser.add_argument("--output", "-o", help="Save PDF to this path")
    parser.add_argument("--text", action="store_true", help="Also extract full text")
    parser.add_argument("--max-chars", type=int, default=50000, help="Max text chars to output")
    args = parser.parse_args()

    if not args.doi and not args.title:
        parser.error("Provide --doi or --title")

    # Resolve DOI from title
    doi = args.doi
    if not doi and args.title:
        print(f"Searching DOI for: {args.title}", file=sys.stderr)
        doi = search_doi_by_title(args.title)
        if not doi:
            print(json.dumps({"error": "Could not find DOI for the given title"}))
            sys.exit(1)
        print(f"Found DOI: {doi}", file=sys.stderr)

    # Try mirrors
    pdf_url = None
    page_title = None
    used_mirror = None

    for mirror in MIRRORS:
        print(f"Trying {mirror}...", file=sys.stderr)
        html = fetch_scihub_page(doi, mirror)
        if not html:
            print(f"  No response from {mirror}", file=sys.stderr)
            continue

        if check_paper_not_found(html):
            print(f"  Paper not found on {mirror}", file=sys.stderr)
            continue

        pdf_url = extract_pdf_url(html)
        page_title = extract_title(html)
        used_mirror = mirror

        if pdf_url:
            break

        # For proxy-style mirrors, try polling API
        if "ren" in mirror:
            task_id_m = re.search(r'taskId\s*=\s*"([^"]+)"', html)
            if task_id_m:
                task_id = task_id_m.group(1)
                print(f"  Polling task {task_id}...", file=sys.stderr)
                api_url = f"{mirror}/api/check-status?task_id={task_id}"
                for _ in range(30):
                    resp_text = curl_get(api_url, cookies={"scihub_verified": "1"}, timeout=10)
                    if not resp_text:
                        break
                    try:
                        d = json.loads(resp_text)
                    except json.JSONDecodeError:
                        break
                    if d.get("status") == "completed" and d.get("data"):
                        pdf_url = d["data"].get("pdf_url")
                        break
                    elif d.get("status") == "error":
                        break
                    time.sleep(3)

        if pdf_url:
            break

    if not pdf_url:
        print(json.dumps({
            "error": "Paper not available on Sci-Hub",
            "doi": doi,
            "hint": "Paper may be too new or not indexed. Try open access sources.",
        }))
        sys.exit(1)

    # Download PDF
    output_path = args.output or os.path.join(tempfile.gettempdir(), f"scihub_{doi.replace('/', '_')}.pdf")
    print(f"Downloading PDF from {pdf_url}...", file=sys.stderr)

    if not curl_download(pdf_url, output_path):
        print(json.dumps({"error": "PDF download failed", "pdf_url": pdf_url}))
        sys.exit(1)

    result = {
        "doi": doi,
        "title": page_title,
        "pdf_url": pdf_url,
        "mirror": used_mirror,
        "pdf_path": output_path,
        "pdf_size": os.path.getsize(output_path),
    }

    # Extract text if requested
    if args.text:
        print("Extracting text...", file=sys.stderr)
        text = extract_text_from_pdf(output_path)
        if text:
            result["full_text"] = text[: args.max_chars]
            result["text_length"] = len(text)
            result["text_truncated"] = len(text) > args.max_chars
        else:
            result["full_text"] = None
            result["text_error"] = "Could not extract text (PyMuPDF not installed or PDF is scanned)"

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
