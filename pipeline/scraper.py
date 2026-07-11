#!/usr/bin/env python3
"""
FilmVault Incremental Scraper
Tracks last processed post ID. Each run processes new posts since last run.
Full coverage of talafillm.sbs in ~4 runs at 5000 posts/run.
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
PER_PAGE = 100
MAX_POSTS = 5000  # ~50 API calls, ~2 min — well within GitHub Actions timeout
CATALOG_PATH = os.path.join(os.path.dirname(__file__), "..", "catalog.json")
STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "pipeline_state.json")
LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "pipeline.log")


def log(msg):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def wp_get(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "FilmVault/2.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                headers = dict(resp.headers)
                return data, headers
        except Exception as e:
            log(f"  Retry {attempt+1}/{retries}: {e}")
            time.sleep(2 * (attempt + 1))
    return None, {}


def normalize_title(title):
    t = title.lower().strip()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    return re.sub(r"\s+", " ", t)


def clean_title(title):
    t = unescape(title).strip()
    # Strip Farsi prefixes/suffixes
    t = re.sub(r"^دانلود\s+(فیلم|انیمیشن|سریال)\s+", "", t)
    t = re.sub(r"\s+بدون\s+سانسور$", "", t)
    t = re.sub(r"\s+با\s+کیفیت\s+\d+p$", "", t)
    # Strip watermark
    t = re.sub(r"_?www\.TalaFilm\.Top$", "", t, flags=re.IGNORECASE)
    # Strip trailing year
    t = re.sub(r"\s+\d{4}$", "", t)
    return t.strip()


def extract_links(acf):
    """Extract ALL download links + subtitles."""
    links = []
    seen = set()

    # Video links from ACF fields
    for field in ["po_original_links", "po_dubbed_links"]:
        raw = acf.get(field, [])
        if isinstance(raw, str):
            try: raw = json.loads(raw)
            except Exception: continue
        if not isinstance(raw, list): continue
        link_type = "original" if "original" in field else "dubbed"
        for item in raw:
            if not isinstance(item, dict): continue
            url = item.get("po_video_url", "").strip()
            quality = item.get("po_quality", "1080")
            if url and url.startswith("http") and url not in seen:
                seen.add(url)
                links.append({"url": url, "quality": str(quality), "type": link_type})

    # New format: add_links
    for field in ["add_links", "add_links_iran", "add_links_hardsub"]:
        raw = acf.get(field, [])
        if isinstance(raw, str):
            try: raw = json.loads(raw)
            except Exception: continue
        if not isinstance(raw, list): continue
        for item in raw:
            if not isinstance(item, dict): continue
            url = item.get("op5", "").strip()
            label = item.get("op1", "")
            if url and url.startswith("http") and url not in seen:
                seen.add(url)
                q = "1080"
                m = re.search(r"(\d{3,4})p", label)
                if m: q = m.group(1)
                links.append({"url": url, "quality": q, "type": "original"})

    # Subtitles from ACF
    for sub_field in ["po_subtitle"]:
        sub = acf.get(sub_field, "")
        if isinstance(sub, str) and sub.startswith("http") and sub.strip() not in seen:
            seen.add(sub.strip())
            links.append({"url": sub.strip(), "quality": "sub", "type": "subtitle"})

    # Construct subtitle URLs from video URLs (dl3.tinyzmoviez.ir pattern)
    for link in list(links):
        if link["type"] in ("subtitle",): continue
        url = link["url"]
        # dl5.tinyzmoviez.ir/New.Film/2026/Name/file.mp4 → dl3.tinyzmoviez.ir/vtt/2026/Name/file.vtt
        sub_url = re.sub(
            r"https?://dl\d+\.tinyzmoviez\.ir/files_\d+/",
            lambda m: m.group(0).replace("/files_", "/vtt/").rstrip("/") + "/",
            url
        )
        if sub_url != url:
            sub_url = re.sub(r"\.(mp4|mkv)$", ".vtt", sub_url)
            if sub_url not in seen:
                seen.add(sub_url)
                links.append({"url": sub_url, "quality": "sub", "type": "subtitle"})

    return links


def extract_post(post):
    """Extract a single film from a WordPress post."""
    acf = post.get("acf", {})

    # Title: prefer English
    title_en = clean_title(str(acf.get("title_english", "") or ""))
    title_fa = clean_title(post.get("title", {}).get("rendered", ""))
    title = title_en if (title_en and len(title_en) >= 2) else title_fa
    if not title or len(title) < 2:
        return None

    # Year
    year = str(acf.get("release_date", "") or acf.get("po_year", "") or "")
    if not year:
        # Try extracting from first video URL
        links_raw = extract_links(acf)
        for lnk in links_raw:
            m = re.search(r"\.(20\d{2}|19\d{2})\.", lnk["url"])
            if m:
                year = m.group(1)
                break
    if not year:
        date = post.get("date", "")
        if date and len(date) >= 4:
            year = date[:4]

    # Rating
    rating = str(acf.get("imdb_rating", "") or acf.get("po_imdb", "") or "")
    if rating in ("0", "N/A", "null", ""):
        rating = ""

    # Poster
    poster = ""
    backdrop = acf.get("movies_backdrop", "")
    if isinstance(backdrop, str) and backdrop.startswith("http"):
        poster = backdrop
    if not poster:
        raw_poster = acf.get("po_poster", "")
        if isinstance(raw_poster, dict):
            poster = raw_poster.get("url", "")
        elif isinstance(raw_poster, str) and raw_poster.startswith("http"):
            poster = raw_poster

    # Genre
    genre = acf.get("po_genre", "")
    if isinstance(genre, list):
        genre = ", ".join(str(g) for g in genre)
    genre = str(genre or "")

    # Links (video + subtitles)
    links = extract_links(acf)

    return {
        "title": title,
        "year": year,
        "poster": poster,
        "rating": rating,
        "available": len(links) > 0,
        "links": links,
        "genre": genre,
    }


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_post_id": 0, "total_runs": 0, "total_added": 0}


def save_state(state):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_PATH)


def main():
    log("=" * 60)
    log("FilmVault Incremental Scraper — Starting")
    log("=" * 60)

    state = load_state()
    log(f"State: last_post_id={state['last_post_id']}, runs={state['total_runs']}")
    orig_last_id = state["last_post_id"]  # Don't update this during the run

    # Load catalog
    if os.path.exists(CATALOG_PATH):
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            catalog = json.load(f)
    else:
        catalog = []
    log(f"Catalog: {len(catalog)} films")

    # Build dedup index
    existing = {}
    for i, film in enumerate(catalog):
        key = normalize_title(film["title"]) + "|" + str(film.get("year", ""))
        existing[key] = i

    # Fetch new posts (pagination by page, filter by ID > last_post_id)
    new_films = []
    page = 1
    total_fetched = 0

    while total_fetched < MAX_POSTS:
        url = (
            f"{WP_API}?per_page={PER_PAGE}&page={page}"
            f"&_fields=id,slug,title,acf,date"
            f"&orderby=date&order=desc"
        )
        log(f"  Page {page} (fetched {total_fetched}/{MAX_POSTS})...")
        posts, headers = wp_get(url)

        if posts is None or len(posts) == 0:
            log(f"  No more posts.")
            break

        stop = False
        for post in posts:
            post_id = post.get("id", 0)

            # Skip posts we've already processed
            if post_id <= orig_last_id:
                stop = True
                break

            film = extract_post(post)
            if not film:
                continue

            # Dedup
            key = normalize_title(film["title"]) + "|" + str(film.get("year", ""))
            if key in existing:
                # Enrich existing if we have new data
                idx = existing[key]
                old = catalog[idx]
                if not old.get("poster") and film.get("poster"):
                    old["poster"] = film["poster"]
                if not old.get("rating") and film.get("rating"):
                    old["rating"] = film["rating"]
                # Merge new links
                old_urls = set()
                for l in old.get("links", []):
                    if isinstance(l, dict):
                        old_urls.add(l["url"])
                    elif isinstance(l, list) and l:
                        old_urls.add(l[0])
                for link in film.get("links", []):
                    if link["url"] not in old_urls:
                        old["links"].append(link)
                        old["available"] = True
            else:
                new_films.append(film)
                existing[key] = len(catalog) + len(new_films) - 1

            # Update high water mark
            state["last_post_id"] = max(state["last_post_id"], post_id)
            total_fetched += 1

        if stop:
            break

        # Check if there are more pages
        # Case-insensitive header lookup
        total_pages = 0
        for k, v in headers.items():
            if k.lower() == "x-wp-totalpages":
                total_pages = int(v)
                break
        if total_pages == 0:
            # No header — infer from response length
            if len(posts) < PER_PAGE:
                log(f"  Last page ({len(posts)} posts < {PER_PAGE}).")
                break
        elif page >= total_pages:
            log(f"  Reached last page ({total_pages}).")
            break

        page += 1
        time.sleep(0.5)  # Be polite

    # Append new films
    catalog.extend(new_films)

    # Clean Farsi-only entries with no links
    before = len(catalog)
    catalog = [f for f in catalog if not (
        re.search(r"[\u0600-\u06FF]", f.get("title", "")) and not f.get("links")
    )]
    cleaned = before - len(catalog)

    # Save atomically
    tmp = CATALOG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, CATALOG_PATH)

    # Update state
    state["total_runs"] += 1
    state["total_added"] += len(new_films)
    save_state(state)

    size_mb = os.path.getsize(CATALOG_PATH) / 1024 / 1024
    log(f"Result: {len(new_films)} new, {cleaned} cleaned, {len(catalog)} total ({size_mb:.1f}MB)")
    log(f"Last post ID: {state['last_post_id']}")
    log("=" * 60)
    return len(new_films)


if __name__ == "__main__":
    added = main()
    sys.exit(0 if added >= 0 else 1)
