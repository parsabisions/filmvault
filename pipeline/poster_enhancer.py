#!/usr/bin/env python3
"""
FilmVault Poster Enhancer
Scrapes OMDB free API for films missing posters.
Runs after scraper.py — only processes films without posters.
1000 free OMDB requests/day is plenty for incremental updates.
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse

CATALOG_PATH = os.path.join(os.path.dirname(__file__), "..", "catalog.json")
OMDB_KEY = os.environ.get("OMDB_KEY", "b0a0c7e0")  # Free OMDB key
BATCH_SIZE = 50  # Process 50 per run to stay under rate limits


def log(msg):
    print(f"[poster] {msg}")


def fetch_omdb(title, year):
    """Fetch movie data from OMDB API."""
    params = urllib.parse.urlencode({
        "t": title,
        "y": year,
        "apikey": OMDB_KEY,
    })
    url = f"http://www.omdbapi.com/?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FilmVault/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("Response") == "True":
                return data
    except Exception as e:
        log(f"  OMDB error for '{title}': {e}")
    return None


def main():
    if not os.path.exists(CATALOG_PATH):
        log("No catalog found.")
        return

    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    log(f"Catalog: {len(catalog)} films")

    # Find films without posters
    no_poster = [
        i for i, film in enumerate(catalog)
        if not film.get("poster") and film.get("year")
    ]
    log(f"Films missing posters: {len(no_poster)}")

    if not no_poster:
        log("All films have posters. Done.")
        return

    # Process up to BATCH_SIZE
    updated = 0
    for idx in no_poster[:BATCH_SIZE]:
        film = catalog[idx]
        title = film["title"]
        year = film["year"]

        data = fetch_omdb(title, year)
        if data:
            poster = data.get("Poster", "")
            if poster and poster != "N/A":
                film["poster"] = poster
                updated += 1
                log(f"  + Poster: {title} ({year})")

            # Also enrich rating if missing
            if not film.get("rating") and data.get("imdbRating"):
                rating = data["imdbRating"]
                if rating != "N/A":
                    film["rating"] = rating

            # Enrich genre if missing
            if not film.get("genre") and data.get("Genre"):
                film["genre"] = data["Genre"]

        time.sleep(0.15)  # Stay under 10 req/sec OMDB limit

    if updated > 0:
        with open(CATALOG_PATH, "w", encoding="utf-8") as f:
            json.dump(catalog, f, ensure_ascii=False, separators=(",", ":"))
        log(f"Updated {updated} posters. Catalog saved.")
    else:
        log("No new posters found this run.")


if __name__ == "__main__":
    main()
