#!/usr/bin/env python3
"""Fetch paper content from arXiv HTML, PubMed, or open access PDF."""

import sys
import json
import argparse
import re

try:
    import requests
except ImportError:
    print(json.dumps({"error": "pip install requests beautifulsoup4 html2text"}))
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print(json.dumps({"error": "pip install requests beautifulsoup4 html2text"}))
    sys.exit(1)

try:
    import html2text
    HAS_H2T = True
except ImportError:
    HAS_H2T = False

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA}


def fetch_arxiv_html(arxiv_id, max_length=30000):
    """Fetch arXiv paper as HTML (full text for recent papers)."""
    url = f"https://arxiv.org/html/{arxiv_id}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code != 200:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in ["script", "style", "nav"]:
        for el in soup.find_all(tag):
            el.decompose()

    main = soup.find("article") or soup.find("div", class_="ltx_page") or soup.find("body")
    if not main:
        return None

    if HAS_H2T:
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        content = h.handle(str(main))
    else:
        content = main.get_text(separator="\n", strip=True)

    if len(content) > max_length:
        content = content[:max_length] + "\n\n[... truncated]"

    return {"source": "arxiv_html", "arxiv_id": arxiv_id, "url": url, "content": content.strip()}


def fetch_arxiv_abstract(arxiv_id):
    """Fetch arXiv abstract page."""
    url = f"https://arxiv.org/abs/{arxiv_id}"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    if resp.status_code != 200:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    abstract = soup.find("blockquote", class_="abstract")
    if not abstract:
        abstract = soup.find("div", class_="abstract")
    if not abstract:
        return None

    text = abstract.get_text(strip=True)
    text = re.sub(r"^Abstract[:\s]*", "", text, flags=re.IGNORECASE)
    return {"source": "arxiv_abstract", "arxiv_id": arxiv_id, "url": url, "content": text.strip()}


def fetch_pubmed(pmid, max_length=10000):
    """Fetch PubMed abstract via NCBI E-utilities."""
    url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    if resp.status_code != 200:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    abstract_div = soup.find("div", class_="abstract-content")
    if not abstract_div:
        abstract_div = soup.find("div", id="abstract")
    if not abstract_div:
        return None

    content = abstract_div.get_text(separator="\n", strip=True)
    if len(content) > max_length:
        content = content[:max_length] + "\n\n[... truncated]"

    return {"source": "pubmed", "pmid": pmid, "url": url, "content": content.strip()}


def fetch_url(url, max_length=30000):
    """Generic URL fetch for open access papers."""
    resp = requests.get(url, headers=HEADERS, timeout=20)
    if resp.status_code != 200:
        return None

    resp.encoding = resp.apparent_encoding or "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in ["script", "style", "nav", "footer", "header"]:
        for el in soup.find_all(tag):
            el.decompose()

    main = None
    for sel in ["article", "[role='main']", "main", ".article-content", "#content"]:
        main = soup.select_one(sel)
        if main:
            break
    if not main:
        main = soup.find("body") or soup

    if HAS_H2T:
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0
        content = h.handle(str(main))
    else:
        content = main.get_text(separator="\n", strip=True)
        content = re.sub(r"\n{3,}", "\n\n", content)

    if len(content) > max_length:
        content = content[:max_length] + "\n\n[... truncated]"

    return {"source": "url", "url": url, "content": content.strip()}


def main():
    p = argparse.ArgumentParser(description="Fetch paper content")
    p.add_argument("--arxiv", help="arXiv ID (e.g., 2401.12345)")
    p.add_argument("--pmid", help="PubMed ID")
    p.add_argument("--url", help="Direct URL to fetch")
    p.add_argument("-m", "--max-length", type=int, default=30000)
    args = p.parse_args()

    result = None
    if args.arxiv:
        result = fetch_arxiv_html(args.arxiv, args.max_length)
        if not result:
            result = fetch_arxiv_abstract(args.arxiv)
    elif args.pmid:
        result = fetch_pubmed(args.pmid, args.max_length)
    elif args.url:
        result = fetch_url(args.url, args.max_length)
    else:
        print(json.dumps({"error": "specify --arxiv, --pmid, or --url"}))
        sys.exit(1)

    if not result:
        print(json.dumps({"error": "could not fetch content"}))
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
