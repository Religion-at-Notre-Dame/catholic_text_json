#!/usr/bin/env python3
"""
Download Catechism, Canon Law, and GIRM JSON release assets from
aseemsavio/catholicism-in-json into data/catholicism-in-json/.

The NABRE Bible is available via the git submodule at:
  data/bible-nabre-json-dataset/generated_data/nabre.json
"""

from __future__ import annotations

import json
import os
import sys

import requests

# Release assets from https://github.com/aseemsavio/catholicism-in-json
RELEASE_TAG = "v2.0.0"
BASE_URL = (
    f"https://github.com/aseemsavio/catholicism-in-json"
    f"/releases/download/{RELEASE_TAG}"
)

DOWNLOADS: dict[str, str] = {
    "data/catholicism-in-json/catechism.json": f"{BASE_URL}/catechism.json",
    "data/catholicism-in-json/canon.json": f"{BASE_URL}/canon.json",
    "data/catholicism-in-json/girm.json": f"{BASE_URL}/girm.json",
}


def main() -> int:
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0"

    for dest, url in DOWNLOADS.items():
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        print(f"Downloading {dest}...", end=" ", flush=True)
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            f.write(resp.content)

        data = json.loads(resp.content)
        count = len(data) if isinstance(data, list) else "N/A"
        print(f"OK ({count} items, {len(resp.content) // 1024}KB)")

    print("\nAll datasets downloaded.")
    print("NABRE Bible is in the submodule: data/bible-nabre-json-dataset/generated_data/nabre.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
