"""
orders_watcher.py without the network:
  - which cases a causelist entry names (main + connected, not applications)
  - the case-type table and the Orders table parsed from saved portal pages
  - new orders downloaded once, re-uploads of the same PDF not stored twice
  - a not-PDF reply is skipped and retried, not marked as seen
  - linking picks the matching record and records not-found cases
Run: python -m unittest dbtest/test_orders_watcher.py
"""
import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import ecourts_client as ec  # noqa: E402
import orders_watcher as ow  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
HISTORY = open(os.path.join(HERE, "fixture_case_history_WPC_1394_2024.html"), encoding="utf-8").read()
TYPES = open(os.path.join(HERE, "fixture_case_types_srinagar.txt"), encoding="utf-8").read()


def pdf_bytes(tag):
    return b"%PDF-1.4\n% " + tag.encode() + b"\n%%EOF"


class CasesInEntry(unittest.TestCase):
    def test_main_and_connected_cases(self):
        self.assertEqual(
            ow.cases_in_entry("WP(C) 463/2025 CM(1095/2025) CM(4969/2026) c/w i)CCP(S) 109/2025 ii)CCP(S) 167/2026"),
            [("WP(C)", 463, "2025"), ("CCP(S)", 109, "2025"), ("CCP(S)", 167, "2026")])

    def test_application_in_case_gives_the_case(self):
        self.assertEqual(ow.cases_in_entry("CM(5339/2026) IN WP(C) 1319/2025 PREPONEMENT CM(304/2026)"),
                         [("WP(C)", 1319, "2025")])

    def test_bracketed_parent_case_and_caveat_ignored(self):
        self.assertEqual(ow.cases_in_entry("LPASW 26/2019[LPA 42/2019]"), [("LPASW", 26, "2019")])
        self.assertEqual(ow.cases_in_entry("FAO 26/2026 CM(5096/2026) Caveat 1131/2026"), [("FAO", 26, "2026")])
        self.assertEqual(ow.cases_in_entry("RECTIFICATION Caveat 2719/2026"), [])

    def test_two_word_types(self):
        self.assertEqual(ow.cases_in_entry("Arb P 13/2024 CM(1/2024)"), [("Arb P", 13, "2024")])
        self.assertEqual(ow.cases_in_entry("Mac App 7/2023"), [("Mac App", 7, "2023")])


class Aliases(unittest.TestCase):
    def test_renumbered_case_tracked_under_new_number(self):
        matches = [{"caseNo": "FAO 26/2026 CM(5096/2026) Caveat 1131/2026", "caseName": "Z vs S"},
                   {"caseNo": "WP(C) 1/2024", "caseName": "A vs B"}]
        t = ow.tracked_cases(matches, {"FAO 26/2026": "RFA 92/2026"})
        self.assertEqual(sorted(t), ["RFA 92/2026", "WP(C) 1/2024"])
        self.assertEqual((t["RFA 92/2026"]["type"], t["RFA 92/2026"]["number"]), ("RFA", 92))


class PortalParsing(unittest.TestCase):
    def test_case_types(self):
        fake = mock.Mock(text=TYPES)
        with mock.patch.object(ec, "_post_with_retry", return_value=fake):
            types = ec.fetch_case_types(None, "srinagar")
        self.assertEqual(types["WP(C)"], "300")
        self.assertEqual(types["CRM(M)"], "335")
        self.assertEqual(types["Arb P"], "329")
        self.assertIn("FAO(WC)", types)

    def test_orders_table(self):
        rows = ow.parse_orders(HISTORY)
        self.assertEqual(len(rows), 9)
        self.assertEqual(rows[0]["no"], 1)
        self.assertEqual(rows[0]["date"], "2024-07-03")
        self.assertIn("WASIM SADIQ NARGAL", rows[0]["judge"])
        self.assertTrue(rows[0]["url"].startswith(ec.BASE + "/cases/display_pdf.php?"))
        self.assertEqual(len({r["token"] for r in rows}), 9)


class FakePortal:
    def __init__(self, rows, pdfs):
        self.rows, self.pdfs = rows, pdfs

    def history(self, rec):
        return self.rows

    def pdf(self, url):
        return self.pdfs[url]


def history_html(orders):
    trs = "".join(
        f'<tr><td>{n}</td><td>X</td><td>JUDGE</td><td>{d}</td>'
        f'<td><a href="cases/display_pdf.php?filename={tok}&cino=C">View</a></td></tr>'
        for n, d, tok in orders)
    return f'<table class="order_table"><tr><th>h</th></tr>{trs}</table>'


class CheckCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.patch = mock.patch.object(ow, "HERE", self.tmp)
        self.patch.start()
        self.text = mock.patch.object(ow, "extract_text", side_effect=lambda b: ("text of " + b.decode(errors="ignore"), 1, False))
        self.text.start()

    def tearDown(self):
        self.text.stop()
        self.patch.stop()
        shutil.rmtree(self.tmp)

    def url(self, tok):
        return ec.BASE + f"/cases/display_pdf.php?filename={tok}&cino=C"

    def test_downloads_once_and_skips_identical_reupload(self):
        entry = {"status": "linked", "cino": "C", "case_no": "1", "court_code": "2"}
        portal = FakePortal(history_html([(1, "03-07-2024", "a"), (2, "04-07-2024", "b")]),
                            {self.url("a"): pdf_bytes("one"), self.url("b"): pdf_bytes("one")})
        new = ow.check_case(portal, "WP(C) 1/2024", entry)
        self.assertEqual([o["no"] for o in new], [1])  # the re-upload isn't a new order
        first, second = entry["orders"]
        self.assertEqual(first["pdf"], "orders/WP_C_1_2024/001_2024-07-03.pdf")
        self.assertTrue(os.path.exists(os.path.join(self.tmp, first["pdf"])))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, first["text"])))
        self.assertEqual(first["sha256"], hashlib.sha256(pdf_bytes("one")).hexdigest())
        self.assertEqual(second["duplicate_of"], 1)
        self.assertNotIn("pdf", second)
        # second run: nothing new
        self.assertEqual(ow.check_case(portal, "WP(C) 1/2024", entry), [])

    def test_new_order_later(self):
        entry = {"status": "linked", "cino": "C", "case_no": "1", "court_code": "2"}
        pdfs = {self.url("a"): pdf_bytes("one"), self.url("b"): pdf_bytes("two")}
        ow.check_case(FakePortal(history_html([(1, "03-07-2024", "a")]), pdfs), "K 1/2024", entry)
        new = ow.check_case(FakePortal(history_html([(1, "03-07-2024", "a"), (2, "01-08-2024", "b")]), pdfs), "K 1/2024", entry)
        self.assertEqual([o["no"] for o in new], [2])
        self.assertEqual(new[0]["excerpt"], "text of %PDF-1.4 % two %%EOF")

    def test_non_pdf_reply_is_retried(self):
        entry = {"status": "linked", "cino": "C", "case_no": "1", "court_code": "2"}
        rows = history_html([(1, "03-07-2024", "a")])
        self.assertEqual(ow.check_case(FakePortal(rows, {self.url("a"): b"<html>error</html>"}), "K 1/2024", entry), [])
        self.assertEqual(entry["orders"], [])
        self.assertEqual(len(ow.check_case(FakePortal(rows, {self.url("a"): pdf_bytes("x")}), "K 1/2024", entry)), 1)

    def test_next_date_read_on_download_and_backfilled(self):
        entry = {"status": "linked", "cino": "C", "case_no": "1", "court_code": "2"}
        self.text.stop()
        self.text = mock.patch.object(ow, "extract_text", return_value=("Heard. List on 10.12.2026.", 1, False))
        self.text.start()
        portal = FakePortal(history_html([(1, "01-11-2026", "a")]), {self.url("a"): pdf_bytes("x")})
        rec = ow.check_case(portal, "K 1/2024", entry)[0]
        self.assertEqual((rec["next_date"], rec["nd_v"]), ("2026-12-10", ow.NEXT_DATE_VERSION))
        # an order saved before the parser existed gets its date on the next run
        del rec["next_date"], rec["nd_v"]
        self.assertEqual(ow.backfill_next_dates({"K 1/2024": entry}), 1)
        self.assertEqual(rec["next_date"], "2026-12-10")
        self.assertEqual(ow.backfill_next_dates({"K 1/2024": entry}), 0)

    def test_no_download_leaves_orders_unseen(self):
        entry = {"status": "linked", "cino": "C", "case_no": "1", "court_code": "2"}
        portal = FakePortal(history_html([(1, "03-07-2024", "a")]), {self.url("a"): pdf_bytes("x")})
        self.assertEqual(len(ow.check_case(portal, "K 1/2024", entry, download=False)), 1)
        self.assertEqual(len(ow.check_case(portal, "K 1/2024", entry)), 1)


class LinkCase(unittest.TestCase):
    def portal(self, results):
        p = mock.Mock()
        p.type_code.return_value = "300"
        p.search.return_value = results
        return p

    def test_links_matching_record(self):
        entry = {"type": "WP(C)", "number": 1394, "year": "2024"}
        hit = {"case_label": "WP(C)/1394/2024", "cino": "JKHC010028792024", "case_no": "230000013942024",
               "court_code": "2", "petitioner": "A", "respondent": "B"}
        self.assertTrue(ow.link_case(self.portal([hit]), "WP(C) 1394/2024", entry))
        self.assertEqual(entry["status"], "linked")
        self.assertEqual(entry["cino"], "JKHC010028792024")
        self.assertEqual(entry["parties"], "A vs B")

    def test_not_found_and_unknown_type(self):
        entry = {"type": "FAO", "number": 26, "year": "2026"}
        self.assertFalse(ow.link_case(self.portal([]), "FAO 26/2026", entry))
        self.assertEqual(entry["status"], "not_found")
        p = self.portal([])
        p.type_code.return_value = None
        self.assertFalse(ow.link_case(p, "ZZ 1/2026", entry))
        self.assertEqual(entry["status"], "unknown_type")


if __name__ == "__main__":
    unittest.main()
