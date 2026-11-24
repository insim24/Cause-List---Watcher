"""
order_dates.next_hearing_date() against phrasings taken from real orders
(case and order date noted on each), including ones with no next date.
Run: python -m unittest dbtest/test_order_dates.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from order_dates import next_hearing_date  # noqa: E402

# (case, order date, text excerpt, expected next date)
REAL = [
    ("Arb P 13/2024", "2024-05-24",
     "Requisite steps for service upon respondent within one week. List on 26.07.2024. "
     "(N. KOTISWAR SINGH) CHIEF JUSTICE SRINAGAR 24.05.2024", "2024-07-26"),
    ("Arb P 13/2024", "2024-10-05",
     "Heard. Admit. Notice. Steps for service be taken within one week. List again on 31st October, 2024. "
     "(TASHI RABSTAN) Chief Justice Srinagar 05.10.2024", "2024-10-31"),
    ("Arb P 13/2024", "2026-05-22",
     "a legible copy of the same. 02. List for consideration on 17.07.2026. (Sanjeev Kumar) Judge Jammu 22.05.2026",
     "2026-07-17"),
    ("CCP(S) 475/2024", "2025-03-03",
     "Time for filing statement of facts/compliance report is further extended by two weeks. "
     "Put up again on 18.03.2025. (Registrar Judicial) SRINAGAR 03.03.2025", "2025-03-18"),
    ("Arb P 13/2024", "2025-04-24",
     "ORDER 24.04.2025 On the request of the learned counsel for the parties, adjourned to 03.07.2025. "
     "(ARUN PALLI) CHIEF JUSTICE JAMMU 24.04.2025", "2025-07-03"),
    ("CPOWP 712/2017", "2024-08-30",
     "the matter is adjourned, to be listed on 4th of October, 2024 with liberty to make a mention.", "2024-10-04"),
    ("CRMC 387/2018", "2021-07-02",
     "In terms of order dated 01.04.2021, the matter was sent to Mediator. Await the report and "
     "re-notify on 11.08.2021. (Sanjeev Kumar) Judge SRINAGAR 02.07.2021", "2021-08-11"),
    ("WP(C) 1394/2024", "2026-08-12",  # the PDF's text splits the date
     "two weeks' time to file reply. List on 21.09 .2026. Interim direction, if any, shall continue "
     "(SHAHZAD AZEEM) JUDGE SRINAGAR 12.08.2026", "2026-09-21"),
    ("OWP 31/2015", "2024-09-04", "List for final hearing 08.10.2024. Meanwhile, record be produced.", "2024-10-08"),
    ("OWP 1417/2018", "2022-09-02",
     "list the writ petition 12th October, 2022. (MOKSHA KHAJURIA KAZMI) JUDGE SRINAGAR", "2022-10-12"),
    ("CONC 17/2019", "2025-11-19",
     "List for consideration of 11th of February, 2026. (M. A. CHOWDHARY) JUDGE SRINAGAR", "2026-02-11"),
    ("SWP 2371/2011", "2025-04-07",
     "List in terms of Order dated 9th September, 2025 on 28th July, 2025. (RAJESH SEKHRI) JUDGE", "2025-07-28"),
    ("CM(M) 355/2025", "2026-09-29", "List on 14-10-2026. 3. Interim direction, if any, to continue.", "2026-10-14"),
    # no next date
    ("SWP 2371/2011", "2022-12-12", "O R D E R 12.12.2022 Heard. Reserved. (MOKSHA KHAJURIA KAZMI) "
     "(SANJEEV KUMAR) JUDGE JUDGE SRINAGAR: 12.12.2022 Altaf", None),
    ("WP(C) 2423/2026", "2026-09-26", "within a period of eight weeks 8. Disposed of. (MOHD YOUSUF WANI) "
     "JUDGE SRINAGAR September 26th, 2026", None),
    ("CRM(M) 216/2024", "2026-02-07", "4. A copy of this order shall also be forwarded to Coordinator "
     "Mediation Centre for necessary action. (MOHD YOUSUF WANI) JUDGE SRINAGAR 07.02.2026", None),
    # the order's own typo puts the date before the order: not trusted
    ("WP(C) 2934/2023", "2025-11-25", "List this matter on 9th February, 2025. 7. In the meantime, the", None),
]


class RealOrders(unittest.TestCase):
    def test_real_phrasings(self):
        for case, od, text, want in REAL:
            with self.subTest(case=case, order_date=od):
                self.assertEqual(next_hearing_date(text, od)[0], want)

    def test_last_listing_wins_over_quoted_earlier_ones(self):
        text = ("Vide order dated 02.03.2026 it was directed to list on 10.03.2026. "
                "Today, reply filed. List on 20.04.2026.")
        self.assertEqual(next_hearing_date(text, "2026-03-10")[0], "2026-04-20")

    def test_signature_date_alone_is_not_a_next_date(self):
        self.assertEqual(next_hearing_date("Heard. Judgment reserved. JUDGE SRINAGAR 12.08.2026", "2026-08-12"),
                         (None, None))

    def test_phrase_is_returned(self):
        self.assertEqual(next_hearing_date("List again on 31st October, 2024.", "2024-10-05")[1],
                         "List again on 31st October, 2024")


if __name__ == "__main__":
    unittest.main()
