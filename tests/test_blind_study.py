"""Offline contract tests for opt-in respondent packets. All respondents FAKE."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest

from evidencetrail.blind_study import (
    ARMS, GOLD_CLOCKS, KIND_RESULT, StudyValidationError, assignment,
    main, packet_for_slot, render_packet, score_dir, source_cards, validate_result,
)
from evidencetrail.cross_issuer_milton import run_cross_issuer_milton


def simulated_result(packet, *, time_ms=34000, truthful=True):
    tasks=[]
    for task in packet["tasks"]:
        clock=task["as_of_utc"]
        r=run_cross_issuer_milton(clock)
        wind=r["latest_nhc_selected_wind_mph"]
        count=r["florida_counties_under_emergency_in_selected_order"]
        cited=[]
        if wind is not None:
            cited.append(r["nhc_admitted_ids"][-1])
        orders=[x for x in r["florida_admitted"]
                if x["claim_type"]=="florida_counties_under_emergency"]
        if count is not None:
            cited.append(sorted(orders,key=lambda x:(x["displayed_local_date"],x["id"]))[-1]["id"])
        if not truthful:
            wind=999
            cited=[task["cards"][-1]["source_id"]]
        tasks.append({
            "task_id":task["task_id"],"arm":task["arm"],
            "as_of_utc":clock,
            "nhc_wind_mph":wind,
            "florida_counties":count,
            "source_ids":cited,
            "elapsed_ms":time_ms,
        })
    return {"kind":KIND_RESULT,
            "session_token":packet["session_token"],
            "packet_sha256":packet["packet_sha256"],
            "assignment_slot_mod8":packet["assignment_slot_mod8"],
            "answers":tasks}


class BlindStudyPacketTests(unittest.TestCase):
    def packet(self,slot=0):
        return packet_for_slot(slot,token=f"{slot+1:024x}")

    def test_eight_slots_balance_arms_case_and_order(self):
        examples=[assignment(i) for i in range(8)]
        counts=Counter((c,a) for group in examples for c,a in group)
        self.assertEqual({case for case,arm in counts},set(range(4)))
        self.assertEqual(set(counts.values()),{2})
        self.assertTrue(all({arm for case,arm in group}==set(ARMS) for group in examples))
        first=Counter(arm for group in examples for _,arm in group[:1])
        self.assertEqual(first,{"REFERENCE_ONLY":4,"CHRONOLOGY_ASSISTED":4})

    def test_participant_file_does_not_embed_gold_answer_or_scoring_code(self):
        p=self.packet()
        html=render_packet(p)
        self.assertEqual(html.count(p["session_token"]),1)
        self.assertNotIn("latest_nhc_selected_wind_mph",html)
        self.assertNotIn("florida_counties_under_emergency_in_selected_order",html)
        self.assertNotIn("numeric_correct_0_to_2",html)
        self.assertNotIn("run_cross_issuer_milton",html)
        self.assertNotIn("__STUDY_PACKET_JSON__",html)
        self.assertIn('Content-Security-Policy',html)
        self.assertIn("No cloud upload",html)
        self.assertIn("textContent",html)

    def test_both_arms_show_same_source_cards(self):
        for slot in range(8):
            p=self.packet(slot)
            a,b=p["tasks"]
            self.assertEqual(a["cards"],b["cards"])
            self.assertEqual(len(a["cards"]),7)
            self.assertNotEqual(a["arm"],b["arm"])
            self.assertEqual("admission_overlay" in a,
                             a["arm"]=="CHRONOLOGY_ASSISTED")

    def test_asof_assist_overlay_uses_actual_cross_issuer_admission(self):
        for slot in range(8):
            for task in self.packet(slot)["tasks"]:
                if task["arm"]!="CHRONOLOGY_ASSISTED":
                    continue
                report=run_cross_issuer_milton(task["as_of_utc"])
                expected=set(report["nhc_admitted_ids"]+
                             [x["id"] for x in report["florida_admitted"]])
                self.assertEqual(set(task["admission_overlay"]["admitted_source_ids"]),
                                 expected)
                self.assertFalse(task["admission_overlay"][
                    "first_original_publication_proven"])

    def test_valid_simulated_answers_not_human_certification(self):
        p=self.packet()
        assessment=validate_result(simulated_result(p),p)
        self.assertTrue(assessment["valid_packet_bound_responses"])
        self.assertFalse(assessment["independent_human_verified"])
        self.assertTrue(all(x["numbers_correct"]==2 for x in assessment["scores"]))
        self.assertTrue(all(x["exact_pivotal_citations"] for x in assessment["scores"]))

    def test_fake_error_decreases_accuracy_and_citation(self):
        p=self.packet(2)
        scored=validate_result(simulated_result(p,truthful=False),p)
        self.assertTrue(any(v["numbers_correct"]<2 for v in scored["scores"]))
        self.assertTrue(any(not v["exact_pivotal_citations"] for v in scored["scores"]))

    def test_mismatched_packet_digest_or_session_rejected(self):
        p=self.packet(1)
        for k,val in [("session_token","deadbeefdeadbeefdeadbeef"),
                      ("packet_sha256","0"*64),
                      ("assignment_slot_mod8",7)]:
            r=simulated_result(p)
            r[k]=val
            with self.subTest(k=k),self.assertRaisesRegex(
                StudyValidationError,"RESULT_PACKET_BINDING_INVALID"):
                validate_result(r,p)

    def test_task_reordering_and_condition_swap_rejected(self):
        p=self.packet(4)
        for mutation in ("reorder","arm","case"):
            r=simulated_result(p)
            if mutation=="reorder":
                r["answers"].reverse()
            elif mutation=="arm":
                r["answers"][0]["arm"]="CHRONOLOGY_ASSISTED" if (
                    r["answers"][0]["arm"]=="REFERENCE_ONLY") else "REFERENCE_ONLY"
            else:
                r["answers"][0]["as_of_utc"]="2024-10-09T09:00:00Z"
            with self.subTest(mutation=mutation),self.assertRaisesRegex(
                StudyValidationError,"RESULT_TASK_ASSIGNMENT_MISMATCH"):
                validate_result(r,p)

    def test_injected_citation_and_time_bypass_rejected(self):
        p=self.packet(3)
        for bogus in ("https://evil.test", "<script>"):
            r=simulated_result(p)
            r["answers"][0]["source_ids"]=[bogus]
            with self.subTest(bogus=bogus),self.assertRaisesRegex(
                StudyValidationError,"RESULT_CITATION_IDENTIFIERS_INVALID"):
                validate_result(r,p)
        for bad in (True,-1,0,999,900001,"12345"):
            r=simulated_result(p)
            r["answers"][0]["elapsed_ms"]=bad
            with self.subTest(bad=bad),self.assertRaisesRegex(
                StudyValidationError,"RESULT_TIME_IMPLAUSIBLE_OR_INVALID"):
                validate_result(r,p)

    def test_implicit_missing_answer_distinct_from_explicit_none(self):
        p=self.packet(0)
        r=simulated_result(p)
        del r["answers"][0]["nhc_wind_mph"]
        with self.assertRaisesRegex(StudyValidationError,"RESULT_SCHEMA_FIELDS_INVALID"):
            validate_result(r,p)
        r=simulated_result(p)
        r["answers"][0]["nhc_wind_mph"]=True
        with self.assertRaisesRegex(StudyValidationError,"ANSWER_INT_OR_NULL_INVALID"):
            validate_result(r,p)

    def test_duplicate_forged_and_unregistered_files_not_counted_as_humans(self):
        p=self.packet(5)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);pack=root/"packets";res=root/"responses"
            pack.mkdir();res.mkdir()
            (pack/(p["session_token"]+".json")).write_text(json.dumps(p),encoding="utf8")
            r=simulated_result(p)
            (res/"a.json").write_text(json.dumps(r),encoding="utf8")
            (res/"duplicate.json").write_text(json.dumps(r),encoding="utf8")
            (res/"malformed.json").write_text('{"junk":1}',encoding="utf8")
            report=score_dir(res,pack)
            self.assertEqual(report["unverified_packet_bound_sessions"],1)
            self.assertEqual(report["rejected_file_count"],2)
            self.assertEqual(report["independently_verified_human_participants"],0)
            self.assertFalse(report["human_impact_claim_authorized"])
            self.assertEqual(report["status"],"NO_INDEPENDENT_HUMAN_VALIDATION")

    def test_manifest_file_tampering_not_scored(self):
        p=self.packet(6)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);pack=root/"packets";res=root/"responses"
            pack.mkdir();res.mkdir()
            payload=dict(p)
            payload["voluntary_no_personal_data"]=False
            (pack/(p["session_token"]+".json")).write_text(json.dumps(payload),encoding="utf8")
            (res/"result.json").write_text(json.dumps(simulated_result(p)),encoding="utf8")
            report=score_dir(res,pack)
            self.assertEqual(report["unverified_packet_bound_sessions"],0)
            self.assertEqual(report["rejected_file_count"],1)

    def test_script_tag_termination_is_escaped_in_render(self):
        p=self.packet(7)
        p["participant_procedure"]="</script><script>alert(1)</script>"
        rendered=render_packet(p)
        self.assertNotIn("</script><script>alert(1)</script>",rendered)
        self.assertIn("\\u003c/script",rendered)

    def test_prepare_private_registry_to_score_roundtrip_without_real_people(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            html=root/"participants"/"anonymous-slot-0.html"
            registry=root/"private-registry"
            responses=root/"returned"
            responses.mkdir()
            self.assertEqual(main(["prepare","--slot","0","--out",str(html),
                                   "--registry",str(registry)]),0)
            files=list(registry.glob("*.json"))
            self.assertEqual(len(files),1)
            packet=json.loads(files[0].read_text(encoding="utf-8"))
            self.assertEqual(files[0].stem,packet["session_token"])
            self.assertTrue(html.is_file())
            self.assertEqual(list(html.parent.glob("*.json")),[])
            (responses/"automated-not-human.json").write_text(
                json.dumps(simulated_result(packet)),encoding="utf-8")
            report_path=root/"scores.json"
            self.assertEqual(main(["score","--responses",str(responses),
                                   "--packets",str(registry),
                                   "--output",str(report_path)]),0)
            report=json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["unverified_packet_bound_sessions"],1)
            self.assertEqual(report["independently_verified_human_participants"],0)
            self.assertFalse(report["human_impact_claim_authorized"])
            with self.assertRaises(SystemExit):
                main(["prepare","--slot","0","--out",str(html),
                      "--registry",str(registry)])

    def test_private_registry_must_not_be_exported_to_participant_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); html=root/"person.html"
            with self.assertRaisesRegex(SystemExit,"SHARED_PACKET_DIRECTORY"):
                main(["prepare","--slot","0","--out",str(html),
                      "--registry",str(root)])
            self.assertFalse(html.exists())

    def test_no_embedded_real_participant_or_trial_data(self):
        p=self.packet()
        self.assertTrue(p["voluntary_no_personal_data"])
        self.assertFalse(p["historical_disaster_advice_authorized"])
        self.assertEqual({x["task_id"] for x in p["tasks"]}, {"T0","T3"})
        self.assertEqual(len(source_cards()),7)


if __name__=="__main__":
    unittest.main()
