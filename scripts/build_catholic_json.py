#!/usr/bin/env python3
"""
Build a single unified Catholic JSON file from all available datasets.

Output: a JSON object with top-level keys for each corpus:
  {
    "generatedAt": "...",
    "bible": [ ... ],
    "catechism": [ ... ],
    "canonLaw": [ ... ],
    "romanMissal": [ ... ],
    "encyclicals": [ ... ]
  }
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone


def _load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _try_load(path: str, label: str):
    """Load JSON if file exists, else warn and return None."""
    if not os.path.isfile(path):
        print(f"  SKIP {label}: {path} not found", file=sys.stderr)
        return None
    data = _load_json(path)
    count = len(data) if isinstance(data, list) else "dict"
    print(f"  OK   {label}: {path} ({count} items)", file=sys.stderr)
    return data


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Build a unified Catholic JSON from all available datasets."
    )
    parser.add_argument(
        "--nabre-json",
        default="data/bible-nabre-json-dataset/generated_data/nabre.json",
        help="Path to nabre.json",
    )
    parser.add_argument(
        "--catechism-json",
        default="data/catholicism-in-json/catechism.json",
        help="Path to catechism.json",
    )
    parser.add_argument(
        "--canon-json",
        default="data/catholicism-in-json/canon.json",
        help="Path to canon.json",
    )
    parser.add_argument(
        "--girm-json",
        default="data/catholicism-in-json/girm.json",
        help="Path to girm.json",
    )
    parser.add_argument(
        "--encyclicals-json",
        default="data/papal_encyclicals.json",
        help="Path to papal_encyclicals.json",
    )
    parser.add_argument("--out", default="data/catholic_all.json", help="Output JSON file path")
    args = parser.parse_args(argv)

    print("Loading datasets...", file=sys.stderr)

    output: dict = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "bible": "https://github.com/nirmalben/bible-nabre-json-dataset",
            "catechism": "https://github.com/aseemsavio/catholicism-in-json",
            "canonLaw": "https://github.com/aseemsavio/catholicism-in-json",
            "romanMissal": "https://github.com/aseemsavio/catholicism-in-json",
            "encyclicals": "https://www.vatican.va/offices/papal_docs_list.html",
        },
    }

    # Bible
    bible = _try_load(args.nabre_json, "Bible (NABRE)")
    if bible and isinstance(bible, list):
        output["bible"] = bible

    # Catechism
    catechism = _try_load(args.catechism_json, "Catechism (CCC)")
    if catechism and isinstance(catechism, list):
        output["catechism"] = catechism

    # Canon Law
    canon = _try_load(args.canon_json, "Canon Law")
    if canon and isinstance(canon, list):
        output["canonLaw"] = canon

    # GIRM
    girm = _try_load(args.girm_json, "Roman Missal (GIRM)")
    if girm and isinstance(girm, list):
        output["romanMissal"] = girm

    # Encyclicals
    enc_payload = _try_load(args.encyclicals_json, "Papal Encyclicals")
    if enc_payload:
        if isinstance(enc_payload, dict) and "items" in enc_payload:
            output["encyclicals"] = enc_payload["items"]
        elif isinstance(enc_payload, list):
            output["encyclicals"] = enc_payload

    # Summary
    counts = {}
    for key in ["bible", "catechism", "canonLaw", "romanMissal", "encyclicals"]:
        if key in output and isinstance(output[key], list):
            counts[key] = len(output[key])
    output["counts"] = counts

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    print(f"\nSaved to {args.out}", file=sys.stderr)
    for k, v in counts.items():
        print(f"  {k}: {v}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
