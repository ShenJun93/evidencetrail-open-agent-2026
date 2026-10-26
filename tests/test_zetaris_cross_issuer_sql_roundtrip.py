"""Observed Zetaris SQL Editor CSV transport normalization, fail-closed.

These are offline regression tests, not additional real sponsor calls. The
successful live SQL receipt is stored separately in ignored acceptance logs.
"""
from __future__ import annotations

from copy import deepcopy
import unittest

from evidencetrail.adapters.zetaris_sql_editor import SqlEditorContractError
from evidencetrail.zetaris_cross_issuer import evaluate_sql_rows
from run_zetaris_cross_issuer import import_rows


def as_actual_sql_editor_csv():
    nhc, fl = import_rows()
    a, b = deepcopy(nhc), deepcopy(fl)
    for row in a:
        row["value_int"] = str(row["value_int"])
        row["issue_utc"] = row["issue_utc"].replace("T", " ").replace("Z", ".0")
    for row in b:
        row["value_int"] = str(row["value_int"])
    return a, b


class SqlEditorObservedTypeRegression(unittest.TestCase):
    def test_real_sql_editor_csv_types_retain_origin_and_witness(self):
        n, f = as_actual_sql_editor_csv()
        result = evaluate_sql_rows(n, f, clock="2024-10-07T11:00:00Z")
        self.assertEqual(result["latest_noaa_wind_mph"], 100)
        self.assertEqual(result["latest_florida_emergency_counties"], 51)
        self.assertEqual(result["selected_original_ids"], [
            "NHC-AL142024-PUBLIC-008","FL-EO-24-214","FL-EO-24-215",
        ])
        self.assertFalse(result["original_2024_first_publication_authenticated"])

    def test_one_hour_backdated_sql_clock_refused(self):
        n, f = as_actual_sql_editor_csv()
        n[0]["issue_utc"] = "2024-10-07 08:00:00.0"
        with self.assertRaisesRegex(SqlEditorContractError,"METADATA_DOES_NOT_MATCH"):
            evaluate_sql_rows(n, f, clock="2024-10-07T11:00:00Z")

    def test_malformed_sql_date_without_verified_utc_pattern_refused(self):
        n, f = as_actual_sql_editor_csv()
        for altered in ("2024-10-07 09:00:00.1", "2024-10-07 09:00:00",
                        "2024-10-07 99:00:00.0", "2024-10-07T09:00:00"):
            with self.subTest(altered=altered):
                candidate = deepcopy(n)
                candidate[0]["issue_utc"] = altered
                with self.assertRaises(SqlEditorContractError):
                    evaluate_sql_rows(candidate, f)

    def test_sql_integer_string_only_plain_decimal(self):
        n, f = as_actual_sql_editor_csv()
        for mutated in ("1e2","0100","100.0","-100",True,None):
            with self.subTest(mutated=mutated):
                candidate = deepcopy(n)
                candidate[0]["value_int"] = mutated
                with self.assertRaises(SqlEditorContractError):
                    evaluate_sql_rows(candidate, f)

    def test_normalization_does_not_make_strict_2024_proof(self):
        n, f = as_actual_sql_editor_csv()
        strict = evaluate_sql_rows(n, f, strict=True,
                                   clock="2024-10-08T04:00:00Z")
        self.assertEqual(strict["selected_original_ids"], [])
        self.assertIsNone(strict["latest_noaa_wind_mph"])
        self.assertIsNone(strict["latest_florida_emergency_counties"])


if __name__=="__main__":
    unittest.main()
