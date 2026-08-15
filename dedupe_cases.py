#!/usr/bin/env python3
"""
dedupe_cases.py

One-off migration for cases_auto.json: collapses duplicate rows that were
saved before merge_matches() started grouping multiple tracked people on
the same case into a single row (see causelist_core.PARSER_VERSION
"4-grouped-people"). Old data has one row per (case, person) pair; this
merges rows that share the same (date, court, primary case id) into one
row with a combined "people" list, exactly like a live run would now.

Usage:
    python dedupe_cases.py            # updates cases_auto.json in place
                                       # (writes cases_auto.json.bak first)
    python dedupe_cases.py --dry-run  # report what would change, no writes
    python dedupe_cases.py --file path/to/other.json
"""
import argparse
import json
import shutil

from causelist_core import primary_case_id

DEFAULT_FILE = "cases_auto.json"


def dedupe(matches):
    for item in matches:
        if "people" not in item:
            item["people"] = [item["person"]] if item.get("person") else []

    def key(r):
        return (r.get("date"), r.get("court"), primary_case_id(r.get("caseNo")))

    deduped = []
    index = {}
    merged_count = 0
    for r in matches:
        k = key(r)
        if k in index:
            target = index[k]
            people = list(target.get("people", []))
            for p in r.get("people", []):
                if p not in people:
                    people.append(p)
            target["people"] = people
            target["person"] = ", ".join(people)
            if not target.get("sr") and r.get("sr"):
                target["sr"] = r["sr"]
            merged_count += 1
        else:
            index[k] = r
            deduped.append(r)
    return deduped, merged_count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", default=DEFAULT_FILE, help="path to the cases JSON file")
    parser.add_argument("--dry-run", action="store_true", help="report only, don't write")
    args = parser.parse_args()

    with open(args.file, "r", encoding="utf-8") as f:
        matches = json.load(f)

    deduped, merged_count = dedupe(matches)

    print(f"Read {len(matches)} row(s) from {args.file}")
    print(f"Merged {merged_count} duplicate row(s) into existing entries")
    print(f"Result: {len(deduped)} row(s) ({len(matches) - len(deduped)} fewer)")

    if args.dry_run:
        print("Dry run — nothing written.")
        return

    if merged_count == 0:
        print("Nothing to merge — leaving file untouched.")
        return

    backup_path = args.file + ".bak"
    shutil.copyfile(args.file, backup_path)
    print(f"Backed up original to {backup_path}")

    with open(args.file, "w", encoding="utf-8") as f:
        json.dump(deduped, f, indent=2, ensure_ascii=False)
    print(f"Wrote deduped data to {args.file}")


if __name__ == "__main__":
    main()
