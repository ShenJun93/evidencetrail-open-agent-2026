"""Adversarial guards for retrospective GTS witness clocks; no network."""
from __future__ import annotations

from copy import deepcopy
import json
import unittest

from evidencetrail.gts_witness import (
    FIXTURE, validated_gts_witnesses, compare_gts_vs_bulletin_clocks,
)


class GTSWitnessTests(unittest.TestCase):
    def fixture(self):
        return json.loads(FIXTURE.read_text("utf-8"))

    def test_four_official_rows_and_early_relay_clocks(self):
        rows = validated_gts_witnesses()
        self.assertEqual(len(rows), 4)
        self.assertEqual([r["minutes_received_before_valid"] for r in rows],
                         [1, 11, 5, 24])
        self.assertEqual([r["reported_wind_mph"] for r in rows], [100, 125, 155, 70])

    def test_relay_clock_cannot_masquerade_as_bulletin_valid_clock(self):
        for at, relay_count, valid_count in [
            ("2024-10-07T08:58:00Z", 0, 0),
            ("2024-10-07T08:59:00Z", 1, 0),
            ("2024-10-07T09:00:00Z", 1, 1),
            ("2024-10-07T11:49:00Z", 2, 1),
            ("2024-10-07T12:00:00Z", 2, 2),
            ("2024-10-07T14:55:00Z", 3, 2),
            ("2024-10-07T15:00:00Z", 3, 3),
            ("2024-10-10T20:36:00Z", 4, 3),
            ("2024-10-10T21:00:00Z", 4, 4),
        ]:
            with self.subTest(at=at):
                result = compare_gts_vs_bulletin_clocks(at)
                self.assertEqual(len(result["gdacs_relay_reportedly_seen_source_ids"]), relay_count)
                self.assertEqual(len(result["nhc_bulletin_valid_source_ids"]), valid_count)
                self.assertFalse(result["independent_original_first_publication_proven"])
                self.assertFalse(result["relay_is_additional_independent_issuer"])

    def test_strict_refuses_retroactively_displayed_clocks(self):
        out = compare_gts_vs_bulletin_clocks("2024-10-10T21:00:00Z", strict=True)
        self.assertEqual(out["status"], "ABSTAIN_UNAUTHENTICATED_FIRST_PUBLICATION")
        self.assertEqual(out["gdacs_relay_reportedly_seen_source_ids"], [])
        self.assertEqual(out["nhc_bulletin_valid_source_ids"], [])

    def test_whole_batch_tamper_guards(self):
        template = self.fixture()
        def tamper(mutate):
            candidate = deepcopy(template)
            mutate(candidate)
            with self.assertRaises(ValueError):
                validated_gts_witnesses(candidate)
        tamper(lambda x: x["rows"].pop())
        tamper(lambda x: x["rows"].append(deepcopy(x["rows"][0])))
        tamper(lambda x: x["rows"][1].update(source_id=x["rows"][0]["source_id"]))
        tamper(lambda x: x["rows"][0].update(wind_mph=155))
        tamper(lambda x: x["rows"][1].update(wmo_header="WTNT34 KNHC 081147"))
        tamper(lambda x: x["rows"][2].update(gts_received_utc="2024-10-07T14:40:00Z"))
        tamper(lambda x: x["rows"][3].update(gts_received_utc="2024-10-10T21:40:00Z"))
        tamper(lambda x: x.update(authentic_2024_first_web_publication_proven=True))
        tamper(lambda x: x.update(contemporaneous_immutable_reception_log_proven=True))
        tamper(lambda x: x.update(source_url="https://attacker.example/forged"))
        tamper(lambda x: x["rows"][0].update(source_id="FL-EO-24-215"))

    def test_reject_invalid_asof_and_strict(self):
        for at in ("2025-10-07T12:00:00Z", "2024-10-07T12:00:23Z",
                   "2024-13-07T12:00:00Z", "not-time"):
            with self.subTest(at=at), self.assertRaises(ValueError):
                compare_gts_vs_bulletin_clocks(at)
        with self.assertRaises(ValueError):
            compare_gts_vs_bulletin_clocks("2024-10-07T12:00:00Z", strict="true")


if __name__ == "__main__":
    unittest.main()
