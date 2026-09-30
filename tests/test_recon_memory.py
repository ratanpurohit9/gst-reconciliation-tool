import unittest
import pandas as pd
from recon_memory import assign_row_ids, make_row_id, normalize_invoice_number


class StableRowIdTests(unittest.TestCase):
    def test_invoice_punctuation_is_normalized(self):
        self.assertEqual(normalize_invoice_number("INV/0458"), normalize_invoice_number("inv-0458"))

    def test_identity_is_stable_across_runs_and_not_amount_based(self):
        a = make_row_id("27AAAAA0000A1Z5", "INV/0458", "B", "INV", "2025-26")
        b = make_row_id("27aaaaa0000a1z5", "inv-0458", "B", "INV", "2025-26")
        self.assertEqual(a, b)

    def test_dataframe_index_is_not_part_of_identity(self):
        a = pd.DataFrame({"GSTIN": ["G1"], "Invoice Number": ["INV/0458"]}, index=[77])
        b = pd.DataFrame({"GSTIN": ["G1"], "Invoice Number": ["inv-0458"]}, index=[2])
        self.assertEqual(assign_row_ids(a, side="B").iloc[0]["Row ID"],
                         assign_row_ids(b, side="B").iloc[0]["Row ID"])


if __name__ == "__main__":
    unittest.main()

