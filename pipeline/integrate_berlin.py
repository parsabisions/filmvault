#!/usr/bin/env python3
"""
FilmVault — Integrate berlin_archive.json into catalog.
Parses filenames to extract titles, years, quality.
"""
import json
import os
import re
import sys
import io
from datetime import datetime
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
CATALOG_PATH = os.path.join(BASE_DIR, "catalog.json")
BERLIN_PATH = os.path.join(BASE_DIR, "..", "other download links", "berlin_archive.json")
LOG_PATH = os.path.join(BASE_DIR, "pipeline.log")
STATE_PATH = os.path.join(BASE_DIR, "pipeline_state.json")


def log(msg):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] [berlin] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def normalize(title):
    t = title.lower().strip()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    return re.sub(r"\s+", " ", t)


def parse_filename(filename):
    """Parse a movie filename like 'Movie.Title.2024.1080p.BluRay.x264-GROUP.mkv'."""
    name = filename
    # Remove extension
    name = re.sub(r"\.(mkv|mp4|avi|mov|wmv)$", "", name, flags=re.IGNORECASE)
    # Try to find year
    year_match = re.search(r"\.(19\d{2}|20\d{2})\.", name)
    year = year_match.group(1) if year_match else ""
    # Extract title: everything before the year
    if year_match:
        title_part = name[:year_match.start()]
    else:
        title_part = name
    # Clean title: replace dots/dashes with spaces, strip quality/group info
    title = title_part.replace(".", " ").replace("_", " ").replace("-", " ")
    # Remove trailing quality/group markers
    title = re.sub(r"\s+(720p|1080p|2160p|480p|540p|BluRay|BRRip|DVDRip|WEB-DL|WEBRip|HDRip|HDTS).*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+(x264|x265|HEVC|AAC|DTS|FLAC|AC3|REMUX).*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*-\s*\w+$", "", title)  # Remove group tag
    title = title.strip()
    return title, year


def main():
    log("=" * 60)
    log("Berlin Archive Integration — Starting")
    log("=" * 60)

    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    log(f"Catalog: {len(catalog)} films")

    if not os.path.exists(BERLIN_PATH):
        log(f"File not found: {BERLIN_PATH}")
        return

    with open(BERLIN_PATH, "r", encoding="utf-8") as f:
        berlin = json.load(f)

    # Parse all filenames
    parsed = []
    for year_key, entries in berlin.items():
        if not isinstance(entries, dict):
            continue
        for imdb_id, files in entries.items():
            if not isinstance(files, list):
                continue
            for f_info in files:
                if not isinstance(f_info, dict) or not f_info.get("name"):
                    continue
                title, year = parse_filename(f_info["name"])
                if title and len(title) > 1:
                    parsed.append({"title": title, "year": year or year_key, "filename": f_info["name"]})

    log(f"Parsed {len(parsed)} filenames")

    # Group by title+year
    grouped = defaultdict(list)
    for p in parsed:
        key = normalize(p["title"]) + "|" + p["year"]
        grouped[key].append(p)

    # Build catalog index
    cat_norm_map = {}
    for i, film in enumerate(catalog):
        key = normalize(film["title"])
        if key not in cat_norm_map:
            cat_norm_map[key] = i

    matched = 0
    new_entries = 0

    for key, files in grouped.items():
        title = files[0]["title"]
        year = files[0]["year"]

        # We don't have actual URLs for berlin archive, just filenames
        # Create entry with metadata only (no download links)
        norm = normalize(title)
        if norm in cat_norm_map:
            matched += 1
            continue

        entry = {
            "title": title,
            "year": year,
            "poster": "",
            "rating": "",
            "available": False,
            "links": [],
            "genre": "",
            "source": "berlin",
        }
        catalog.append(entry)
        cat_norm_map[norm] = len(catalog) - 1
        new_entries += 1

    log(f"Matched: {matched}, New: {new_entries}")
    log(f"Catalog now: {len(catalog)} films")

    tmp = CATALOG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, CATALOG_PATH)
    log(f"Saved: {CATALOG_PATH}")

    state = {}
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
    state["berlin_integrated"] = True
    state["berlin_new"] = new_entries
    tmp2 = STATE_PATH + ".tmp"
    with open(tmp2, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp2, STATE_PATH)

    log("=" * 60)


if __name__ == "__main__":
    main()
