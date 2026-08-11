#!/usr/bin/env python3
"""
causelist_watcher.py

Checks the J&K High Court (Srinagar Wing) causelist page for PDFs, downloads
the ones you've asked for (day-wise / entire / registrar / supplementary),
searches them for your name, and keeps a running local record + dashboard.

Usage:
    python causelist_watcher.py            # normal run
    python causelist_watcher.py --dry-run  # fetch & parse, don't save anything

Setup:
    1. pip install -r requirements.txt
    2. cp config.example.json config.json   (then edit config.json)
    3. python causelist_watcher.py
See README.md for scheduling it to run automatically (Task Scheduler / cron / GitHub Actions).
"""
import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime

import requests

from causelist_core import (
    CAUSELIST_PAGE,
    PARSER_VERSION,
    build_people,
    extract_entries_from_pdf,
    find_causelist_links,
    guess_date_from_filename,
    match_people,
)
from dashboard_template import render_dashboard

HERE = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(HERE, "downloads")
DATA_FILE = os.path.join(HERE, "cases_auto.json")
MANIFEST_FILE = os.path.join(HERE, "manifest.json")
DASHBOARD_FILE = os.path.join(HERE, "causelist_dashboard.html")
LOG_FILE = os.path.join(HERE, "watcher.log")
CONFIG_FILE = os.path.join(HERE, "config.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
PDF_HEADERS = dict(HEADERS, **{"Accept": "application/pdf,*/*", "Referer": CAUSELIST_PAGE})


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
    )


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logging.warning("Could not read %s, starting fresh", path)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_config():
    if not os.path.exists(CONFIG_FILE):
        logging.error(
            "config.json not found. Copy config.example.json to config.json and fill in your name."
        )
        sys.exit(1)
    cfg = load_json(CONFIG_FILE, {})
    has_single = bool(cfg.get("name"))
    has_people = bool(cfg.get("people")) and any(p.get("name") for p in cfg["people"])
    if not has_single and not has_people:
        logging.error(
            "config.json needs either a 'name', or a 'people' list with at least one name. "
            "See config.example.json / README.md."
        )
        sys.exit(1)
    cfg.setdefault("aliases", [])
    cfg.setdefault("list_types", ["daywise", "supplementary", "entire", "registrar"])
    return cfg


def fetch_page(session):
    resp = session.get(CAUSELIST_PAGE, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def download_pdf(session, url, dest_path):
    resp = session.get(url, headers=PDF_HEADERS, timeout=60)
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "")
    if "pdf" not in content_type.lower() and resp.content[:4] != b"%PDF":
        raise ValueError(f"Response doesn't look like a PDF (Content-Type: {content_type})")
    with open(dest_path, "wb") as f:
        f.write(resp.content)
    return hashlib.sha256(resp.content).hexdigest()


def merge_matches(existing, new_results):
    def key(r):
        return (r.get("date"), r.get("court"), r.get("sr"), r.get("caseNo"), r.get("person"))

    existing_keys = {key(r) for r in existing}
    added = 0
    for r in new_results:
        k = key(r)
        if k not in existing_keys:
            r = dict(r)
            r["id"] = "-".join(str(x) for x in k) + f"-{added}-{int(time.time())}"
            existing.append(r)
            existing_keys.add(k)
            added += 1
    return existing, added


def run(dry_run=False):
    setup_logging()
    cfg = load_config()
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    manifest = load_json(MANIFEST_FILE, {})
    matches = load_json(DATA_FILE, [])
    people = build_people(cfg)
    people_label = ", ".join(p["person"] for p in people)
    logging.info("Watching for: %s", people_label)

    session = requests.Session()
    logging.info("Fetching %s", CAUSELIST_PAGE)
    try:
        html = fetch_page(session)
    except Exception as e:
        logging.error("Could not reach the causelist page: %s", e)
        logging.error(
            "The site may be temporarily down, or blocking automated requests. "
            "Try again later, or download the PDF by hand and use the upload app instead."
        )
        sys.exit(2)

    links = find_causelist_links(html)
    wanted = [l for l in links if l["type"] in cfg["list_types"]]
    logging.info(
        "Found %d relevant causelist link(s) on the page (%d after filtering by list_types)",
        len(links),
        len(wanted),
    )

    new_results_total = []
    for link in wanted:
        fname = os.path.basename(link["url"].split("?")[0])
        dest = os.path.join(DOWNLOAD_DIR, fname)
        try:
            logging.info("Downloading %s (%s)", fname, link["type"])
            file_hash = download_pdf(session, link["url"], dest)
        except Exception as e:
            logging.warning("Could not download %s: %s", link["url"], e)
            continue

        prev = manifest.get(link["url"])
        if prev and prev.get("hash") == file_hash and prev.get("parser_version") == PARSER_VERSION:
            logging.info("Unchanged since last run, skipping re-parse: %s", fname)
            continue
        manifest[link["url"]] = {
            "hash": file_hash,
            "parser_version": PARSER_VERSION,
            "last_seen": datetime.now().isoformat(),
        }

        try:
            date_guess = link.get("date") or guess_date_from_filename(fname)
            entries = extract_entries_from_pdf(dest, fallback_date=date_guess)
        except Exception as e:
            logging.warning("Could not read text from %s: %s (may be a scanned/image PDF)", fname, e)
            continue

        if not entries:
            logging.info("No case entries found in %s (empty, scanned, or an unrecognized layout) — skipping", fname)
            continue

        results = match_people(entries, people, fname)
        logging.info("%s: %d case row(s) read, %d potential match(es)", fname, len(entries), len(results))
        new_results_total.extend(results)

    if dry_run:
        logging.info("Dry run — nothing saved. Would have added up to %d match(es).", len(new_results_total))
        return

    matches, added = merge_matches(matches, new_results_total)
    save_json(DATA_FILE, matches)
    save_json(MANIFEST_FILE, manifest)

    dashboard_html = render_dashboard(
        matches,
        people_label,
        source_note="last checked " + datetime.now().strftime("%d %b %Y, %I:%M %p"),
    )
    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        f.write(dashboard_html)

    logging.info("Added %d new match(es). Total saved: %d. Dashboard: %s", added, len(matches), DASHBOARD_FILE)
    for r in new_results_total:
        logging.info(
            "  -> [%s] %s | Court %s | Sr %s | %s",
            r.get("person"), r.get("date"), r.get("court"), r.get("sr"), r.get("caseNo"),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check the J&K High Court (Srinagar) causelist for your cases.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and parse but don't save or update the dashboard")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
