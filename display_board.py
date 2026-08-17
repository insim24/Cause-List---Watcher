"""
display_board.py

Reads the High Court's live Digital Display Board (https://jkhc.gov.in/dis/),
which shows which item/serial number each court is *currently* calling, plus
any "mentioned matters" notices — the genuine real-time counterpart to the
cause list (which is only ever a schedule).

Each wing renders as a <div class="wing"><table class="my_table"> with a
title row, a COURT NO / CORAM / SR NO header row, then either data rows or a
single "No Cases To Display" row, then a "Messages" title row and id/text
rows. Note that the court number lives inside a hidden
<input name="roomno" value="..."> submit button, not as plain text next to
"Court No" — a flat get_text() pass can't see it, so this walks the table
DOM directly instead.
"""
import re

DISPLAY_BOARD_URL = "https://jkhc.gov.in/dis/"


def _cell_text(cell):
    return cell.get_text(" ", strip=True)


def _court_number(cell):
    inp = cell.find("input", attrs={"name": "roomno"})
    if inp and inp.get("value", "").strip():
        return inp["value"].strip()
    return _cell_text(cell)


def parse_display_board(html):
    """Returns {wing_name: {"idle": bool,
    "courts": [{"court": "5", "item": "23", "coram": "..."}, ...],
    "raw_status_rows": [...], "messages": [{"id": "8", "text": "..."}]}}"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    result = {}

    for wing_div in soup.select("div.wing"):
        table = wing_div.find("table")
        if not table:
            continue
        rows = table.find_all("tr", recursive=False) or table.find_all("tr")
        if not rows:
            continue

        wing_name = _cell_text(rows[0])
        section = "courts"
        idle = False
        courts = []
        messages = []
        raw_status_rows = []

        for tr in rows[1:]:
            if tr.find("th"):
                if _cell_text(tr).strip().lower() == "messages":
                    section = "messages"
                continue

            cells = tr.find_all("td")
            if not cells:
                continue

            if section == "courts":
                if len(cells) == 1:
                    if _cell_text(cells[0]).lower() == "no cases to display":
                        idle = True
                    continue
                if len(cells) == 3:
                    court = _court_number(cells[0])
                    coram = _cell_text(cells[1])
                    item = _cell_text(cells[2])
                    if court:
                        courts.append({"court": court, "item": item, "coram": coram})
                    continue
                raw_status_rows.append(_cell_text(tr))
            elif len(cells) >= 2:
                msg_id = _cell_text(cells[0])
                text = _cell_text(cells[1])
                if text:
                    messages.append({"id": msg_id, "text": text})

        result[wing_name] = {
            "idle": idle,
            "courts": courts,
            "raw_status_rows": raw_status_rows,
            "messages": messages,
        }
    return result


def fetch_display_board(session, headers, timeout=20):
    resp = session.get(DISPLAY_BOARD_URL, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return parse_display_board(resp.text)
