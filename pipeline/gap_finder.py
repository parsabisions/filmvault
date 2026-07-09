#!/usr/bin/env python3
"""
FilmVault Gap Finder
Discovers films that exist on sources but aren't in our catalog yet.
Methods:
1. Paginate ALL talafillm.sbs posts (pages we haven't scraped)
2. Probe tinyzmoviez.ir CDN for new year/title combos
3. Cross-check against catalog to find gaps
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
MAX_CDN_PROBES = 500  # Max CDN directory probes per run


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
        except Exception as e:
            time.sleep(1)
    return None, {}


def dir_exists(url):
    """Check if a CDN directory exists."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "FilmVault/2.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status < 400
    except urllib.error.HTTPError as e:
        return e.code < 500  # 403 still means it exists
    except:
        return False


def scan_cdn_for_year(year, known_titles, catalog_keys):
    """Probe tinyzmoviez.ir for movies in a given year."""
    new_films = []
    # Generate probe URLs from known titles — we can't enumerate all titles,
    # but we can check if titles from other years exist in this year too
    # Also probe common patterns

    base_urls = [
        f"https://dl5.tinyzmoviez.ir/files_3/Pakhsh.Online.Film/{year}/",
        f"https://dl5.tinyzmoviez.ir/files_3/New.Film/{year}/",
    ]

    # Check if the year directory itself exists
    for base in base_urls:
        if not dir_exists(base):
            continue

        # We can't enumerate without wordlists, but we CAN check
        # titles we know from other sources (simbaios, berlin, etc.)
        for title_slug in known_titles[:MAX_CDN_PROBES]:
            probe = base + title_slug + "/"
            if dir_exists(probe):
                # Found a directory — but we might not have a proper name
                # Just log it for now; the main scraper will pick it up
                pass

    return new_films


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

    # Method 1: Scan ALL pages of talafillm.sbs
    # We can scan pages we haven't covered yet by checking each page
    # The main scraper handles this via incremental ID tracking,
    # but gap_finder can do a broader scan for very old posts
    log("Method 1: Checking talafillm.sbs for older posts...")

    # Check pages from the end (older posts) that the incremental scraper
    # might have missed
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
                if date: year = date[:4]

            key = normalize_title(title) + "|" + year
            if key not in existing_keys:
                # New film found! Extract it
                sys.path.insert(0, os.path.dirname(__file__))
                from scraper import extract_post
                film = extract_post(post)
                if film and film.get("links"):
                    catalog.append(film)
                    existing_keys.add(key)
                    new_count += 1

        time.sleep(0.5)

    # Save updated scan page
    state["gap_scan_page"] = scan_start_page + pages_per_run
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

    if new_count > 0:
        with open(CATALOG_PATH, "w", encoding="utf-8") as f:
            json.dump(catalog, f, ensure_ascii=False, separators=(",", ":"))

    log(f"Found {new_count} new films. Catalog: {len(catalog)} total")


if __name__ == "__main__":
    main()
