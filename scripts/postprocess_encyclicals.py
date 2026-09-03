#!/usr/bin/env python3
"""
Clean already-scraped encyclical JSON without re-fetching Vatican pages.

- Drops remaining headings, greetings, and citation junk
- Parses paragraph numbers like "2 ." (space before the period)
- Dedupes by title + date
- Writes a small index for GitHub browsing
- Rebuilds the combined encyclicals file from unique documents
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone

from scrape_papal_encyclicals_vatican import (
    _is_heading_or_junk,
    _parse_paragraph_number,
    _slugify,
)


def _clean_encyclical(enc: dict) -> dict:
    cleaned = []
    for para in enc.get("paragraphs") or []:
        if isinstance(para, dict):
            text = (para.get("text") or "").strip()
            num = para.get("paragraph")
        else:
            text = str(para).strip()
            num = None
        if not text or len(text) < 10:
            continue
        if num is None:
            num, text = _parse_paragraph_number(text)
        if _is_heading_or_junk(text):
            continue
        cleaned.append({"paragraph": num, "text": text})

    title = enc.get("title")
    date = enc.get("publicationDate")
    pope_slug = (enc.get("popeSectionSlug") or "").replace("_", "-") or None
    slug = enc.get("slug") or _slugify(title or "unknown")
    enc = {**enc}
    enc["popeSectionSlug"] = pope_slug
    enc["slug"] = slug
    enc["id"] = enc.get("id") or "-".join(p for p in [pope_slug, date, slug] if p)
    enc["language"] = enc.get("language") or "en"
    enc["paragraphs"] = cleaned
    enc["paragraphCount"] = len(cleaned)
    return enc


def _dedupe(items: list[dict]) -> list[dict]:
    best: dict[tuple, dict] = {}
    for enc in items:
        key = (
            (enc.get("title") or "").lower(),
            enc.get("publicationDate"),
        )
        prev = best.get(key)
        if prev is None:
            best[key] = enc
            continue
        # Prefer more paragraphs, then modern /content/ URLs.
        prev_score = (
            len(prev.get("paragraphs") or []),
            1 if "/content/" in (prev.get("vaticanUrl") or "") else 0,
        )
        new_score = (
            len(enc.get("paragraphs") or []),
            1 if "/content/" in (enc.get("vaticanUrl") or "") else 0,
        )
        if new_score > prev_score:
            best[key] = enc
    return sorted(
        best.values(),
        key=lambda e: (e.get("publicationDate") or "", e.get("title") or ""),
    )


def _index_entry(enc: dict, filename: str) -> dict:
    return {
        "id": enc.get("id"),
        "slug": enc.get("slug"),
        "title": enc.get("title"),
        "pope": enc.get("pope"),
        "publicationDate": enc.get("publicationDate"),
        "language": enc.get("language"),
        "paragraphCount": enc.get("paragraphCount"),
        "file": filename,
        "vaticanUrl": enc.get("vaticanUrl"),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--lang",
        default="en",
        help="Language folder to clean (default: en). Example: it, es, fr, la.",
    )
    parser.add_argument("--dir", default=None, help="Per-encyclical JSON directory")
    parser.add_argument("--combined", default=None)
    parser.add_argument("--index", default=None)
    args = parser.parse_args(argv)

    lang = args.lang.lower()
    enc_dir = args.dir or os.path.join("data", "encyclicals", lang)
    index_path = args.index or (
        os.path.join("data", "encyclicals", "index.json")
        if lang == "en"
        else os.path.join("data", "encyclicals", f"index-{lang}.json")
    )
    combined_path = args.combined or (
        "data/papal_encyclicals.json"
        if lang == "en"
        else f"data/papal_encyclicals-{lang}.json"
    )

    paths = sorted(glob.glob(os.path.join(enc_dir, "*.json")))
    if not paths:
        raise SystemExit(f"No encyclical JSON files in {enc_dir}")

    items = [_clean_encyclical(json.load(open(p, encoding="utf-8"))) for p in paths]
    unique = _dedupe(items)

    os.makedirs(enc_dir, exist_ok=True)
    written = []
    for enc in unique:
        slug = enc["slug"]
        path = os.path.join(enc_dir, f"{slug}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(enc, f, ensure_ascii=False, indent=2)
            f.write("\n")
        written.append((enc, f"{lang}/{slug}.json"))

    index = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "language": lang,
        "count": len(written),
        "items": [_index_entry(enc, rel) for enc, rel in written],
    }
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
        f.write("\n")

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "language": lang,
        "sources": {"vatican": "https://www.vatican.va/offices/papal_docs_list.html"},
        "count": len(unique),
        "items": unique,
    }
    os.makedirs(os.path.dirname(combined_path) or ".", exist_ok=True)
    with open(combined_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    print(f"Cleaned {len(unique)} unique encyclicals ({lang})", file=sys.stderr)
    print(f"Index: {index_path}", file=sys.stderr)
    print(f"Combined: {combined_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    raise SystemExit(main(sys.argv[1:]))
