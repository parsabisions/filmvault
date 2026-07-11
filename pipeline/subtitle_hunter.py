#!/usr/bin/env python3
"""
FilmVault Subtitle Hunter
Finds subtitles for films that don't have them yet.
Constructs candidate URLs from video URL patterns and checks if they exist.
"""

import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime

CATALOG_PATH = os.path.join(os.path.dirname(__file__), "..", "catalog.json")
STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "pipeline_state.json")
LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "pipeline.log")
MAX_CHECKS = 3000


def log(msg):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] [sub] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_video_links(film):
    """Extract video URLs from either dict or list format links."""
    videos = []
    for l in film.get("links", []):
        if isinstance(l, dict) and l.get("type") in ("original", "dubbed"):
            videos.append(l["url"])
        elif isinstance(l, list) and len(l) >= 3 and l[2] in ("original", "dubbed"):
            videos.append(l[0])
    return videos


def has_subtitle(film):
    for l in film.get("links", []):
        if isinstance(l, dict) and l.get("type") == "subtitle":
            return True
        if isinstance(l, list) and len(l) >= 3 and l[2] == "subtitle":
            return True
    return False


def construct_subtitle_candidates(video_url):
    """Given a video URL, construct possible subtitle URLs."""
    candidates = []
    # dl5/dl6.tinyzmoviez.ir → dl3/dl6/dl8 for subtitles
    for cdn in [3, 6, 8]:
        sub = re.sub(r"https?://dl\d+\.tinyzmoviez\.ir/", f"https://dl{cdn}.tinyzmoviez.ir/", video_url)
        sub = re.sub(r"/files_\d+/", "/vtt/", sub)
        sub = re.sub(r"\.(mp4|mkv|avi)$", ".vtt", sub)
        if sub != video_url:
            candidates.append(sub)
            candidates.append(sub.replace(".vtt", ".srt"))
    return candidates


def url_exists(url, timeout=8):
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "FilmVault/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 400
    except urllib.error.HTTPError:
        return False
    except Exception:
        return False


def save_catalog(catalog):
    tmp = CATALOG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, CATALOG_PATH)


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_PATH)


def main():
    if not os.path.exists(CATALOG_PATH):
        log("No catalog found.")
        return

    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    log(f"Catalog: {len(catalog)} films")

    # Find films needing subtitles
    needs_sub = []
    has_sub = 0
    for i, film in enumerate(catalog):
        if has_subtitle(film):
            has_sub += 1
        elif get_video_links(film):
            needs_sub.append(i)

    log(f"With subtitles: {has_sub}, without: {len(needs_sub)}")

    if not needs_sub:
        log("All films with video links have subtitles.")
        return

    # Resume from last checked index
    state = load_state()
    start_idx = state.get("sub_last_checked", 0)
    if start_idx > 0:
        log(f"Resuming from index {start_idx}")

    checked = 0
    found = 0
    last_checked = start_idx

    for idx in needs_sub[start_idx:start_idx + MAX_CHECKS]:
        film = catalog[idx]
        videos = get_video_links(film)
        if not videos:
            continue

        for vurl in videos:
            candidates = construct_subtitle_candidates(vurl)
            for sub_url in candidates:
                if url_exists(sub_url):
                    film.setdefault("links", []).append({
                        "url": sub_url,
                        "quality": "sub",
                        "type": "subtitle"
                    })
                    found += 1
                    log(f"  + {film['title']} ({film['year']}) → {sub_url.split('/')[-1]}")
                    break
            if has_subtitle(film):
                break

        checked += 1
        last_checked = start_idx + checked
        if checked % 200 == 0:
            log(f"  Progress: {checked}/{min(len(needs_sub) - start_idx, MAX_CHECKS)} checked, {found} found")
            if found > 0:
                save_catalog(catalog)
                state["sub_last_checked"] = last_checked
                save_state(state)
        time.sleep(0.02)

    if found > 0:
        save_catalog(catalog)
        state["sub_last_checked"] = last_checked
        save_state(state)
        log(f"Done: {found} subtitles found across {checked} films.")
    else:
        log(f"No new subtitles found across {checked} films.")


if __name__ == "__main__":
    main()
