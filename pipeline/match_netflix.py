#!/usr/bin/env python3
"""
FilmVault — Match Netflix catalog entries against unified catalog.
Merges Netflix metadata (genre, director, cast, country, description) into matched entries.
Creates new entries for unmatched Netflix titles.
"""
import csv
import json
import os
import re
import sys
import io
from collections import defaultdict
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
CATALOG_PATH = os.path.join(BASE_DIR, "catalog.json")
NETFLIX_CSV = os.path.join(BASE_DIR, "..", "other download links", "archive_extracted", "netflix_titles.csv")
LOG_PATH = os.path.join(BASE_DIR, "pipeline.log")
STATE_PATH = os.path.join(BASE_DIR, "pipeline_state.json")


def log(msg):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] [netflix] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def normalize(title):
    t = title.lower().strip()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    return re.sub(r"\s+", " ", t)


def word_set(title):
    return frozenset(normalize(title).split())


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def year_close(nf_year, cat_year):
    if not nf_year or not cat_year:
        return False
    try:
        return abs(int(nf_year) - int(cat_year)) <= 1
    except (ValueError, TypeError):
        return False


def main():
    log("=" * 60)
    log("Netflix Catalog Matcher — Starting")
    log("=" * 60)

    # Load Netflix
    netflix = []
    with open(NETFLIX_CSV, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            netflix.append(row)
    log(f"Netflix titles: {len(netflix)}")

    # Load catalog
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    log(f"Catalog: {len(catalog)} films")

    # Build prefix index
    prefix_index = defaultdict(list)
    cat_norm_map = {}
    for i, film in enumerate(catalog):
        norm = normalize(film["title"])
        prefix_index[norm[:3]].append(i)
        if norm not in cat_norm_map:
            cat_norm_map[norm] = i

    cat_words = [word_set(f["title"]) for f in catalog]
    cat_years = [f.get("year", "") for f in catalog]
    cat_norms = [normalize(f["title"]) for f in catalog]

    exact_matched = 0
    fuzzy_matched = 0
    unmatched = 0
    metadata_enriched = 0

    for row in netflix:
        norm = normalize(row["title"])
        nf_words = word_set(row["title"])
        nf_year = row["release_year"]
        prefix = norm[:3]

        match_idx = None

        # Exact match
        if norm in cat_norm_map:
            match_idx = cat_norm_map[norm]
            exact_matched += 1
        else:
            # Fuzzy: gather candidates
            candidate_set = set()
            candidate_set.update(prefix_index.get(prefix, []))
            first_word = norm.split()[0] if norm.split() else ""
            if len(first_word) >= 3:
                for p, entries in prefix_index.items():
                    if p.startswith(first_word[:3]) or first_word.startswith(p):
                        candidate_set.update(entries)

            best_score = 0
            best_idx = -1
            for idx in candidate_set:
                score = jaccard(nf_words, cat_words[idx])
                # Require year proximity for fuzzy matches
                if year_close(nf_year, cat_years[idx]):
                    score += 0.2
                elif nf_year and cat_years[idx]:
                    score -= 0.2
                if score > best_score:
                    best_score = score
                    best_idx = idx

            # Stricter threshold: 0.6 without year match, 0.5 with year match
            if best_idx >= 0:
                has_year_match = year_close(nf_year, cat_years[best_idx])
                threshold = 0.5 if has_year_match else 0.65
                if best_score >= threshold:
                    match_idx = best_idx
                    fuzzy_matched += 1

        if match_idx is not None:
            # Merge Netflix metadata
            film = catalog[match_idx]
            enriched = False

            # Genre: take Netflix genre if catalog has none
            nf_genre = row.get("listed_in", "").strip()
            if nf_genre and not film.get("genre"):
                film["genre"] = nf_genre
                enriched = True

            # Description: take if catalog has none
            nf_desc = row.get("description", "").strip()
            if nf_desc and not film.get("description"):
                film["description"] = nf_desc
                enriched = True

            # Director: take if catalog has none
            nf_director = row.get("director", "").strip()
            if nf_director and nf_director != "Unknown" and not film.get("director"):
                film["director"] = nf_director
                enriched = True

            # Source tag
            if not film.get("source"):
                film["source"] = "netflix_match"

            if enriched:
                metadata_enriched += 1
        else:
            unmatched += 1
            # Create new entry with Netflix metadata only (no download links)
            nf_genre = row.get("listed_in", "").strip()
            entry = {
                "title": row["title"],
                "year": str(nf_year) if nf_year else "",
                "poster": "",
                "rating": "",
                "available": False,
                "links": [],
                "genre": nf_genre,
                "description": row.get("description", "").strip(),
                "director": row.get("director", "").strip() if row.get("director", "").strip() != "Unknown" else "",
                "source": "netflix",
            }
            catalog.append(entry)

    log(f"Exact matches: {exact_matched}")
    log(f"Fuzzy matches: {fuzzy_matched}")
    log(f"Total matched: {exact_matched + fuzzy_matched}")
    log(f"Metadata enriched: {metadata_enriched}")
    log(f"Unmatched (new entries): {unmatched}")
    log(f"Catalog now: {len(catalog)} films")

    # Save
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
    state["netflix_matched"] = exact_matched + fuzzy_matched
    state["netflix_enriched"] = metadata_enriched
    state["netflix_new_entries"] = unmatched
    tmp2 = STATE_PATH + ".tmp"
    with open(tmp2, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp2, STATE_PATH)

    log("=" * 60)


if __name__ == "__main__":
    main()
