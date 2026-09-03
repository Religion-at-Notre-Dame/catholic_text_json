#!/usr/bin/env python3
"""
Scrape Papal Encyclicals from Vatican.va and output JSON.

The scraper:
1) Downloads an index page that lists Papal Documents (including Encyclical entries).
2) Extracts all encyclical document URLs from the index.
3) Fetches each document page and extracts:
   - title
   - publication date (best-effort)
   - pope section slug (derived from URL)
   - main paragraphs (best-effort)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


DEFAULT_INDEX_URL = "https://www.vatican.va/offices/papal_docs_list.html"

# Vatican index pages sometimes link to broken URLs. These map bad → good.
URL_FIXES: dict[str, str] = {
    "https://www.vatican.va/holy_father/leo_xiii/encyclicals/documents/hf_l-xiii_enc_25071891_pastoralis_en.html":
        "https://www.vatican.va/content/leo-xiii/en/encyclicals/documents/hf_l-xiii_enc_12091891_pastoralis-officii.html",
    "https://www.vatican.va/holy_father/pius_x/encyclicals/documents/hf_p-x_enc_28071906_pieni-l'animo_en.html":
        "https://www.vatican.va/content/pius-x/en/encyclicals/documents/hf_p-x_enc_28071906_pieni-l-animo.html",
    "https://www.vatican.va/holy_father/pius_xi/encyclicals/documents/hf_p-xi_enc_08051928_miserentissimus-redemptor_en.html":
        "https://www.vatican.va/content/pius-xi/en/encyclicals/documents/hf_p-xi_enc_19280508_miserentissimus-redemptor.html",
    "https://www.vatican.va/holy_father/pius_xi/encyclicals/documents/hf_p-xi_enc_19031937_divini-redemptoris_en.html":
        "https://www.vatican.va/content/pius-xi/en/encyclicals/documents/hf_p-xi_enc_19370319_divini-redemptoris.html",
    "https://www.vatican.va/holy_father/pius_xi/encyclicals/documents/hf_p-xi_enc_20121929_mens-nostra_en.html":
        "https://www.vatican.va/content/pius-xi/en/encyclicals/documents/hf_p-xi_enc_19291220_mens-nostra.html",
    "https://www.vatican.va/holy_father/pius_xi/encyclicals/documents/hf_p-xi_enc_31121930_casti-connubii_en.html":
        "https://www.vatican.va/content/pius-xi/en/encyclicals/documents/hf_p-xi_enc_19301231_casti-connubii.html",
}

# Pope-specific encyclical indexes. `{lang}` is a Vatican language code
# such as en, it, es, fr, de, pt, la, pl, ar, zh_cn.
EXTRA_INDEX_TEMPLATES = [
    "https://www.vatican.va/content/francesco/{lang}/encyclicals.index.html",
    "https://www.vatican.va/content/francesco/{lang}/encyclicals.html",
    "https://www.vatican.va/content/john-paul-ii/{lang}/encyclicals.html",
    "https://www.vatican.va/content/benedict-xvi/{lang}/encyclicals.html",
    "https://www.vatican.va/content/paul-vi/{lang}/encyclicals.html",
    "https://www.vatican.va/content/john-xxiii/{lang}/encyclicals.html",
    "https://www.vatican.va/content/pius-xii/{lang}/encyclicals.html",
    "https://www.vatican.va/content/leo-xiii/{lang}/encyclicals.html",
]

# Common Vatican.va language codes (not exhaustive).
KNOWN_LANGS = (
    "en", "it", "es", "fr", "de", "pt", "la", "pl", "ar",
    "zh_cn", "zh_tw", "ru", "uk", "nl", "cs", "hu", "sk", "sl",
)

# Map URL slugs to readable pope names.
POPE_NAMES: dict[str, str] = {
    "francesco": "Francis",
    "john-paul-ii": "John Paul II",
    "john_paul_ii": "John Paul II",
    "benedict-xvi": "Benedict XVI",
    "benedict_xvi": "Benedict XVI",
    "paul-vi": "Paul VI",
    "paul_vi": "Paul VI",
    "p-vi": "Paul VI",
    "john_xxiii": "John XXIII",
    "john-xxiii": "John XXIII",
    "pius_xii": "Pius XII",
    "pius_xi": "Pius XI",
    "pius_x": "Pius X",
    "benedict_xv": "Benedict XV",
    "leo_xiii": "Leo XIII",
    "pius-xii": "Pius XII",
    "pius-xi": "Pius XI",
    "pius-x": "Pius X",
    "benedict-xv": "Benedict XV",
    "leo-xiii": "Leo XIII",
}


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            # A real User-Agent reduces the chance of being blocked.
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        }
    )
    return s


_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    # Italian
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
    # Spanish
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    # French
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
    # German
    "januar": 1, "februar": 2, "märz": 3, "marz": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "dezember": 12,
    # Portuguese
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
    # Latin
    "ianuarii": 1, "februarii": 2, "martii": 3, "aprilis": 4,
    "maii": 5, "iunii": 6, "iulii": 7, "augusti": 8,
    "septembris": 9, "octobris": 10, "novembris": 11, "decembris": 12,
}


def _iso_date_fuzzy(value: str | None) -> str | None:
    if not value:
        return None
    # Already ISO?
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", value)
    if m:
        return m.group(1)
    # "3 October 2020" or "October 3, 2020"
    m = re.search(r"(\d{1,2})\s+(\w+)\s+(\d{4})", value)
    if m:
        day, mon, year = int(m.group(1)), m.group(2).lower(), m.group(3)
        if mon in _MONTHS:
            return f"{year}-{_MONTHS[mon]:02d}-{day:02d}"
    m = re.search(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", value)
    if m:
        mon, day, year = m.group(1).lower(), int(m.group(2)), m.group(3)
        if mon in _MONTHS:
            return f"{year}-{_MONTHS[mon]:02d}-{day:02d}"
    return value.strip()


def _pope_from_url(url: str) -> tuple[str | None, str | None]:
    """
    Returns (popeSectionSlug, language).

    Handles both URL patterns:
      /content/francesco/en/encyclicals/documents/...
      /holy_father/pius_xii/encyclicals/documents/..._en.html
    """
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")

    if len(parts) >= 3 and parts[0] == "content":
        return parts[1], parts[2]

    if len(parts) >= 2 and parts[0] == "holy_father":
        pope_slug = parts[1]
        # Language is encoded in the filename suffix, e.g. _en.html or _zh_cn.html
        m = re.search(r"_([a-z]{2}(?:_[a-z]{2})?)\.html?$", parsed.path)
        lang = m.group(1) if m else None
        return pope_slug, lang

    return None, None


def _extra_index_urls(lang: str | None) -> list[str]:
    code = lang or "en"
    return [tpl.format(lang=code) for tpl in EXTRA_INDEX_TEMPLATES]


def _rewrite_url_language(url: str, lang: str) -> str:
    """Rewrite an encyclical URL from English (or another lang) to `lang`."""
    if not lang:
        return url
    # /content/<pope>/en/...  -> /content/<pope>/<lang>/...
    url = re.sub(r"(/content/[^/]+/)[a-z]{2}(?:_[a-z]{2})?(/)", rf"\1{lang}\2", url)
    # ..._en.html -> ..._it.html  (also zh_cn)
    url = re.sub(r"_([a-z]{2}(?:_[a-z]{2})?)\.html$", f"_{lang}.html", url)
    return url


def discover_encyclical_urls(
    index_url: str, *, preferred_lang: str | None = "en", session: requests.Session | None = None
) -> list[str]:
    session = session or _session()
    resp = session.get(index_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    urls: set[str] = set()
    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        # Vatican encyclical document pages live under paths like:
        #   /holy_father/<pope>/encyclicals/documents/<file>.html
        #   /content/<pope>/<lang>/encyclicals/documents/<file>.html
        if "/encyclicals/documents/" not in href:
            continue
        abs_url = urljoin(index_url, href)
        if preferred_lang:
            # Keep links already in the requested language, and rewrite
            # English (or other) index links into that language.
            if f"/{preferred_lang}/" in abs_url or f"_{preferred_lang}." in abs_url:
                urls.add(abs_url)
            else:
                urls.add(_rewrite_url_language(abs_url, preferred_lang))
        else:
            urls.add(abs_url)

    return sorted(urls)


def _url_fingerprint(url: str) -> str:
    """Collapse /content/ vs /holy_father/ and language suffixes into one key."""
    path = urlparse(url).path.lower()
    path = path.replace("/holy_father/", "/content/")
    path = re.sub(r"_[a-z]{2}(?:_[a-z]{2})?\.html$", ".html", path)
    path = re.sub(r"/[a-z]{2}(?:_[a-z]{2})?/", "/", path)
    path = path.replace("_", "-")
    return path


def _dedupe_urls(urls: set[str]) -> list[str]:
    """Prefer modern /content/ URLs when the same document is listed twice."""
    best: dict[str, str] = {}
    for url in urls:
        key = _url_fingerprint(url)
        prev = best.get(key)
        if prev is None:
            best[key] = url
            continue
        prefer_new = ("/content/" in url and "/holy_father/" in prev) or (
            "/content/" in url and "/content/" in prev and len(url) < len(prev)
        )
        if prefer_new:
            best[key] = url
    return sorted(best.values())


def _extract_title_and_date(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    """
    Extract the encyclical title and publication date.
    The <title> tag is the most reliable source — it usually looks like:
      "Fratelli tutti (3 October 2020)" or "Ad Beatissimi Apostolorum (November 1, 1914)"
    """
    raw_title = None
    pub_date = None

    title_tag = soup.find("title")
    if title_tag:
        full = title_tag.get_text(" ", strip=True)
        # Normalize whitespace (some pages have \r or multiple spaces).
        full = re.sub(r"\s+", " ", full).strip()
        # Try to split "Name (date_string)"
        m = re.match(r"^(.+?)\s*\(([^)]+\d{4})\)\s*$", full)
        if m:
            raw_title = m.group(1).strip()
            pub_date = _iso_date_fuzzy(m.group(2))
        else:
            raw_title = full

    # If <title> didn't give us a clean title, try <h1>.
    if not raw_title or len(raw_title) < 3:
        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            raw_title = re.sub(r"\s+", " ", h1.get_text(" ", strip=True)).strip()

    # If date still missing, try meta tags.
    if not pub_date:
        for attr, key in [
            ("property", "article:published_time"),
            ("name", "dc.date"),
            ("name", "date"),
            ("itemprop", "datePublished"),
        ]:
            meta = soup.find("meta", attrs={attr: key})
            if meta and meta.get("content"):
                pub_date = _iso_date_fuzzy(meta.get("content"))
                if pub_date:
                    break

    return raw_title, pub_date


def _parse_paragraph_number(text: str) -> tuple[int | None, str]:
    """
    Strip a leading paragraph number like "42. The text..." or "2 . The text..."
    and return (number, cleaned_text).  Returns (None, original) if no number found.
    """
    m = re.match(r"^(\d{1,4})\s*\.\s+", text)
    if m:
        return int(m.group(1)), text[m.end():]
    return None, text


def _is_heading_or_junk(text: str) -> bool:
    """Return True if this looks like a section heading, pope signature, footnote, or boilerplate."""
    # Copyright / boilerplate (any length).
    if re.search(r"(©|Copyright)\s", text, flags=re.I):
        return True

    # Footnotes: "[123] ..." or "[ 1] ..." or "(81) ..." or "(cf. ...)" at start
    if re.match(r"^\[?\s*\d+\s*[)\]]\s", text):
        return True
    if re.match(r"^\(\d+\)\s", text):
        return True

    # Condensed footnote blocks: "1 . Jn. 1:14. 2 . Jn. 3:16. 3 . ..." or "1. Cf. ..."
    if re.match(r"^\d+\s*\.\s", text) and text.count(". ") > 5 and re.search(r"\d+\s*\.\s.*\d+\s*\.", text[:100]):
        return True

    # The big "ENCYCLICAL LETTER/OF POPE ..." header paragraph (any language).
    if re.match(
        r"^(ENCYCLICAL\s+(LETTER\s+|OF\s+)|LETTERA\s+ENCICLICA|CARTA\s+ENC[IÍ]CLICA|"
        r"LETTRE\s+ENCYCLIQUE|ENZYKLIKA|LITTERAE\s+ENCYCLICAE|CARTA\s+ENC[IÍ]CLICA)",
        text,
        flags=re.I,
    ):
        return True

    # Address / greeting boilerplate.
    if re.match(
        r"^(To (His |Our )?(Venerable|Beloved)|Venerable (Brothers|Brethren)|"
        r"Health and (the )?Apostolic|My Venerable)",
        text,
        flags=re.I,
    ):
        return True

    # Pope name header lines like "JOHN PAUL II HOLY FATHER ..."
    if re.match(r"^(JOHN PAUL II|IOANNES PAULUS|BENEDICT|PIUS|LEO|PAUL VI)\s", text, flags=re.I):
        return True

    # "Given at/in Rome/Castel Gandolfo" closing paragraph.
    if re.match(r"^Given (at|in) (Rome|St\.?\s*Peter|Castel|the Vatican)", text, flags=re.I):
        return True

    # Date-only lines like "SEPTEMBER 15, 1966".
    if re.fullmatch(r"[A-Z]+\s+\d{1,2},?\s+\d{4}", text.strip()):
        return True

    # Separator lines (underscores, dashes, asterisks).
    if re.fullmatch(r"[_\-*=\s]{3,}", text.strip()):
        return True

    # Short inline scripture/footnote references (under 80 chars).
    # e.g. "Rom. 13:1.", "Hebrews, XIII, 14.", "S. Aug. serm. clxxix., I."
    if len(text) < 80:
        # Scripture references: contain chapter:verse or Roman-numeral citations
        if re.search(r"\d+[.:]\d+", text) and not re.search(r"[a-z]{15,}", text):
            return True
        # Roman numeral citations: "Hebrews, XIII, 14" or "II Tim., IV, 2-5"
        if re.search(r"[IVXLC]{2,}\s*,\s*\d", text):
            return True
        # Abbreviated references and source citations
        if re.match(
            r"^(Cf\.|Id\.|Ibid|See |Op\.|Sess\.|Conc\.|Opusc|Encyclical|"
            r"L'Osservatore|S\.\s|Ep\.\s|Vita\s|Antiph|Constitution,|"
            r"Roman (Missal|Pontifical)|Brev\.|Baronius|Acta Apostolicae|"
            r"AAS |Canon |St\. |Saint )",
            text,
        ):
            return True
        # Generic short reference: mostly punctuation/numbers, few real words
        alpha_chars = sum(1 for c in text if c.isalpha())
        if alpha_chars < len(text) * 0.5 and len(text) < 50:
            return True
        # Date-only lines like "December 20, 1905."
        if re.fullmatch(r"[A-Z][a-z]+\s+\d{1,2},?\s+\d{4}\.?", text.strip()):
            return True

    # Short lines — likely headings, sub-headings, labels, signatures.
    if len(text) < 80:
        # All caps → heading (e.g. "CHAPTER ONE", "INTRODUCTION").
        if text.upper() == text and re.search(r"[A-Z]", text):
            return True
        # Roman numeral section headers like "III. THE OLD TESTAMENT".
        if re.match(r"^[IVXLC]+\.\s", text):
            return True
        # Short title-case lines → sub-heading.
        # e.g. "An illusory light?", "Mary, Star of Hope", "Worker Solidarity"
        if text[0].isupper() and not re.search(r"\.\s", text):
            word_count = len(text.split())
            if word_count <= 10:
                return True
    return False


def _extract_paragraphs(soup: BeautifulSoup) -> list[dict]:
    """
    Returns a list of dicts: {"paragraph": <int|null>, "text": "..."}
    Only keeps real body paragraphs (filters out headings, labels, signatures).
    """
    root = soup.find("main") or soup.find("article") or soup

    raw: list[str] = []
    for p in root.find_all("p"):
        text = p.get_text(" ", strip=True)
        if not text:
            continue
        if len(text) < 10:
            continue
        if _is_heading_or_junk(text):
            continue
        raw.append(text)

    # De-duplicate consecutive identical paragraphs.
    deduped: list[str] = []
    for para in raw:
        if deduped and deduped[-1] == para:
            continue
        deduped.append(para)

    results: list[dict] = []
    for para in deduped:
        num, cleaned = _parse_paragraph_number(para)
        results.append({"paragraph": num, "text": cleaned})
    return results


def scrape_encyclical(url: str, *, session: requests.Session | None = None) -> dict:
    session = session or _session()
    resp = session.get(url, timeout=60)
    resp.raise_for_status()
    # Use resp.content (bytes) so BeautifulSoup can detect UTF-8 properly
    # instead of resp.text which often defaults to ISO-8859-1.
    soup = BeautifulSoup(resp.content, "html.parser")

    title, publication_date = _extract_title_and_date(soup)
    pope_slug, language = _pope_from_url(url)
    paragraphs = _extract_paragraphs(soup)

    pope_slug_norm = pope_slug.replace("_", "-") if pope_slug else None
    pope_name = (
        POPE_NAMES.get(pope_slug)
        or POPE_NAMES.get(pope_slug_norm or "")
        or (pope_slug.replace("_", " ").replace("-", " ").title() if pope_slug else None)
    )
    slug = _slugify(title or "unknown")

    return {
        "id": "-".join(p for p in [pope_slug_norm, publication_date, slug] if p),
        "type": "papalEncyclical",
        "slug": slug,
        "popeSectionSlug": pope_slug_norm,
        "pope": pope_name,
        "title": title,
        "publicationDate": publication_date,
        "vaticanUrl": url,
        "language": language,
        "paragraphCount": len(paragraphs),
        "paragraphs": paragraphs,
    }


def _slugify(text: str) -> str:
    """Turn a title into a filesystem-safe slug."""
    s = text.lower()
    s = re.sub(r"[''ʼ]", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:120] or "unknown"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--index-url",
        default=DEFAULT_INDEX_URL,
        help=f"Vatican index page to discover encyclical links (default: {DEFAULT_INDEX_URL})",
    )
    parser.add_argument(
        "--lang",
        "--preferred-lang",
        dest="lang",
        default="en",
        help=(
            "Language to scrape (default: en). Vatican codes include: "
            + ", ".join(KNOWN_LANGS)
            + ". Use 'none' to keep whatever language the indexes list."
        ),
    )
    parser.add_argument("--out", required=True, help="Output combined JSON file path")
    parser.add_argument("--out-dir", default=None, help="Directory for individual per-encyclical JSON files")
    parser.add_argument("--limit", type=int, default=0, help="Optional max number of encyclicals to scrape (0 = no limit)")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds to wait between requests (be polite)")
    args = parser.parse_args(argv)

    preferred_lang = None if args.lang.lower() == "none" else args.lang.lower()

    session = _session()

    # Discover from the main index plus extra pope-specific pages.
    all_index_urls = [args.index_url] + _extra_index_urls(preferred_lang)
    url_set: set[str] = set()
    for idx_url in all_index_urls:
        try:
            found = discover_encyclical_urls(idx_url, preferred_lang=preferred_lang, session=session)
            url_set.update(found)
            print(f"Discovered {len(found)} links from {idx_url}", file=sys.stderr)
        except Exception as e:
            print(f"WARN: could not fetch index {idx_url}: {e}", file=sys.stderr)
    # Apply URL fixes for known broken English links, then rewrite to the
    # requested language if needed.
    fixed: set[str] = set()
    for u in url_set:
        u = URL_FIXES.get(u, u)
        if preferred_lang:
            u = _rewrite_url_language(u, preferred_lang)
        fixed.add(u)
    urls = _dedupe_urls(fixed)

    if args.limit and args.limit > 0:
        urls = urls[: args.limit]

    if not urls:
        raise SystemExit(
            "No encyclical URLs discovered from the index page. "
            "Try changing --preferred-lang, or update discovery logic."
        )

    # Create per-encyclical output directory if requested.
    # Files go into <out_dir>/<language>/<slug>.json
    out_dir = args.out_dir

    results: list[dict] = []
    for i, url in enumerate(urls, start=1):
        print(f"[{i}/{len(urls)}] Scraping: {url}", file=sys.stderr)
        try:
            enc = scrape_encyclical(url, session=session)
            results.append(enc)

            # Write individual JSON file into a language subfolder.
            if out_dir:
                lang = enc.get("language") or preferred_lang or "unknown"
                lang_dir = os.path.join(out_dir, lang)
                os.makedirs(lang_dir, exist_ok=True)
                slug = _slugify(enc.get("title") or "unknown")
                individual_path = os.path.join(lang_dir, f"{slug}.json")
                with open(individual_path, "w", encoding="utf-8") as f:
                    json.dump(enc, f, ensure_ascii=False, indent=2)
                print(f"  -> {individual_path}", file=sys.stderr)

        except Exception as e:
            print(f"  WARN: failed to scrape {url}: {e}", file=sys.stderr)

        if args.delay > 0 and i < len(urls):
            time.sleep(args.delay)

    # Write combined JSON.
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sources": {"vatican": args.index_url},
        "count": len(results),
        "items": results,
    }

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    print(f"Saved {len(results)} encyclicals to {args.out}", file=sys.stderr)
    if out_dir:
        print(f"Individual files in {out_dir}/", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

