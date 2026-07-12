#!/usr/bin/env python3
"""
FilmVault — Integrate rio.ggusers.com download URLs into catalog.
Parses the rio_archive.csv, groups by series, creates/merges catalog entries.
"""
import csv
import json
import os
import re
import sys
import io
from datetime import datetime
from urllib.parse import unquote

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
CATALOG_PATH = os.path.join(BASE_DIR, "catalog.json")
RIO_CSV = os.path.join(BASE_DIR, "..", "output", "rio_archive.csv")
LOG_PATH = os.path.join(BASE_DIR, "pipeline.log")
STATE_PATH = os.path.join(BASE_DIR, "pipeline_state.json")


def log(msg):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] [rio] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def normalize_title(title):
    t = title.lower().strip()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    return re.sub(r"\s+", " ", t)


def parse_quality(quality_str):
    """Extract numeric quality like '1080', '720', '480' from quality string."""
    m = re.match(r"(\d{3,4})p?", quality_str)
    return m.group(1) if m else quality_str


def parse_rio_csv(csv_path):
    """Parse rio_archive.csv and group files by series."""
    series_map = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            series_name = unquote(row["series"])
            season = unquote(row["season"])
            quality_raw = unquote(row["quality"])
            url = row["url"]
            ext = row["extension"]

            if series_name not in series_map:
                series_map[series_name] = {
                    "seasons": {},
                    "qualities": set(),
                }

            s = series_map[series_name]
            s["qualities"].add(quality_raw)

            if season not in s["seasons"]:
                s["seasons"][season] = []

            # Decode the URL for the link entry
            decoded_url = unquote(url)

            # Parse quality number
            quality_num = parse_quality(quality_raw)

            # Determine link type from quality string
            link_type = "original"

            s["seasons"][season].append({
                "url": decoded_url,
                "quality": quality_num,
                "type": link_type,
                "quality_raw": quality_raw,
                "ext": ext,
            })

    return series_map


def extract_year_from_links(series_data):
    """Try to extract year from link URLs or filenames."""
    for season, files in series_data["seasons"].items():
        for f in files[:3]:
            # Pattern: Title.YEAR.Quality in filename
            url = f["url"]
            m = re.search(r"\.(20\d{2}|19\d{2})\.", url)
            if m:
                return m.group(1)
    return ""


def find_existing_match(catalog_index, series_name):
    """Find best matching catalog entry for a series name."""
    norm = normalize_title(series_name)
    best_match = None
    best_score = 0

    for idx, film in enumerate(catalog_index):
        existing_norm = normalize_title(film["title"])
        # Exact match
        if norm == existing_norm:
            return idx
        # Check if one contains the other
        if norm in existing_norm or existing_norm in norm:
            score = len(norm) / max(len(existing_norm), 1)
            if score > best_score:
                best_score = score
                best_match = idx

    return best_match if best_score > 0.6 else None


def build_rio_links(series_data):
    """Build a flat list of all video links across all seasons."""
    links = []
    for season, files in series_data["seasons"].items():
        for f in files:
            links.append({
                "url": f["url"],
                "quality": f["quality"],
                "type": f["type"],
            })
    return links


def main():
    log("=" * 60)
    log("Rio.ggusers.com Integration — Starting")
    log("=" * 60)

    # Load catalog
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    log(f"Catalog: {len(catalog)} films")

    # Build lookup index
    catalog_index = [{"title": f["title"], "year": f.get("year", "")} for f in catalog]

    # Parse rio CSV
    if not os.path.exists(RIO_CSV):
        log(f"Rio CSV not found: {RIO_CSV}")
        return

    series_map = parse_rio_csv(RIO_CSV)
    log(f"Rio series: {len(series_map)}")
    total_rio_files = sum(
        len(files)
        for s in series_map.values()
        for files in s["seasons"].values()
    )
    log(f"Rio total files: {total_rio_files}")

    # Match and merge
    matched = 0
    new_entries = 0
    total_links_added = 0

    for series_name, series_data in series_map.items():
        # Extract year if possible
        year = extract_year_from_links(series_data)

        # Build rio links
        rio_links = build_rio_links(series_data)
        if not rio_links:
            continue

        # Find existing match
        match_idx = find_existing_match(catalog_index, series_name)

        if match_idx is not None:
            # Merge: add rio links to existing entry
            existing = catalog[match_idx]
            existing_urls = set()
            for l in existing.get("links", []):
                url = l.get("url", "") if isinstance(l, dict) else (l[0] if isinstance(l, list) else "")
                existing_urls.add(url)

            added = 0
            for link in rio_links:
                if link["url"] not in existing_urls:
                    existing["links"].append(link)
                    existing_urls.add(link["url"])
                    added += 1

            if added > 0:
                existing["available"] = True
                total_links_added += added
                matched += 1
        else:
            # Create new entry
            entry = {
                "title": series_name,
                "year": year,
                "poster": "",
                "rating": "",
                "available": True,
                "links": rio_links,
                "genre": "",
                "source": "rio",
            }
            catalog.append(entry)
            catalog_index.append({"title": series_name, "year": year})
            total_links_added += len(rio_links)
            new_entries += 1

    log(f"Matched to existing: {matched}")
    log(f"New entries: {new_entries}")
    log(f"Total links added: {total_links_added}")
    log(f"Catalog now: {len(catalog)} films")

    # Save atomically
    tmp = CATALOG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, CATALOG_PATH)
    log(f"Saved: {CATALOG_PATH}")

    # Update state
    state = {}
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
    state["rio_integrated"] = True
    state["rio_new_entries"] = new_entries
    state["rio_matched"] = matched
    state["rio_links_added"] = total_links_added
    tmp2 = STATE_PATH + ".tmp"
    with open(tmp2, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp2, STATE_PATH)

    log("=" * 60)


if __name__ == "__main__":
    main()
