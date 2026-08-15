"""
Core parsing helpers for the J&K High Court (Srinagar Wing) causelist watcher.

The real cause list PDFs are a genuine 4-column table (Sr. No. | Case No. |
Case Name | Advocate), each column wrapping independently across lines, with
a header block per page giving the date, bench type (SB/DB), court number,
and presiding judge. This reads that structure directly rather than
guessing from flowing text.
"""
import re
import statistics
from collections import Counter
from urllib.parse import urljoin

BASE = "https://jkhighcourt.nic.in"
CAUSELIST_PAGE = BASE + "/causelistk.php"

# Bump this whenever extraction/parsing logic changes materially. The watcher
# stores this alongside each file's hash in manifest.json, so a code update
# forces re-parsing even of files whose content hasn't changed — otherwise a
# PDF fetched once under old, buggy parsing logic would stay wrong forever,
# since "unchanged since last run" would keep skipping it.
PARSER_VERSION = "4-grouped-people"

PRIMARY_CASE_RE = re.compile(r"[A-Za-z()/\s]{2,20}?\d{1,6}/\d{4}")


def primary_case_id(case_no):
    """Reduces a possibly multi-line, multi-reference case number string
    down to its first real case reference, normalized for comparison —
    used as the identity for dedup, since the exact concatenated text can
    vary slightly between source PDFs (daywise vs entire causelist) even
    for the literal same case."""
    m = PRIMARY_CASE_RE.search(case_no or "")
    text = m.group(0) if m else (case_no or "")
    return re.sub(r"\s+", " ", text).strip().upper()

COURT_RE = re.compile(r"court\s*no\.?\s*[:\-]?\s*([0-9]{1,3}|[ivxlcdm]{1,6})\b", re.I)
BENCH_RE = re.compile(r"^\W*hon'?ble\s+.*justice.*$", re.I)
BENCH_TYPE_RE = re.compile(r"bench\s*no\.?\s*:?\s*([A-Za-z]{1,4}-[IVXLCDM0-9]+)", re.I)
LIST_TYPE_RE = re.compile(r"(SUPPLEMENTARY[-\s]?\d*|REGULAR)\s*CAUSE\s?LIST", re.I)
HEADER_DATE_RE = re.compile(r"CAUSE\s?LIST\s+FOR\s+\w+\s*\(\s*(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})", re.I)
DATE_RE = re.compile(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})")
FNAME_DATE_RE = re.compile(r"(\d{2})[._-]?(\d{2})[._-]?(\d{4})")
SR_CHUNK_RE = re.compile(r"^\d{1,4}[.\)]?$")


def normalize_href(href):
    """Fix the site's Windows-style backslashed paths and spaces into a real URL."""
    href = href.replace("\\", "/")
    href = href.replace(" ", "%20")
    if href.lower().startswith("http"):
        return href
    return urljoin(BASE + "/", href.lstrip("/"))


def classify_link(href, text):
    low = href.lower()
    if "entirelist" in low:
        kind = "entire"
    elif "rjcourt" in low:
        kind = "registrar"
    elif "supplementary" in low or "supplementary" in text.lower():
        kind = "supplementary"
    elif re.search(r"causelist_\d{8}\.pdf", low):
        kind = "daywise"
    else:
        kind = "other"

    date_guess = ""
    m = re.search(r"causelist_(\d{2})(\d{2})(\d{4})\.pdf", low)
    if m:
        date_guess = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    else:
        m2 = DATE_RE.search(text)
        if m2:
            dd, mm, yyyy = m2.group(1).zfill(2), m2.group(2).zfill(2), m2.group(3)
            date_guess = f"{yyyy}-{mm}-{dd}"
    return kind, date_guess


def find_causelist_links(html):
    """Extract cause-list PDF links from the causelistk.php page HTML."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.lower().endswith(".pdf"):
            continue
        if not re.search(r"causelist|entirelist|rjcourt", href, re.I):
            continue
        text = a.get_text(strip=True)
        kind, date_guess = classify_link(href, text)
        links.append({
            "text": text,
            "href": href,
            "url": normalize_href(href),
            "type": kind,
            "date": date_guess,
        })
    seen = set()
    uniq = []
    for l in links:
        if l["url"] not in seen:
            seen.add(l["url"])
            uniq.append(l)
    return uniq


def build_people(cfg):
    """Turns config.json into a normalized list of
    [{'person': <display name>, 'terms': [<name>, <alias>, ...]}, ...]
    Supports both:
      - new format: {"people": [{"name": "...", "aliases": [...]}, ...]}
      - old format: {"name": "...", "aliases": [...]}   (treated as one person)
    """
    people_cfg = cfg.get("people")
    if people_cfg:
        out = []
        for p in people_cfg:
            terms = [p.get("name", "")] + list(p.get("aliases", []))
            terms = [t.strip() for t in terms if t and t.strip()]
            if terms:
                out.append({"person": p.get("name", terms[0]), "terms": terms})
        return out
    terms = [cfg.get("name", "")] + list(cfg.get("aliases", []))
    terms = [t.strip() for t in terms if t and t.strip()]
    return [{"person": cfg.get("name", terms[0] if terms else ""), "terms": terms}]


def guess_date_from_filename(name):
    m = FNAME_DATE_RE.search(name)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        if 1 <= int(mm) <= 12 and 1 <= int(dd) <= 31:
            return f"{yyyy}-{mm}-{dd}"
    return ""


# ---------------------------------------------------------------------------
# Word/line grouping
# ---------------------------------------------------------------------------

def _group_words_into_lines(words, tol=2.5):
    words = sorted(words, key=lambda w: (round(w["top"], 1), w["x0"]))
    lines, cur_top, cur = [], None, []
    for w in words:
        if cur_top is None or abs(w["top"] - cur_top) <= tol:
            cur.append(w)
            if cur_top is None:
                cur_top = w["top"]
        else:
            lines.append(sorted(cur, key=lambda x: x["x0"]))
            cur, cur_top = [w], w["top"]
    if cur:
        lines.append(sorted(cur, key=lambda x: x["x0"]))
    return lines


def _chunk_line(line_words, gap=12):
    """Groups words on a line into visually-separated chunks (a whitespace
    gap wider than `gap` starts a new chunk). Used only to *learn* column
    positions from clean, short cells (serial no. / case no.) — reconstruction
    itself is done word-by-word against the learned thresholds, since a long
    word can sit close enough to the next column to fool gap-based chunking."""
    if not line_words:
        return [], []
    chunks = [[line_words[0]]]
    for w in line_words[1:]:
        if w["x0"] - chunks[-1][-1]["x1"] > gap:
            chunks.append([w])
        else:
            chunks[-1].append(w)
    texts = [" ".join(x["text"] for x in c) for c in chunks]
    x0s = [c[0]["x0"] for c in chunks]
    return texts, x0s


def _classify_word(x0, thresholds):
    labels = ["sr", "caseNo", "caseName", "advocate"]
    idx = 0
    for i, t in enumerate(thresholds):
        if x0 >= t - 10:
            idx = i
    return labels[idx]


# ---------------------------------------------------------------------------
# Header metadata (date, bench type, court no., judge) — checked line by line
# ---------------------------------------------------------------------------

def _update_header_state(text, current):
    cm = COURT_RE.search(text)
    if cm:
        new_court = cm.group(1)
        if new_court != current["court"]:
            current["bench"] = ""  # genuinely a new court section, different judge
        current["court"] = new_court
    bm = BENCH_RE.match(text.strip())
    if bm:
        current["bench"] = text.strip()
    btm = BENCH_TYPE_RE.search(text)
    if btm:
        current["benchType"] = btm.group(1).upper()
    ltm = LIST_TYPE_RE.search(text)
    if ltm:
        current["listType"] = ltm.group(1).strip().title()
    dm = HEADER_DATE_RE.search(text)
    if dm:
        dd, mm, yyyy = dm.group(1).zfill(2), dm.group(2).zfill(2), dm.group(3)
        current["date"] = f"{yyyy}-{mm}-{dd}"


# ---------------------------------------------------------------------------
# Column learning — driven by where lines actually start, not by guessing
# which columns share a line. Real cause lists don't reliably put the case
# name on the same physical row as the serial number; what IS reliable is
# that each column's wrapped continuation lines always start at the same
# x-position, so the four true column starts are simply the four most
# common "first word of a line" x-positions in the whole document.
# ---------------------------------------------------------------------------

def _learn_column_thresholds(all_lines):
    votes = Counter()
    for lw in all_lines:
        if lw:
            votes[round(lw[0]["x0"] / 3) * 3] += 1
    if len(votes) < 4:
        return None
    top4 = sorted(x for x, _ in votes.most_common(4))
    return top4


def _classify_word(x0, thresholds):
    labels = ["sr", "caseNo", "caseName", "advocate"]
    idx = 0
    for i, t in enumerate(thresholds):
        if x0 >= t - 10:
            idx = i
    return labels[idx]


def _finalize_entry(e):
    for k in ("caseNo", "caseName", "advocate"):
        e[k] = re.sub(r"\s+", " ", e[k]).strip()
    e["snippet"] = "\n".join(x for x in [e["caseNo"], e["caseName"], e["advocate"]] if x)
    return e


def extract_entries_from_pdf(path, fallback_date=""):
    """Returns every case-table row found in the PDF (not yet filtered to
    any particular person), each tagged with the court/bench/date active on
    its page. This intentionally extracts everyone's cases, not just yours —
    matching against tracked names happens afterwards in match_people().

    Column positions are learned once from the whole document (they're a
    fixed template), and entries accumulate across page breaks rather than
    resetting per page, since a single case entry can run onto the next
    page in these lists."""
    import pdfplumber

    all_lines = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            if not words:
                continue
            all_lines.extend(_group_words_into_lines(words))

    if not all_lines:
        return []

    thresholds = _learn_column_thresholds(all_lines)
    if thresholds is None:
        return []

    current = {"court": "", "bench": "", "benchType": "", "listType": "Regular", "date": fallback_date}
    entries = []
    cur = None

    for lw in all_lines:
        if not lw:
            continue
        text = " ".join(w["text"] for w in lw)
        _update_header_state(text, current)

        first = lw[0]
        is_start = bool(SR_CHUNK_RE.match(first["text"])) and abs(first["x0"] - thresholds[0]) < 10
        if is_start:
            if cur:
                entries.append(_finalize_entry(cur))
            cur = {
                "sr": first["text"].rstrip(".)"),
                "caseNo": "", "caseName": "", "advocate": "",
                "court": current["court"], "bench": current["bench"],
                "benchType": current["benchType"], "listType": current["listType"],
                "date": current["date"] or fallback_date,
            }
            rest = lw[1:]
        else:
            if cur is None:
                continue
            rest = lw

        col_words = []
        for w in rest:
            col = _classify_word(w["x0"], thresholds)
            if col_words and col_words[-1][0] == col:
                col_words[-1][1].append(w["text"])
            else:
                col_words.append([col, [w["text"]]])
        for col, ws in col_words:
            if col in cur:
                cur[col] = (cur[col] + " " + " ".join(ws)).strip()

    if cur:
        entries.append(_finalize_entry(cur))
    return entries


def match_people(entries, people, source_name=""):
    """Checks each entry's advocate AND case-name text for tracked
    names/aliases (covers both use cases: tracking yourself as counsel, or
    as a named party). If more than one tracked person appears on the same
    case, returns ONE result listing all of them — not a duplicate row per
    person."""
    results = []
    for e in entries:
        haystack = (e.get("advocate", "") + " " + e.get("caseName", "")).lower()
        matched = [p["person"] for p in people if any(term and term.lower() in haystack for term in p["terms"])]
        if not matched:
            continue
        if not (e.get("caseNo") or e.get("caseName")):
            continue  # nothing identifiable about this row — likely a parsing artifact, not a real case
        results.append({
            "person": ", ".join(matched),
            "people": matched,
            "court": e.get("court", ""),
            "sr": e.get("sr", ""),
            "bench": e.get("bench", ""),
            "benchType": e.get("benchType", ""),
            "listType": e.get("listType", ""),
            "caseNo": e.get("caseNo", ""),
            "caseName": e.get("caseName", ""),
            "snippet": e.get("snippet", ""),
            "date": e.get("date", ""),
            "source": source_name,
        })
    return results
