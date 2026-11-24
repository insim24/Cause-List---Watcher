"""
Reads the next-hearing date out of a J&K High Court order's text.

The phrasings come from a survey of the 977 orders downloaded so far:
  "List on 26.07.2024."                         (530 orders)
  "List again on 31st October, 2024."            (70)
  "List for consideration/continuation/final hearing on 17.07.2026."
  "Put up again on 18.03.2025."                  (Registrar's orders, 22)
  "adjourned to 03.07.2025."                     (10)
  "to be listed on 4th of October, 2024"         (11)
  "re-notify on 11.08.2021."
Dates are dd.mm.yyyy (most), "31st October, 2024" / "4th of October, 2024",
or dd-mm-yyyy; one PDF splits a date as "21.09 .2026". About 6% of orders
name no next date at all ("Heard. Reserved.", "Disposed of.", mediation).

Dates that are NOT the next date: the order's own date in the signature
("SRINAGAR 12.08.2026") and earlier orders ("in terms of order dated
01.04.2021"). Only a date that follows a listing phrase in the same
sentence counts, it must be after the order's date, and the last such
date in the order wins (earlier ones are usually quoted from past orders).
"""
import re
from datetime import date

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

NUMERIC = r"(?P<d>\d{1,2})[.\-/](?P<m>\d{1,2})[.\-/](?P<y>\d{4}|\d{2})(?!\d)"
WORDY = (r"(?P<d2>\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+(?P<y2>\d{4})"
         r"|(?P<mon3>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(?P<d3>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<y3>\d{4})")
DATE = rf"(?:{NUMERIC}|{WORDY})"

# A listing phrase, then up to ~80 characters of the same sentence, then
# (usually) "on/to/for/of" and the date. The preposition is sometimes left
# out ("List for final hearing 08.10.2024", "list the writ petition 12th
# October, 2022"). A date right after "dated" is an earlier order's date
# ("List in terms of Order dated 9th September, 2025 on 28th July, 2025").
PHRASE = (r"\b(?:list(?:ed)?|put\s+up|adjourned|re-?notif(?:y|ied)|posted|come\s+up)\b"
          r"(?P<between>(?:(?!\.\s+[A-Z(])[^;:!?]){0,80}?)"   # same sentence only
          r"(?<!dated)(?<!dated )(?:\b(?:on|to|for|till|before|of)\s+(?:the\s+)?|\s)")
PATTERN = re.compile(PHRASE + DATE, re.I)


def _normalise(text):
    t = re.sub(r"\s+", " ", text)
    # "21.09 .2026" / "21 .09.2026": the PDF's text layer split the date
    return re.sub(r"(?<=\d)\s*([.\-/])\s*(?=\d)", r"\1", t)


def _to_date(m):
    try:
        if m.group("d"):
            y = int(m.group("y"))
            return date(y + 2000 if y < 100 else y, int(m.group("m")), int(m.group("d")))
        if m.group("d2"):
            return date(int(m.group("y2")), MONTHS[m.group("mon").lower()[:3]], int(m.group("d2")))
        return date(int(m.group("y3")), MONTHS[m.group("mon3").lower()[:3]], int(m.group("d3")))
    except ValueError:  # e.g. 31.02.2026
        return None


def next_hearing_date(text, order_date=None):
    """Returns (iso_date, phrase) or (None, None). `order_date` (ISO) rules
    out dates on or before the order itself and implausible ones (>3 years on)."""
    t = _normalise(text or "")
    od = date.fromisoformat(order_date) if order_date else None
    found = (None, None)
    for m in PATTERN.finditer(t):
        d = _to_date(m)
        if not d:
            continue
        if od and (d <= od or (d - od).days > 3 * 366):
            continue
        found = (d.isoformat(), m.group(0).strip())
    return found
