"""
Order monitor for the J&K High Court (Srinagar Wing) on hcservices.ecourts.gov.in.

Reads the cases the causelist watcher has already found (cases_auto.json --
never modified here) and, for each distinct case:

  1. Links it once to its eCourts record (cino). That needs a Case Status >
     Case Number search, which is captcha-gated; the captcha is read by the
     ONNX model in captcha_solver.py. A linked case never needs this again.
  2. Reads the case-history page (no captcha) and downloads any order PDF
     not seen before, skipping byte-identical re-uploads (SHA-256).
  3. Extracts the full text of each new PDF (pdfplumber; Tesseract OCR as a
     fallback for scanned pages, when it's installed).

Everything is recorded in orders_index.json, with the PDFs and .txt files
under orders/<case>/. orders_status.json summarises the latest run for the
dashboard.
"""
import argparse
import hashlib
import io
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pdfplumber
import requests
from bs4 import BeautifulSoup

import ecourts_client as ec

HERE = os.path.dirname(os.path.abspath(__file__))
CASES_FILE = os.path.join(HERE, "cases_auto.json")
INDEX_FILE = os.path.join(HERE, "orders_index.json")
STATUS_FILE = os.path.join(HERE, "orders_status.json")
ORDERS_DIR = os.path.join(HERE, "orders")
LOG_FILE = os.path.join(HERE, "orders.log")

BENCH = "srinagar"            # the causelist watcher only reads the Srinagar lists
REQUEST_GAP = 1.5             # seconds between portal requests -- keep the load light
MAX_LINKS_PER_RUN = 120       # captcha-gated searches per run
NOT_FOUND_RETRY = timedelta(days=14)
EXCERPT_LEN = 400

log = logging.getLogger("orders")

# "WP(C) 1394/2024", "CRM(M) 333/2022", "Arb P 12/2026", "Mac App 3/2025".
# Applications are written "CM(1095/2025)" -- number inside the brackets -- so
# they don't match. Text in [...] names an earlier/parent case and is dropped.
CASE_TOKEN = re.compile(r"(?<![A-Za-z0-9(])([A-Z][A-Za-z]*(?:\([A-Za-z]+\))?(?: [A-Z][a-z]*)?)\s+(\d{1,6})\s*/\s*(\d{4})\b")
NOT_CASE_TYPES = {"CAVEAT", "COURTNO"}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def norm_type(t):
    return re.sub(r"[^A-Z0-9()]", "", t.upper())


def case_key(ctype, number, year):
    return f"{ctype} {int(number)}/{year}"


def case_slug(key):
    return re.sub(r"[^A-Za-z0-9]+", "_", key).strip("_")


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def cases_in_entry(case_no_text):
    """The main case and any connected (c/w) cases named in a causelist entry."""
    text = re.sub(r"\[[^\]]*\]", " ", case_no_text)
    out = []
    for m in CASE_TOKEN.finditer(text):
        ctype, number, year = m.group(1), m.group(2), m.group(3)
        if norm_type(ctype) in NOT_CASE_TYPES:
            continue
        out.append((ctype, int(number), year))
    return out


def tracked_cases(matches):
    """{key: {type, number, year, parties}} for every distinct case."""
    found = {}
    for m in matches:
        for ctype, number, year in cases_in_entry(m.get("caseNo", "")):
            key = case_key(ctype, number, year)
            found.setdefault(key, {"type": ctype, "number": number, "year": year,
                                   "title": m.get("caseName", "")})
    return found


# ---- portal access ---------------------------------------------------------

class Portal:
    """One requests session plus the case-type table, with a polite gap
    between calls."""

    def __init__(self, manual_captcha=False):
        self.session = ec.new_session()
        self.manual = manual_captcha
        self._types = None
        self._last = 0.0

    def wait(self):
        gap = time.monotonic() - self._last
        if gap < REQUEST_GAP:
            time.sleep(REQUEST_GAP - gap)
        self._last = time.monotonic()

    def type_code(self, ctype):
        if self._types is None:
            self.wait()
            raw = ec.fetch_case_types(self.session, BENCH)
            self._types = {norm_type(k): v for k, v in raw.items()}
        return self._types.get(norm_type(ctype))

    def search(self, code, number, year):
        self.wait()
        return ec.search_by_case_number(
            self.session, code, number, year, bench=BENCH,
            tmp_captcha_path=os.path.join(HERE, "downloads", "_captcha.png"),
            auto=not self.manual,
        )

    def history(self, rec):
        self.wait()
        data = {
            "court_code": rec["court_code"], "state_code": ec.STATE_CODE,
            "court_complex_code": rec["court_code"], "case_no": rec["case_no"],
            "cino": rec["cino"], "appFlag": "",
        }
        r = ec._post_with_retry(self.session, ec.QRY + "o_civil_case_history.php",
                                data=data, headers=ec._ajax_headers())
        return r.text

    def pdf(self, url):
        self.wait()
        r = ec._get_with_retry(self.session, url, headers={"Referer": ec.MAIN_PAGE})
        return r.content.lstrip(b"\xef\xbb\xbf")


def parse_orders(history_html):
    """Rows of the 'Orders' table on a case-history page:
    [{no, date (ISO), judge, url, token}]. The token (the PDF's encrypted
    filename parameter) is stable across sessions and identifies the order."""
    soup = BeautifulSoup(history_html, "html.parser")
    table = soup.find("table", class_="order_table")
    if table is None:
        return []
    out = []
    for tr in table.find_all("tr"):
        a = tr.find("a", href=lambda h: h and "display_pdf.php" in h)
        if not a:
            continue
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        href = a["href"].strip()
        url = ec.BASE + "/" + href.lstrip("/")
        token = (parse_qs(urlparse(url).query).get("filename") or [href])[0]
        date = ""
        if len(cells) > 3:
            dm = re.match(r"(\d{2})-(\d{2})-(\d{4})", cells[3])
            if dm:
                date = f"{dm.group(3)}-{dm.group(2)}-{dm.group(1)}"
        no = re.sub(r"\D", "", cells[0]) if cells else ""
        out.append({
            "no": int(no) if no else None,
            "date": date,
            "judge": re.sub(r"\s+", " ", cells[2]) if len(cells) > 2 else "",
            "url": url,
            "token": token,
        })
    return out


# ---- text extraction --------------------------------------------------------

def extract_text(pdf_bytes):
    """Returns (text, pages, used_ocr). Pages with no text layer are OCR'd
    when pytesseract + the tesseract binary are available."""
    parts, used_ocr = [], False
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        pages = len(pdf.pages)
        for page in pdf.pages:
            t = (page.extract_text() or "").strip()
            if len(t) < 20:
                o = _ocr_page(page)
                if o:
                    t, used_ocr = o, True
            parts.append(t)
    return "\n\n".join(parts).strip(), pages, used_ocr


def _ocr_page(page):
    try:
        import pytesseract
        img = page.to_image(resolution=300).original
        return pytesseract.image_to_string(img).strip()
    except Exception as e:  # not installed, or tesseract binary missing
        log.debug("OCR unavailable: %s", e)
        return ""


# ---- the run -----------------------------------------------------------------

def link_case(portal, key, entry):
    code = portal.type_code(entry["type"])
    if not code:
        entry.update(status="unknown_type", error=f"case type {entry['type']!r} not on the portal's list")
        return False
    results = portal.search(code, entry["number"], entry["year"])
    label = f"{entry['type']}/{entry['number']}/{entry['year']}"
    hit = next((r for r in results if norm_type(r["case_label"]) == norm_type(label)), None)
    hit = hit or (results[0] if len(results) == 1 else None)
    if not hit or not hit.get("cino"):
        entry.update(status="not_found", error="no matching record on the portal")
        return False
    entry.update(
        status="linked", error="", cino=hit["cino"], case_no=hit["case_no"],
        court_code=hit["court_code"] or ec.BENCH_CODES[BENCH], linked_at=now_iso(),
        parties=" vs ".join(p for p in (hit["petitioner"], hit["respondent"]) if p),
    )
    return True


def needs_link(entry, now):
    st = entry.get("status")
    if st == "linked":
        return False
    if st == "not_found" and entry.get("last_attempt"):
        return now - datetime.fromisoformat(entry["last_attempt"]) >= NOT_FOUND_RETRY
    return True


def check_case(portal, key, entry, download=True):
    """Downloads new orders for one linked case. Returns the new order records."""
    rows = parse_orders(portal.history(entry))
    entry["last_checked"] = now_iso()
    orders = entry.setdefault("orders", [])
    seen_tokens = {o["token"] for o in orders}
    by_hash = {o["sha256"]: o for o in orders if o.get("sha256") and not o.get("duplicate_of")}
    new = []
    slug = case_slug(key)
    for row in rows:
        if row["token"] in seen_tokens:
            continue
        rec = {k: row[k] for k in ("no", "date", "judge", "token")}
        rec["fetched_at"] = now_iso()
        if not download:  # report only; left unseen so a later run downloads it
            new.append(rec)
            continue
        data = portal.pdf(row["url"])
        if not data.startswith(b"%PDF"):
            log.warning("%s order %s: not a PDF (%d bytes), will retry next run", key, row["no"], len(data))
            continue
        digest = hashlib.sha256(data).hexdigest()
        rec["sha256"] = digest
        if digest in by_hash:
            rec["duplicate_of"] = by_hash[digest]["no"]
            orders.append(rec)
            seen_tokens.add(row["token"])
            log.info("%s order %s: same PDF as order %s, not stored again", key, row["no"], rec["duplicate_of"])
            continue
        stem = f"{(row['no'] or 0):03d}_{row['date'] or 'undated'}"
        rel_pdf = f"orders/{slug}/{stem}.pdf"
        rel_txt = f"orders/{slug}/{stem}.txt"
        os.makedirs(os.path.join(HERE, "orders", slug), exist_ok=True)
        with open(os.path.join(HERE, rel_pdf), "wb") as f:
            f.write(data)
        try:
            text, pages, used_ocr = extract_text(data)
        except Exception as e:
            log.warning("%s order %s: text extraction failed: %s", key, row["no"], e)
            text, pages, used_ocr = "", 0, False
        with open(os.path.join(HERE, rel_txt), "w", encoding="utf-8") as f:
            f.write(text)
        rec.update(pdf=rel_pdf, text=rel_txt, pages=pages, chars=len(text), ocr=used_ocr,
                   bytes=len(data), excerpt=re.sub(r"\s+", " ", text)[:EXCERPT_LEN])
        if not text:
            rec["no_text"] = True
        orders.append(rec)
        seen_tokens.add(row["token"])
        by_hash[digest] = rec
        new.append(rec)
    orders.sort(key=lambda o: (o.get("no") or 0))
    return new


def run(only=None, download=True, manual_captcha=False):
    matches = load_json(CASES_FILE, [])
    index = load_json(INDEX_FILE, {})
    cases = index.setdefault("cases", {})
    now = datetime.now(timezone.utc)

    tracked = tracked_cases(matches)
    if only:
        tracked = {k: v for k, v in tracked.items() if norm_type(k) == norm_type(only)}
        if not tracked:
            log.error("No tracked case matches %r", only)
            return 1
    for key, info in tracked.items():
        entry = cases.setdefault(key, {"status": "new"})
        entry.update(type=info["type"], number=info["number"], year=info["year"])
        entry.setdefault("title", info["title"])

    status = {"last_run": now_iso(), "ok": True, "problem": None,
              "linked_now": [], "link_failures": [], "new_orders": [], "errors": []}
    try:
        portal = Portal(manual_captcha=manual_captcha)
    except requests.RequestException as e:
        log.error("Could not reach hcservices.ecourts.gov.in: %s", e)
        status.update(ok=False, problem={"kind": "site_unreachable", "message": str(e)})
        save_json(STATUS_FILE, finish_status(status, cases))
        return 0

    # 1. link cases we don't have a cino for yet
    links = 0
    for key in sorted(tracked):
        entry = cases[key]
        if not needs_link(entry, now):
            continue
        if links >= MAX_LINKS_PER_RUN:
            log.info("Link limit reached for this run; the rest are linked next run")
            break
        links += 1
        entry["last_attempt"] = now_iso()
        try:
            if link_case(portal, key, entry):
                log.info("Linked %s -> %s", key, entry["cino"])
                status["linked_now"].append(key)
            else:
                log.info("Could not link %s: %s", key, entry.get("error"))
                status["link_failures"].append({"case": key, "why": entry.get("error")})
        except ec.InvalidCaptcha:
            entry.update(status="link_failed", error="captcha not accepted after several tries")
            status["link_failures"].append({"case": key, "why": entry["error"]})
        except (ec.EcourtsError, requests.RequestException) as e:
            entry.update(status="link_failed", error=str(e)[:200])
            status["link_failures"].append({"case": key, "why": entry["error"]})
        save_json(INDEX_FILE, index)  # keep progress if the run is cut short

    # 2. check every linked case for new orders
    for key in sorted(tracked):
        entry = cases[key]
        if entry.get("status") != "linked":
            continue
        try:
            for rec in check_case(portal, key, entry, download=download):
                status["new_orders"].append({"case": key, "no": rec.get("no"), "date": rec.get("date"),
                                             "pdf": rec.get("pdf")})
                log.info("New order: %s #%s (%s)", key, rec.get("no"), rec.get("date"))
        except (ec.EcourtsError, requests.RequestException) as e:
            log.warning("Could not check %s: %s", key, e)
            status["errors"].append({"case": key, "why": str(e)[:200]})
        save_json(INDEX_FILE, index)

    index["updated"] = now_iso()
    save_json(INDEX_FILE, index)
    linked = sum(1 for k in tracked if cases[k].get("status") == "linked")
    if tracked and linked == 0 and status["link_failures"]:
        status.update(ok=False, problem={"kind": "link_failed",
                                         "message": "no case could be linked to its eCourts record"})
    save_json(STATUS_FILE, finish_status(status, {k: cases[k] for k in tracked}))
    log.info("Done: %d/%d cases linked, %d new orders", linked, len(tracked), len(status["new_orders"]))
    return 0


def finish_status(status, cases):
    status["cases_total"] = len(cases)
    status["cases_linked"] = sum(1 for c in cases.values() if c.get("status") == "linked")
    status["orders_total"] = sum(1 for c in cases.values() for o in c.get("orders", []) if not o.get("duplicate_of"))
    status["unlinked"] = sorted(
        ({"case": k, "status": c.get("status"), "why": c.get("error", "")} for k, c in cases.items()
         if c.get("status") != "linked"), key=lambda x: x["case"])
    return status


def main(argv=None):
    p = argparse.ArgumentParser(description="Download new J&K High Court orders for every tracked case.")
    p.add_argument("--case", help='only this case, e.g. "WP(C) 1394/2024"')
    p.add_argument("--no-download", action="store_true", help="list new orders without downloading them")
    p.add_argument("--manual-captcha", action="store_true", help="type captchas yourself instead of using the model")
    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_FILE, encoding="utf-8")],
    )
    return run(only=args.case, download=not args.no_download, manual_captcha=args.manual_captcha)


if __name__ == "__main__":
    sys.exit(main())
