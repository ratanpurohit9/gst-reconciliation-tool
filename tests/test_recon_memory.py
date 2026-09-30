import sqlite3
import unittest
from pathlib import Path

from recon_memory import (
    assign_row_ids, create_memory, make_row_id, normalize_invoice_number,
    open_uploaded_memory, export_memory, save_run, validate_memory,
)


class MemoryTests(unittest.TestCase):
    def test_row_id_is_stable_and_normalizes_invoice_punctuation(self):
        a = make_row_id("27AAAAA0000A1Z5", "INV/0458", "B", "INV", "2025-26")
        b = make_row_id("27aaaaa0000a1z5", "inv-0458", "B", "INV", "2025-26")
        self.assertEqual(a, b)
        self.assertEqual(normalize_invoice_number("inv/0458"), normalize_invoice_number("INV-0458"))

    def test_assign_row_ids_does_not_depend_on_dataframe_index(self):
        import pandas as pd
        df = pd.DataFrame({"GSTIN": ["G1"], "Invoice Number": ["INV/0458"]}, index=[77])
        row_id = assign_row_ids(df, side="B").iloc[0]["Row ID"]
        other = pd.DataFrame({"GSTIN": ["G1"], "Invoice Number": ["INV-0458"]}, index=[1])
        self.assertEqual(row_id, assign_row_ids(other, side="B").iloc[0]["Row ID"])

    def test_memory_roundtrip_and_replace(self):
        tmp = Path(__file__).parents[1]
        path = tmp / "_test-memory-roundtrip.db"
        uploaded = None
        try:
            create_memory(path, "Client A", "2025 - 2026")
            validate_memory(path, "client a", "2025 - 2026")
            rows = [{"row_id": "r1", "side": "B", "gstin": "G1", "inv_no": "1",
                     "taxable": 100, "engine_status": "Not in GSTR-2B"}]
            save_run(path, "run-1", "April", "GSTR2B", rows, "2025-05-01")
            first = export_memory(path)
            uploaded = open_uploaded_memory(first, "Client A", "2025 - 2026", tmp)
            self.assertEqual(validate_memory(uploaded, "Client A", "2025 - 2026")["client"], "Client A")
            save_run(path, "run-2", "April", "GSTR2B", rows, "2025-05-02")
            db = sqlite3.connect(path)
            try:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM run_lines").fetchone()[0], 1)
            finally:
                db.close()
        finally:
            path.unlink(missing_ok=True)
            if uploaded:
                Path(uploaded).unlink(missing_ok=True)

    def test_mismatched_identity_rejected(self):
        p = Path(__file__).parents[1] / "_test-memory-identity.db"
        try:
            create_memory(p, "A", "2025-26")
            with self.assertRaises(ValueError):
                validate_memory(p, "B", "2025-26")
        finally:
            p.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()

