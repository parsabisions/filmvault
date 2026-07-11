#!/usr/bin/env python3
"""
FilmVault Gap Finder
Discovers films that exist on talafillm.sbs but aren't in our catalog yet.
"""

import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from html import unescape

WP_API = "https://talafillm.sbs/wp-json/wp/v2/posts"
CATALOG_PATH = os.path.join(os.path.dirname(__file__), "..", "catalog.json")
STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "pipeline_state.json")
LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "pipeline.log")


def log(msg):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] [gap] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def normalize_title(title):
    t = title.lower().strip()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    return re.sub(r"\s+", " ", t)


def clean_title(title):
    t = unescape(title).strip()
    t = re.sub(r"^دانلود\s+(فیلم|انیمیشن|سریال)\s+", "", t)
    t = re.sub(r"\s+بدون\s+سانسور$", "", t)
    t = re.sub(r"\s+با\s+کیفیت\s+\d+p$", "", t)
    t = re.sub(r"_?www\.TalaFilm\.Top$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+\d{4}$", "", t)
    return t.strip()


def wp_get(url, retries=2):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "FilmVault/2.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data, dict(resp.headers)
        except Exception:
            time.sleep(1)
    return None, {}


def save_catalog(catalog):
    tmp = CATALOG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, CATALOG_PATH)


def main():
    if not os.path.exists(CATALOG_PATH):
        log("No catalog found.")
        return

    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    log(f"Catalog: {len(catalog)} films")

    # Build existing keys
    existing_keys = set()
    for film in catalog:
        key = normalize_title(film["title"]) + "|" + str(film.get("year", ""))
        existing_keys.add(key)

    # Load state for high water mark
    state = {}
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)

    # Scan pages from the end (older posts)
    scan_start_page = max(1, state.get("gap_scan_page", 200))
    pages_per_run = 50
    new_count = 0

    for page in range(scan_start_page, scan_start_page + pages_per_run):
        url = f"{WP_API}?per_page=100&page={page}&_fields=id,slug,title,acf,date&orderby=date&order=desc"
        posts, headers = wp_get(url)
        if not posts:
            break

        for post in posts:
            acf = post.get("acf", {})
            title_en = clean_title(str(acf.get("title_english", "") or ""))
            title_fa = clean_title(post.get("title", {}).get("rendered", ""))
            title = title_en if (title_en and len(title_en) >= 2) else title_fa
            year = str(acf.get("release_date", "") or acf.get("po_year", "") or "")
            if not year:
                date = post.get("date", "")
                if date:
                    year = date[:4]

            key = normalize_title(title) + "|" + year
            if key not in existing_keys:
                sys.path.insert(0, os.path.dirname(__file__))
                from scraper import extract_post
                film = extract_post(post)
                if film and film.get("links"):
                    catalog.append(film)
                    existing_keys.add(key)
                    new_count += 1

        time.sleep(0.5)

    # Save state atomically
    state["gap_scan_page"] = scan_start_page + pages_per_run
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_PATH)

    if new_count > 0:
        save_catalog(catalog)

    log(f"Found {new_count} new films. Catalog: {len(catalog)} total")


if __name__ == "__main__":
    main()
