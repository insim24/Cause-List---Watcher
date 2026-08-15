"""
display_board.py

Reads the High Court's live Digital Display Board (https://jkhc.gov.in/dis/),
which shows which item/serial number each court is *currently* calling, plus
any "mentioned matters" notices — the genuine real-time counterpart to the
cause list (which is only ever a schedule).

IMPORTANT — this module was built and tested only against the board's IDLE
state ("No Cases To Display"), since that's what was live at build time. The
*populated* state (an actual court actively hearing case N) has not been
observed yet, so the court-status parsing below is a best-effort guess at
the layout based on the page's static text ("Court Nos. which are not
listed are currently not in session" implies per-court rows when active).
If it turns out wrong once real data is seen, only WING_TABLE_RE / the
row-parsing logic here needs correcting — the rest of the pipeline doesn't
care about the internal shape, just the dict this returns.
"""
import re

DISPLAY_BOARD_URL = "https://jkhc.gov.in/dis/"

WING_NAMES = ["Srinagar Wing", "Jammu Wing"]
COURT_ROW_RE = re.compile(r"court\s*no\.?\s*[:\-]?\s*(\d+)\D+(\d+)", re.I)


def parse_display_board(html):
    """Returns {wing_name: {"idle": bool, "courts": [{"court": "5", "item": "23"}, ...],
    "raw_status_rows": [...], "messages": [{"id": "8", "text": "..."}]}}"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    text_blocks = soup.get_text("\n", strip=True).split("\n")

    result = {}
    wing_starts = []
    for i, line in enumerate(text_blocks):
        for wing in WING_NAMES:
            if line.strip().lower() == wing.lower():
                wing_starts.append((wing, i))

    for idx, (wing, start) in enumerate(wing_starts):
        end = wing_starts[idx + 1][1] if idx + 1 < len(wing_starts) else len(text_blocks)
        block = text_blocks[start + 1:end]

        # the last wing's block otherwise runs into page footer text
        for i, l in enumerate(block):
            if re.match(r"^(Note|Disclaimer)\s*:", l.strip(), re.I):
                block = block[:i]
                break

        try:
            messages_at = next(i for i, l in enumerate(block) if l.strip().lower() == "messages")
        except StopIteration:
            messages_at = len(block)

        status_lines = [l for l in block[:messages_at] if l.strip()]
        message_lines = [l for l in block[messages_at + 1:] if l.strip()]

        idle = any(l.strip().lower() == "no cases to display" for l in status_lines)
        courts = []
        if not idle:
            for l in status_lines:
                m = COURT_ROW_RE.search(l)
                if m:
                    courts.append({"court": m.group(1), "item": m.group(2)})

        messages = []
        i = 0
        while i < len(message_lines):
            l = message_lines[i].strip()
            if re.match(r"^(\d+|\*)$", l):
                msg_id = l
                text = message_lines[i + 1].strip() if i + 1 < len(message_lines) else ""
                if text:
                    messages.append({"id": msg_id, "text": text})
                    i += 2
                    continue
            i += 1

        result[wing] = {
            "idle": idle,
            "courts": courts,
            "raw_status_rows": status_lines if not idle and not courts else [],
            "messages": messages,
        }
    return result


def fetch_display_board(session, headers, timeout=20):
    resp = session.get(DISPLAY_BOARD_URL, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return parse_display_board(resp.text)
