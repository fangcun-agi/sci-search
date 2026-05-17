#!/usr/bin/env python3
"""Fetch paper content: Sci-Hub first, then arXiv HTML / PubMed / URL fallback.

Usage:
    python3 paper_fetch.py --arxiv 2401.12345
    python3 paper_fetch.py --pmid 12345678
    python3 paper_fetch.py --url "https://..."
    python3 paper_fetch.py --doi 10.1038/nature12373
    python3 paper_fetch.py --doi 10.1038/nature12373 --text
    python3 paper_fetch.py --doi 10.1038/nature12373 --output-dir /tmp/papers

Storage layout (when --output-dir is set):
    {output-dir}/
        pdfs/            # Raw PDF files
        texts/           # Extracted full text (.txt)
"""

import sys
import json
import argparse
import os
import re
import subprocess

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

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA}

SCI_HUB_MIRRORS = [
    "https://sci-hub.et-fine.com",
    "https://sci-hub.ren",
]

S2_API = "https://api.semanticscholar.org/graph/v1/paper/search"


# ── Sci-Hub fetch ──────────────────────────────────────────────

def curl_get(url, cookies=None, timeout=20):
    cmd = ["curl", "-s", "-L", "--connect-timeout", str(timeout), "-A", UA]
    if cookies:
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        cmd += ["-b", cookie_str]
    cmd.append(url)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        return r.stdout
    except Exception:
        return None


def curl_download(url, output_path, timeout=60):
    cmd = ["curl", "-s", "-L", "-o", output_path, "--connect-timeout", str(timeout), "-A", UA, url]
    try:
        subprocess.run(cmd, capture_output=True, timeout=timeout + 10)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
            with open(output_path, "rb") as f:
                magic = f.read(5)
            return magic.startswith(b"%PDF")
    except Exception:
        pass
    return False


def _scihub_extract_pdf_url(html):
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


def _scihub_not_found(html):
    indicators = [
        "please try searching the corresponding DOI again",
        "How to quickly find the DOI",
    ]
    lower = html.lower()
    return any(ind.lower() in lower for ind in indicators)


def _scihub_extract_title(html):
    m = re.search(r"<title>([^<]+)</title>", html)
    if m:
        title = m.group(1)
        if "|" in title:
            parts = title.split("|")
            if len(parts) >= 2:
                return parts[1].strip()
        return title
    return None


def fetch_scihub(doi, output_path=None):
    """Try to fetch a paper PDF via Sci-Hub. Returns result dict or None."""
    import time as _time

    for mirror in SCI_HUB_MIRRORS:
        cookies = {"scihub_verified": "1"} if "ren" in mirror else None
        html = curl_get(f"{mirror}/{doi}", cookies=cookies)
        if not html:
            continue
        if _scihub_not_found(html):
            continue

        pdf_url = _scihub_extract_pdf_url(html)
        title = _scihub_extract_title(html)

        # Proxy-style mirror: try polling
        if not pdf_url and "ren" in mirror:
            task_m = re.search(r'taskId\s*=\s*"([^"]+)"', html)
            if task_m:
                tid = task_m.group(1)
                api = f"{mirror}/api/check-status?task_id={tid}"
                for _ in range(30):
                    resp = curl_get(api, cookies=cookies, timeout=10)
                    if not resp:
                        break
                    try:
                        d = json.loads(resp)
                    except json.JSONDecodeError:
                        break
                    if d.get("status") == "completed" and d.get("data"):
                        pdf_url = d["data"].get("pdf_url")
                        break
                    elif d.get("status") == "error":
                        break
                    _time.sleep(3)

        if not pdf_url:
            continue

        if not output_path:
            import tempfile
            output_path = os.path.join(tempfile.gettempdir(), f"scihub_{doi.replace('/', '_')}.pdf")

        if curl_download(pdf_url, output_path):
            return {
                "source": "sci-hub",
                "doi": doi,
                "title": title,
                "pdf_url": pdf_url,
                "mirror": mirror,
                "pdf_path": output_path,
                "pdf_size": os.path.getsize(output_path),
            }

    return None


def search_doi_by_title(title):
    try:
        resp = requests.get(
            S2_API,
            params={"query": title, "limit": 3, "fields": "title,externalIds"},
            timeout=15, headers=HEADERS,
        )
        if resp.status_code != 200:
            return None
        for p in resp.json().get("data", []):
            doi = p.get("externalIds", {}).get("DOI")
            if doi:
                return doi
    except Exception:
        pass
    return None


def resolve_doi(arxiv_id=None, pmid=None, url=None, doi=None):
    """Try to resolve a DOI from any identifier."""
    if doi:
        return doi

    # arXiv → DOI via S2
    if arxiv_id:
        query = f"ArXiv:{arxiv_id}"
        try:
            resp = requests.get(
                S2_API,
                params={"query": query, "limit": 1, "fields": "externalIds"},
                timeout=15, headers=HEADERS,
            )
            if resp.status_code == 200:
                for p in resp.json().get("data", []):
                    doi = p.get("externalIds", {}).get("DOI")
                    if doi:
                        return doi
        except Exception:
            pass

    return None


# ── Fallback fetchers ──────────────────────────────────────────

def fetch_arxiv_html(arxiv_id, max_length=30000):
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
    url = f"https://arxiv.org/abs/{arxiv_id}"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    if resp.status_code != 200:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    abstract = soup.find("blockquote", class_="abstract") or soup.find("div", class_="abstract")
    if not abstract:
        return None
    text = abstract.get_text(strip=True)
    text = re.sub(r"^Abstract[:\s]*", "", text, flags=re.IGNORECASE)
    return {"source": "arxiv_abstract", "arxiv_id": arxiv_id, "url": url, "content": text.strip()}


def fetch_pubmed(pmid, max_length=10000):
    url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    if resp.status_code != 200:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    abstract_div = soup.find("div", class_="abstract-content") or soup.find("div", id="abstract")
    if not abstract_div:
        return None
    content = abstract_div.get_text(separator="\n", strip=True)
    if len(content) > max_length:
        content = content[:max_length] + "\n\n[... truncated]"
    return {"source": "pubmed", "pmid": pmid, "url": url, "content": content.strip()}


def fetch_url(url, max_length=30000):
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


# ── PDF text extraction ────────────────────────────────────────

def extract_text(pdf_path, max_chars=50000):
    if not HAS_FITZ:
        return None
    try:
        doc = fitz.open(pdf_path)
        texts = []
        for page in doc:
            texts.append(page.get_text())
        doc.close()
        full = "\n".join(texts)
        return full[:max_chars]
    except Exception:
        return None


# ── Storage helpers ────────────────────────────────────────────

def save_paper_files(result, output_dir, doi=None, arxiv_id=None):
    """Save PDF to pdfs/ and text to texts/ under output_dir."""
    pdf_dir = os.path.join(output_dir, "pdfs")
    text_dir = os.path.join(output_dir, "texts")
    os.makedirs(pdf_dir, exist_ok=True)
    os.makedirs(text_dir, exist_ok=True)

    # Build base name
    if doi:
        base = doi.replace("/", "_")
    elif arxiv_id:
        base = f"arxiv_{arxiv_id}"
    else:
        base = "paper"

    saved = {}

    # Save PDF
    if result.get("pdf_path") and os.path.exists(result["pdf_path"]):
        pdf_dest = os.path.join(pdf_dir, f"{base}.pdf")
        if result["pdf_path"] != pdf_dest:
            import shutil
            shutil.copy2(result["pdf_path"], pdf_dest)
        saved["pdf_file"] = pdf_dest

    # Save text
    content = result.get("full_text") or result.get("content")
    if content:
        text_dest = os.path.join(text_dir, f"{base}.txt")
        with open(text_dest, "w", encoding="utf-8") as f:
            f.write(content)
        saved["text_file"] = text_dest

    return saved


# ── Main ───────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Fetch paper content (Sci-Hub + fallbacks)")
    p.add_argument("--arxiv", help="arXiv ID (e.g., 2401.12345)")
    p.add_argument("--pmid", help="PubMed ID")
    p.add_argument("--url", help="Direct URL to fetch")
    p.add_argument("--doi", help="DOI (e.g., 10.1038/nature12373)")
    p.add_argument("--text", action="store_true", help="Extract full text from PDF")
    p.add_argument("-m", "--max-length", type=int, default=50000, help="Max text chars")
    p.add_argument("--output-dir", "-d", help="Directory to save pdfs/ and texts/ subdirs")
    args = p.parse_args()

    result = None

    # ── Step 1: Try Sci-Hub if we have a DOI or can resolve one ──
    doi = args.doi or resolve_doi(arxiv_id=args.arxiv)
    if doi:
        print(f"Trying Sci-Hub for DOI: {doi}", file=sys.stderr)
        result = fetch_scihub(doi)
        if result:
            print(f"Sci-Hub success: {result.get('title', doi)}", file=sys.stderr)

    # ── Step 2: Fallback to source-specific fetchers ──
    if not result:
        print("Sci-Hub unavailable, trying fallbacks...", file=sys.stderr)
        if args.arxiv:
            result = fetch_arxiv_html(args.arxiv, args.max_length)
            if not result:
                result = fetch_arxiv_abstract(args.arxiv)
        elif args.pmid:
            result = fetch_pubmed(args.pmid, args.max_length)
        elif args.url:
            result = fetch_url(args.url, args.max_length)
        elif doi:
            # Last resort: try DOI as URL
            result = fetch_url(f"https://doi.org/{doi}", args.max_length)

    if not result:
        print(json.dumps({"error": "could not fetch content from any source"}))
        sys.exit(1)

    # ── Step 3: Extract text if PDF was downloaded ──
    if args.text and result.get("pdf_path") and not result.get("content"):
        full_text = extract_text(result["pdf_path"], args.max_length)
        if full_text:
            result["full_text"] = full_text
            result["text_length"] = len(full_text)

    # ── Step 4: Save to output dir if requested ──
    if args.output_dir:
        saved = save_paper_files(result, args.output_dir, doi=doi, arxiv_id=args.arxiv)
        if saved:
            result["saved_files"] = saved

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
