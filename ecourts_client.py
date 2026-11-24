"""
Client for the eCourts High Court Services portal (hcservices.ecourts.gov.in),
scoped to the High Court of Jammu & Kashmir and Ladakh (state_code=12).

Every search on that portal is gated behind a session-bound image captcha
(the classic PHP "Securimage" library -- a real server-rendered image, not a
client-side puzzle). Searches can either open the image for a human to read
(solve_captcha_interactively) or read it with the ONNX model in
captcha_solver.py (solve_captcha_automatically, auto=True). Case history and
order PDFs aren't captcha-gated once a case's cino is known.

The request shapes below (field names, endpoints, response formats) were
reverse engineered from the portal's own inline JavaScript (funShowRecords /
displayRecordsJson / viewHistory in main.php) -- there is no official API.
"""
import json
import os
import re
import time

import requests
from bs4 import BeautifulSoup

BASE = "https://hcservices.ecourts.gov.in/hcservices"
MAIN_PAGE = BASE + "/main.php"
QRY = BASE + "/cases_qry/"
CAPTCHA_IMG = BASE + "/securimage/securimage_show.php"

STATE_CODE = "12"  # High Court of Jammu and Kashmir and Ladakh
BENCH_CODES = {"jammu": "1", "srinagar": "2"}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class InvalidCaptcha(Exception):
    """The server rejected the captcha text we sent."""


class EcourtsError(Exception):
    """The server returned an error other than a bad captcha."""


def new_session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    _get_with_retry(s, MAIN_PAGE)  # establishes the HCSERVICES_SESSID cookie
    return s


def _get_with_retry(session, url, attempts=3, **kw):
    last = None
    for _ in range(attempts):
        try:
            r = session.get(url, timeout=30, **kw)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            time.sleep(1)
    raise last


def _post_with_retry(session, url, attempts=3, **kw):
    """The portal drops the occasional request outright (RST, no response) --
    seen consistently in testing on the very first POST after a fresh
    session, unrelated to the data sent. A short retry clears it."""
    last = None
    for _ in range(attempts):
        try:
            r = session.post(url, timeout=30, **kw)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            time.sleep(1)
    raise last


def _ajax_headers():
    return {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": MAIN_PAGE,
        "Origin": "https://hcservices.ecourts.gov.in",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "*/*",
    }


def fetch_captcha_image(session):
    """Returns the raw PNG bytes of the current captcha, tied to this session."""
    r = _get_with_retry(session, CAPTCHA_IMG, params={"t": str(time.time())})
    return r.content


def solve_captcha_interactively(session, tmp_path):
    """Saves the captcha image, opens it in the OS default viewer, and asks
    the person running this script to type what they see. A human solves it
    every time -- nothing here reads the image."""
    img = fetch_captcha_image(session)
    with open(tmp_path, "wb") as f:
        f.write(img)
    try:
        os.startfile(tmp_path)  # Windows only
    except AttributeError:
        print(f"Open this image to read the captcha: {tmp_path}")
    return input("Enter the captcha text shown in the image: ").strip()


def solve_captcha_automatically(session):
    """Fetches a fresh captcha for this session and reads it with the ONNX
    model in captcha_solver.py. The portal's captchas are always 6 lowercase
    letters/digits, so anything else is a misread -- grab a new image rather
    than spend a request on it."""
    import captcha_solver
    for _ in range(5):
        text, conf = captcha_solver.solve(fetch_captcha_image(session))
        if re.fullmatch(r"[a-z0-9]{6}", text):
            return text
        time.sleep(1)
    return text


def _run_with_captcha_retries(session, attempt_fn, tmp_captcha_path=None, max_attempts=4, auto=False):
    """Calls attempt_fn(captcha_text) -> result, refreshing the captcha image
    and re-solving whenever the server reports 'Invalid Captcha'. With
    auto=True the model reads the captcha; otherwise a human is asked."""
    for attempt in range(1, max_attempts + 1):
        if auto:
            code = solve_captcha_automatically(session)
        else:
            code = solve_captcha_interactively(session, tmp_captcha_path)
        try:
            return attempt_fn(code)
        except InvalidCaptcha:
            print(f"Invalid captcha (attempt {attempt}/{max_attempts}) -- fetching a new one.")
            time.sleep(2)
    raise InvalidCaptcha(f"Gave up after {max_attempts} attempts")


def _parse_case_status_json(raw):
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise EcourtsError(f"Unexpected response from the portal: {raw[:200]!r}")
    if data.get("con") == "Invalid Captcha":
        raise InvalidCaptcha()
    if data.get("Error"):
        raise EcourtsError(data["Error"])
    return data


def _flatten_case_status(data):
    """Results come back grouped per court establishment, each as its own
    JSON-encoded string in data['con']; this flattens them into one list."""
    out = []
    con = data.get("con") or []
    court_codes = data.get("court_code") or []
    court_names = data.get("courtNameArr") or []
    for idx, chunk in enumerate(con):
        if not chunk:
            continue
        try:
            rows = json.loads(chunk)
        except (json.JSONDecodeError, TypeError):
            continue
        est_court_code = court_codes[idx] if idx < len(court_codes) else ""
        est_name = court_names[idx] if idx < len(court_names) else ""
        for row in rows:
            label = "/".join(
                str(row.get(k, "")) for k in ("type_name", "case_no2", "case_year") if row.get(k)
            )
            out.append({
                "case_no": row.get("case_no", ""),
                "case_label": label,
                "petitioner": row.get("pet_name", ""),
                "respondent": row.get("res_name", ""),
                "cino": row.get("cino", ""),
                "court_code": row.get("court_code") or est_court_code,
                "establishment": est_name,
                "raw": row,
            })
    return out


def search_by_advocate(session, name, bench="srinagar", status="Both",
                        tmp_captcha_path="captcha.png", max_attempts=4):
    """Case Status > Search by Advocate > Advocate Name. `status` is one of
    Pending / Disposed / Both. Returns a list of case dicts."""
    bench_code = BENCH_CODES[bench]

    def attempt(captcha):
        data = {
            "court_code": bench_code,
            "state_code": STATE_CODE,
            "court_complex_code": bench_code,
            "caseStatusSearchType": "CSAdvName",
            "advocate_name": name,
            "search_type": "1",
            "f": status,
            "captcha": captcha,
        }
        r = _post_with_retry(
            session,
            QRY + "index_qry.php",
            params={"action_code": "showRecords"},
            data=data,
            headers=_ajax_headers(),
        )
        return _flatten_case_status(_parse_case_status_json(r.text))

    return _run_with_captcha_retries(session, attempt, tmp_captcha_path, max_attempts)


def fetch_case_types(session, bench="srinagar"):
    """Case Status > Case Number needs the portal's numeric case-type code.
    Returns {abbreviation: code}, e.g. {'WP(C)': '134', ...}. The raw list is
    '0~Select case type#134~WP(C)(WRIT PETITION (CIVIL))-134#...'."""
    bench_code = BENCH_CODES[bench]
    r = _post_with_retry(
        session,
        QRY + "index_qry.php",
        params={"action_code": "fillCaseType"},
        data={"court_code": bench_code, "state_code": STATE_CODE},
        headers=_ajax_headers(),
    )
    text = r.text.lstrip("﻿")
    if text[:5].upper() == "ERROR":
        raise EcourtsError(f"Could not load case types: {text[:200]!r}")
    types = {}
    for item in text.split("#"):
        code, _, name = item.partition("~")
        if not code or code == "0" or not name:
            continue
        # Drop the trailing "-<code>" and the "(long description)" suffix;
        # the abbreviation can itself contain parentheses, e.g. "WP(C)".
        name = re.sub(r"-\d+$", "", name.strip())
        depth, cut = 0, len(name)
        for i in range(len(name) - 1, -1, -1):
            if name[i] == ")":
                depth += 1
            elif name[i] == "(":
                depth -= 1
                if depth == 0:
                    cut = i
                    break
        types.setdefault(name[:cut].strip(), code.strip())
    return types


def search_by_case_number(session, case_type_code, number, year, bench="srinagar",
                          tmp_captcha_path="captcha.png", max_attempts=4, auto=False):
    """Case Status > Case Number. Returns a list of case dicts (normally one)."""
    bench_code = BENCH_CODES[bench]

    def attempt(captcha):
        data = {
            "court_code": bench_code,
            "state_code": STATE_CODE,
            "court_complex_code": bench_code,
            "caseStatusSearchType": "CScaseNumber",
            "captcha": captcha,
            "case_type": case_type_code,
            "case_no": str(number),
            "rgyear": str(year),
            "caseNoType": "new",
            "displayOldCaseNo": "NO",
        }
        r = _post_with_retry(
            session,
            QRY + "index_qry.php",
            params={"action_code": "showRecords"},
            data=data,
            headers=_ajax_headers(),
        )
        raw = r.text.lstrip("﻿")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = None
        # "Record not found" comes back as an Error rather than an empty list
        if isinstance(parsed, dict) and parsed.get("Error") and "not found" in str(parsed["Error"]).lower():
            return []
        return _flatten_case_status(_parse_case_status_json(raw))

    return _run_with_captcha_retries(session, attempt, tmp_captcha_path, max_attempts, auto=auto)


def get_case_orders(session, case):
    """Fetches the case-history page for a case dict returned by
    search_by_advocate() and returns any order/judgement PDF links on it as
    [{'label': ..., 'url': ...}]. No captcha is needed for this step -- the
    portal only gates the initial search, not viewing a result you already
    have permission to see.

    The PDF endpoint needs cino/state_code/court_code query params (it uses
    state_code to pick which state's database to query) in addition to
    filename/caseno/cCode -- passing only the latter three gets you a PHP
    stack trace instead of a PDF, so this uses the full href verbatim rather
    than re-building it from a subset of fields."""
    data = {
        "court_code": case["court_code"],
        "state_code": STATE_CODE,
        "court_complex_code": case["court_code"],
        "case_no": case["case_no"],
        "cino": case["cino"],
        "appFlag": "",
    }
    r = _post_with_retry(
        session,
        QRY + "o_civil_case_history.php",
        data=data,
        headers=_ajax_headers(),
    )
    soup = BeautifulSoup(r.text, "html.parser")
    orders = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if "display_pdf.php" not in href:
            continue
        orders.append({
            "label": a.get_text(strip=True) or href,
            "url": BASE + "/" + href.lstrip("/"),
        })
    return orders


def download_pdf(session, url, dest_path):
    r = _get_with_retry(session, url, headers={"Referer": MAIN_PAGE})
    content = r.content
    if content.startswith(b"\xef\xbb\xbf"):  # stray UTF-8 BOM the portal prepends
        content = content[3:]
    with open(dest_path, "wb") as f:
        f.write(content)
    return dest_path
