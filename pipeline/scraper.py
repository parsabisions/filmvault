#!/usr/bin/env python3
"""
FilmVault Auto-Scraper Pipeline
Runs on GitHub Actions every 6 hours. Scrapes talafillm.sbs WordPress API
for new films, extracts download URLs, fetches posters, and rebuilds catalog.json.

No API keys needed. No rate limits. Just WordPress REST API.
Handles both old and new talafillm.sbs ACF field formats.
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime
from html import unescape

# ── Config ────────────────────────────────────────────
WP_API = "https://talafillm.sbs/wp-json/wp/v2/posts"
PER_PAGE = 50
MAX_PAGES = 30  # Safety cap: last 1500 posts per run
CATALOG_PATH = os.path.join(os.path.dirname(__file__), "..", "catalog.json")
LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "pipeline.log")


def log(msg):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def wp_get(url, retries=3):
    """Fetch a WordPress API URL with retries."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "FilmVault/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            log(f"  Retry {attempt + 1}/{retries} for {url[:80]}... ({e})")
            time.sleep(2 * (attempt + 1))
    return None


def normalize_title(title):
    """Normalize a title for deduplication."""
    t = title.lower().strip()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


def clean_title(title):
    """Clean up a raw title from the API.
    Handles both old format (Farsi title with prefixes) and new format (title_english).
    """
    t = unescape(title).strip()
    # Remove Farsi prefixes/suffixes
    t = re.sub(r"^دانلود\s+(فیلم|انیمیشن|سریال)\s+", "", t)
    t = re.sub(r"\s+بدون\s+سانسور$", "", t)
    t = re.sub(r"\s+با\s+کیفیت\s+\d+p$", "", t)
    # Remove "_www.TalaFilm.Top" suffix
    t = re.sub(r"_?www\.TalaFilm\.Top$", "", t, flags=re.IGNORECASE)
    # Remove trailing 4-digit years (year is separate field)
    t = re.sub(r"\s+\d{4}$", "", t)
    return t.strip()


def extract_links(acf):
    """Extract download URLs from ACF fields. Handles both old and new formats."""
    links = []
    seen = set()

    for field in ["po_original_links", "po_dubbed_links"]:
        raw = acf.get(field, [])
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except:
                continue
        if not isinstance(raw, list):
            continue

        link_type = "original" if "original" in field else "dubbed"

        for item in raw:
            if not isinstance(item, dict):
                continue
            url = item.get("po_video_url", "")
            quality = item.get("po_quality", "1080")
            if url and url.startswith("http"):
                url = url.strip()
                if url not in seen:
                    seen.add(url)
                    links.append([url, str(quality), link_type])

    # New format: add_links (op5 = URL, op1 = quality label)
    for field in ["add_links", "add_links_iran", "add_links_hardsub"]:
        raw = acf.get(field, [])
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except:
                continue
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            url = item.get("op5", "").strip()
            label = item.get("op1", "")
            if url and url.startswith("http") and url not in seen:
                seen.add(url)
                # Parse quality from label
                q = "1080"
                m = re.search(r"(\d{3,4})p", label)
                if m:
                    q = m.group(1)
                links.append([url, q, "original"])

    # Subtitles
    for sub_field in ["po_subtitle", "add_audio_link"]:
        sub = acf.get(sub_field, "")
        if isinstance(sub, str) and sub.startswith("http") and sub.strip() not in seen:
            seen.add(sub.strip())
            links.append([sub.strip(), "sub", "sub"])

    return links


def fetch_new_posts(existing_title_years, max_pages=MAX_PAGES):
    """Fetch new posts from talafillm.sbs WordPress API."""
    new_films = []

    for page in range(1, max_pages + 1):
        url = (
            f"{WP_API}?per_page={PER_PAGE}&page={page}"
            f"&_fields=id,slug,title,acf,date"
            f"&orderby=date&order=desc"
        )
        log(f"  Fetching page {page}...")
        posts = wp_get(url)

        if posts is None:
            log(f"  Failed to fetch page {page}, stopping.")
            break
        if not posts:
            log(f"  No more posts at page {page}.")
            break

        stop = False
        for post in posts:
            title_raw = post.get("title", {}).get("rendered", "")
            acf = post.get("acf", {})

            # ── Extract title ──────────────────────
            # Prefer title_english (new format) over Farsi title
            title_en = clean_title(str(acf.get("title_english", "") or ""))
            title_fa = clean_title(title_raw)
            title = title_en if (title_en and len(title_en) >= 2) else title_fa
            if not title or len(title) < 2:
                continue

            # ── Extract links first (needed for year extraction) ──
            links = extract_links(acf)

            # ── Extract year ───────────────────────
            year = str(acf.get("po_year", "") or acf.get("release_date", "") or "")
            if not year:
                # Try extracting from download URL
                for lnk in links:
                    m = re.search(r"\.(20\d{2}|19\d{2})\.", lnk[0])
                    if m:
                        year = m.group(1)
                        break
            if not year:
                # Guess from post date
                date = post.get("date", "")
                if date and len(date) >= 4:
                    year = date[:4]

            # Dedup: check if we already have this title+year
            norm_key = normalize_title(title) + "|" + str(year)
            if norm_key in existing_title_years:
                log(f"  Hit existing at page {page}: {title} ({year}) — stopping.")
                stop = True
                break

            # ── Extract rating ─────────────────────
            # New format: imdb_rating. Old: po_imdb
            rating = str(acf.get("imdb_rating", "") or acf.get("po_imdb", "") or "")
            if rating in ("0", "N/A", "null"):
                rating = ""

            # ── Extract poster ─────────────────────
            # New format: movies_backdrop (full URL). Old: po_poster (may be dict)
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

            # ── Extract genre ──────────────────────
            genre = acf.get("po_genre", "")
            if isinstance(genre, list):
                genre = ", ".join(str(g) for g in genre)
            genre = str(genre or "")

            new_films.append({
                "title": title,
                "year": year,
                "poster": poster,
                "rating": rating,
                "available": len(links) > 0,
                "links": links,
                "genre": genre,
            })

        if stop:
            break
        time.sleep(1)  # Be polite

    log(f"  Fetched {min(page, max_pages)} pages, found {len(new_films)} new films.")
    return new_films


def update_catalog(new_films, existing_catalog):
    """Merge new films into existing catalog, deduplicate."""
    existing_norm = {}
    for i, film in enumerate(existing_catalog):
        key = normalize_title(film["title"]) + "|" + str(film.get("year", ""))
        existing_norm[key] = i

    added = 0
    for film in new_films:
        key = normalize_title(film["title"]) + "|" + str(film.get("year", ""))

        if key in existing_norm:
            # Already exists — enrich if missing data
            idx = existing_norm[key]
            existing = existing_catalog[idx]
            if not existing.get("poster") and film.get("poster"):
                existing["poster"] = film["poster"]
            if not existing.get("rating") and film.get("rating"):
                existing["rating"] = film["rating"]
            # Merge any new links
            existing_urls = {l[0] for l in existing.get("links", [])}
            for link in film.get("links", []):
                if link[0] not in existing_urls:
                    existing.setdefault("links", []).append(link)
                    existing["available"] = True
        else:
            existing_catalog.append(film)
            existing_norm[key] = len(existing_catalog) - 1
            added += 1

    log(f"  Merged: {added} new films added, {len(new_films) - added} duplicates enriched.")
    return existing_catalog, added


def main():
    log("=" * 60)
    log("FilmVault Pipeline — Starting")
    log("=" * 60)

    # Load existing catalog
    if os.path.exists(CATALOG_PATH):
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            catalog = json.load(f)
        log(f"Loaded existing catalog: {len(catalog)} films")
    else:
        catalog = []
        log("No existing catalog found — starting fresh.")

    # Build dedup index
    existing_title_years = set()
    for film in catalog:
        key = normalize_title(film["title"]) + "|" + str(film.get("year", ""))
        existing_title_years.add(key)
    log(f"Existing title+year keys: {len(existing_title_years)}")

    # Fetch new posts
    new_films = fetch_new_posts(existing_title_years)

    if not new_films:
        log("No new films found. Pipeline complete.")
        return 0

    # Merge into catalog
    catalog, added = update_catalog(new_films, catalog)

    # Save
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = os.path.getsize(CATALOG_PATH) / 1024 / 1024
    log(f"Catalog saved: {len(catalog)} films ({size_mb:.1f}MB)")
    log(f"New films added this run: {added}")
    log("=" * 60)

    return added


if __name__ == "__main__":
    added = main()
    sys.exit(0 if added >= 0 else 1)
