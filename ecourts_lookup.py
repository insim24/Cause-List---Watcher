#!/usr/bin/env python3
"""
Look up cases by advocate name on the eCourts High Court Services portal
(scoped here to the J&K High Court, Srinagar/Jammu wings), and optionally
download any order/judgement PDFs attached to them.

The portal gates every search behind an image captcha. This tool fetches
that captcha image, opens it for you to read, and asks you to type it in --
it never solves or bypasses the captcha itself, it just automates everything
around that one manual step.

Usage:
    python ecourts_lookup.py advocate "Advocate Name" [--bench srinagar|jammu] [--status Pending|Disposed|Both]
"""
import argparse
import os
import sys

import ecourts_client as ec

HERE = os.path.dirname(os.path.abspath(__file__))
ORDERS_DIR = os.path.join(HERE, "downloads", "orders")
TMP_CAPTCHA = os.path.join(HERE, "downloads", "_captcha.png")


def _safe_filename(text):
    return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_") or "case"


def cmd_advocate(args):
    os.makedirs(os.path.dirname(TMP_CAPTCHA), exist_ok=True)
    session = ec.new_session()
    try:
        cases = ec.search_by_advocate(
            session, args.name, bench=args.bench, status=args.status,
            tmp_captcha_path=TMP_CAPTCHA,
        )
    except ec.InvalidCaptcha:
        print("Too many invalid captcha attempts, giving up.")
        sys.exit(1)
    except ec.EcourtsError as e:
        print(f"eCourts error: {e}")
        sys.exit(1)

    if not cases:
        print("No cases found.")
        return

    print(f"\n{len(cases)} case(s) found for '{args.name}':\n")
    for i, c in enumerate(cases, 1):
        vs = f"{c['petitioner']} vs {c['respondent']}" if c["respondent"] else c["petitioner"]
        print(f"[{i}] {c['case_label']}  ({c['establishment']})\n     {vs}")

    if args.no_orders:
        return

    sel = input("\nEnter case number(s) to fetch orders for (e.g. 1,3), or blank to skip: ").strip()
    if not sel:
        return

    os.makedirs(ORDERS_DIR, exist_ok=True)
    chosen = [int(t) - 1 for t in sel.split(",") if t.strip().isdigit()]
    for i in chosen:
        if not (0 <= i < len(cases)):
            continue
        case = cases[i]
        print(f"\nFetching order list for {case['case_label']}...")
        try:
            orders = ec.get_case_orders(session, case)
        except ec.EcourtsError as e:
            print(f"  Could not fetch case history: {e}")
            continue
        if not orders:
            print("  No order/judgement PDFs listed for this case.")
            continue
        for j, o in enumerate(orders, 1):
            print(f"  [{j}] {o['label']}")
        pick = input("  Download which? (numbers / 'all' / blank to skip): ").strip()
        if not pick:
            continue
        indices = range(len(orders)) if pick.lower() == "all" else [
            int(p) - 1 for p in pick.split(",") if p.strip().isdigit()
        ]
        stem = _safe_filename(case["case_label"])
        for idx in indices:
            if 0 <= idx < len(orders):
                dest = os.path.join(ORDERS_DIR, f"{stem}_{idx + 1}.pdf")
                ec.download_pdf(session, orders[idx]["url"], dest)
                print(f"  Saved {dest}")


def main():
    parser = argparse.ArgumentParser(
        description="Search eCourts Case Status by advocate name and fetch order/judgement PDFs (J&K High Court)."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_adv = sub.add_parser("advocate", help="Search Case Status by advocate name")
    p_adv.add_argument("name", help="Advocate name (min 3 characters, as accepted by the portal)")
    p_adv.add_argument("--bench", choices=["srinagar", "jammu"], default="srinagar")
    p_adv.add_argument("--status", choices=["Pending", "Disposed", "Both"], default="Both")
    p_adv.add_argument("--no-orders", action="store_true",
                        help="Skip the order/judgement download prompt after listing cases")
    p_adv.set_defaults(func=cmd_advocate)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
