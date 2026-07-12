#!/usr/bin/env python3
"""
FilmVault — Integrate giftmond.ir (simbaios_final.json) into catalog.
Resolves generic titles from download URL filenames.
"""
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
GIFTMOND_PATH = os.path.join(BASE_DIR, "..", "other download links", "simbaios_final.json")
LOG_PATH = os.path.join(BASE_DIR, "pipeline.log")
STATE_PATH = os.path.join(BASE_DIR, "pipeline_state.json")


def log(msg):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] [giftmond] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def normalize(title):
    t = title.lower().strip()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    return re.sub(r"\s+", " ", t)


def extract_title_from_url(url):
    """Try to extract a meaningful title from a giftmond.ir URL."""
    # Pattern: .../files_N/Title/Quality/file.ext or .../Title/Quality/file.ext
    decoded = unquote(url)
    # Remove domain
    path = re.sub(r"https?://[^/]+/", "", decoded)
    parts = path.split("/")
    # Skip 'files_N', 'New.Film', year-like parts
    title_parts = []
    for p in parts:
        if re.match(r"^(files_\d+|New\.Film|Old\.Film|Serial)$", p):
            continue
        if re.match(r"^\d{4}$", p):
            continue
        if re.match(r"^\d{3,4}p", p):
            break
        if "." in p and any(ext in p.lower() for ext in [".mp4", ".mkv", ".avi"]):
            break
        title_parts.append(p.replace(".", " "))
    return " ".join(title_parts).strip() if title_parts else ""


def main():
    log("=" * 60)
    log("Giftmond.ir Integration — Starting")
    log("=" * 60)

    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    log(f"Catalog: {len(catalog)} films")

    if not os.path.exists(GIFTMOND_PATH):
        log(f"File not found: {GIFTMOND_PATH}")
        return

    with open(GIFTMOND_PATH, "r", encoding="utf-8") as f:
        giftmond = json.load(f)

    movies = giftmond.get("movies", {})
    log(f"Giftmond entries: {len(movies)}")

    # Build catalog index
    cat_norm_map = {}
    for i, film in enumerate(catalog):
        key = normalize(film["title"])
        if key not in cat_norm_map:
            cat_norm_map[key] = i

    matched = 0
    new_entries = 0
    links_added = 0

    for movie_id, movie_data in movies.items():
        title = movie_data.get("title", "")
        urls = movie_data.get("urls", [])
        if not urls:
            continue

        # Try to extract real title from first URL
        real_title = extract_title_from_url(urls[0]) if urls else ""
        display_title = real_title if real_title and len(real_title) > 2 else title

        # Filter to video URLs only
        video_urls = [u for u in urls if any(ext in u.lower() for ext in [".mp4", ".mkv", ".avi", ".mov"])]
        if not video_urls:
            video_urls = urls[:5]

        # Build links
        links = []
        for url in video_urls[:10]:
            q = "1080"
            m = re.search(r"(\d{3,4})p", url)
            if m:
                q = m.group(1)
            links.append({"url": unquote(url), "quality": q, "type": "original"})

        if not links:
            continue

        # Match against catalog
        norm = normalize(display_title)
        match_idx = cat_norm_map.get(norm)

        if match_idx is not None:
            existing = catalog[match_idx]
            existing_urls = set()
            for l in existing.get("links", []):
                u = l.get("url", "") if isinstance(l, dict) else (l[0] if isinstance(l, list) else "")
                existing_urls.add(u)
            added = 0
            for link in links:
                if link["url"] not in existing_urls:
                    existing["links"].append(link)
                    existing_urls.add(link["url"])
                    added += 1
            if added > 0:
                existing["available"] = True
                links_added += added
                matched += 1
        else:
            entry = {
                "title": display_title,
                "year": "",
                "poster": "",
                "rating": "",
                "available": True,
                "links": links,
                "genre": "",
                "source": "giftmond",
            }
            catalog.append(entry)
            cat_norm_map[norm] = len(catalog) - 1
            links_added += len(links)
            new_entries += 1

    log(f"Matched: {matched}, New: {new_entries}, Links added: {links_added}")
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
    state["giftmond_integrated"] = True
    state["giftmond_new"] = new_entries
    state["giftmond_matched"] = matched
    tmp2 = STATE_PATH + ".tmp"
    with open(tmp2, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp2, STATE_PATH)

    log("=" * 60)


if __name__ == "__main__":
    main()
