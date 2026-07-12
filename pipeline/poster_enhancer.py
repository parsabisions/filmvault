#!/usr/bin/env python3
"""
FilmVault OMDB Enricher
Batch-enriches catalog entries with posters, ratings, genres from OMDB API.
Tracks progress for resume across runs. Processes 500 films per run.
"""
import json
import os
import re
import sys
import io
import time
import urllib.request
import urllib.parse
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
CATALOG_PATH = os.path.join(BASE_DIR, "catalog.json")
LOG_PATH = os.path.join(BASE_DIR, "pipeline.log")
STATE_PATH = os.path.join(BASE_DIR, "pipeline_state.json")
OMDB_KEY = os.environ.get("OMDB_KEY", "b0a0c7e0")
BATCH_SIZE = 500


def log(msg):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] [omdb] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def fetch_omdb(title, year, retries=3):
    params = urllib.parse.urlencode({"t": title, "y": year, "apikey": OMDB_KEY})
    url = f"http://www.omdbapi.com/?{params}"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "FilmVault/2.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("Response") == "True":
                    return data
                if data.get("Error") == "Too many results.":
                    return None
                if "not found" in data.get("Error", "").lower():
                    return None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
            else:
                log(f"  Failed after {retries} attempts for '{title}': {e}")
    return None


def needs_enrichment(film):
    """Check if film needs any OMDB data."""
    return (
        not film.get("poster")
        or not film.get("rating")
        or not film.get("genre")
    )


def main():
    log("=" * 60)
    log("OMDB Enricher — Starting")
    log("=" * 60)

    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    log(f"Catalog: {len(catalog)} films")

    # Find films needing enrichment
    candidates = [
        i for i, film in enumerate(catalog)
        if film.get("year") and needs_enrichment(film)
    ]
    log(f"Need enrichment: {len(candidates)}")

    if not candidates:
        log("Nothing to enrich. Done.")
        return

    updated = 0
    queried = 0
    for idx in candidates[:BATCH_SIZE]:
        film = catalog[idx]
        title = film["title"]
        year = film["year"]

        data = fetch_omdb(title, year)
        queried += 1

        if data:
            changed = False

            # Poster
            poster = data.get("Poster", "")
            if poster and poster != "N/A" and not film.get("poster"):
                film["poster"] = poster
                changed = True

            # Rating
            rating = data.get("imdbRating", "")
            if rating and rating != "N/A" and not film.get("rating"):
                film["rating"] = rating
                changed = True

            # Genre
            genre = data.get("Genre", "")
            if genre and genre != "N/A" and not film.get("genre"):
                film["genre"] = genre
                changed = True

            # Director
            director = data.get("Director", "")
            if director and director != "N/A" and not film.get("director"):
                film["director"] = director
                changed = True

            # Description
            plot = data.get("Plot", "")
            if plot and plot != "N/A" and not film.get("description"):
                film["description"] = plot
                changed = True

            if changed:
                updated += 1

        if queried % 100 == 0:
            log(f"  Progress: {queried}/{min(len(candidates), BATCH_SIZE)} queried, {updated} updated")

        time.sleep(0.12)

    # Save
    if updated > 0:
        tmp = CATALOG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(catalog, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, CATALOG_PATH)
        log(f"Updated {updated} films. Catalog saved.")
    else:
        log("No updates this run.")

    # State
    state = {}
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
    state["omdb_last_run"] = datetime.now().isoformat()
    state["omdb_updated"] = updated
    state["omdb_queried"] = queried
    tmp2 = STATE_PATH + ".tmp"
    with open(tmp2, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp2, STATE_PATH)

    log("=" * 60)


if __name__ == "__main__":
    main()
