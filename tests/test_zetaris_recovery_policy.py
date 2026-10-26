"""Isolated policy tests: NEVER contact Docker or start containers."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import diagnose_zetaris_recovery as diagnosis
import restore_local_zetaris as restore


def safe_report():
    containers = []
    for name, service in restore.ORDER + list(restore.ONE_SHOT.items()):
        entry = {
            "name": name, "found": True, "status": "exited",
            "exit_code": 0, "oom_killed": False,
            "compose_project": "zetaris", "compose_service": service,
            "volume_mount_count": 1 if service == "postgres" else 0,
            "persistent_mount_count": 1 if service == "postgres" else 0,
        }
        containers.append(entry)
    return {
        "status": "STOPPED_STACK_VERIFIED_MANUAL_START_CAN_BE_CONSIDERED",
        "docker_context": {"permitted": True},
        "resources": {
            "available": True, "docker_server_linux": True, "cpus": 8,
            "memory_gb_decimal": 8.33, "memory_gib": 7.76,
            "meets_recommended_8gb_4cpu": True,
            "meets_zetaris_preflight_6gb_minimum": True,
        },
        "compose_project": "zetaris", "same_compose_project": True,
        "postgres_persistent_mount_present": True,
        "containers": containers,
    }


class ExistingZetarisRestorePolicyTests(unittest.TestCase):
    def test_7_76_gib_satisfies_8_decimal_gb_zetaris_recommendation(self):
        # Memory is reported as bytes by Docker; previously compared to 8 GiB.
        raw = "8332236554|8|linux"
        with patch.object(diagnosis, "exec_local", return_value=raw):
            result = diagnosis.inspect_docker_resources()
        self.assertAlmostEqual(result["memory_gib"], 7.76, places=1)
        self.assertTrue(result["meets_recommended_8gb_4cpu"])
        self.assertTrue(result["meets_zetaris_preflight_6gb_minimum"])
        self.assertGreater(result["memory_gb_decimal"], 8)

    def test_less_than_sponsor_6gb_preflight_rejected(self):
        raw = "5999999999|8|linux"
        with patch.object(diagnosis, "exec_local", return_value=raw):
            result = diagnosis.inspect_docker_resources()
        self.assertFalse(result["meets_recommended_8gb_4cpu"])
        self.assertFalse(result["meets_zetaris_preflight_6gb_minimum"])

    def test_unmodified_original_stack_allowed_for_explicit_opt_in(self):
        self.assertEqual(restore.preflight_reasons(safe_report()), [])

    def test_postgres_volume_absent_blocks(self):
        report = safe_report()
        report["postgres_persistent_mount_present"] = False
        report["containers"][0]["volume_mount_count"] = 0
        self.assertIn("POSTGRES_VOLUME_NOT_VERIFIED", restore.preflight_reasons(report))

    def test_oom_killed_and_wrong_compose_block(self):
        report = safe_report()
        report["containers"][1]["oom_killed"] = True
        report["containers"][2]["compose_project"] = "other"
        reasons = restore.preflight_reasons(report)
        self.assertIn("DOCKER_RECORDED_OOM_DRIVER", reasons)
        self.assertIn("WRONG_COMPOSE_IDENTITY_API", reasons)

    def test_one_shot_init_bootstrap_must_remain_successful_and_exited(self):
        report = safe_report()
        report["containers"][4]["status"] = "running"
        self.assertIn(
            "ONE_SHOT_JOB_NOT_COMPLETED_INIT",
            restore.preflight_reasons(report),
        )

    def test_check_is_read_only_even_when_ready(self):
        report = safe_report()
        with patch.object(restore, "build_report", return_value=report), \
             patch.object(restore, "exec_local",
                          side_effect=AssertionError("Docker start forbidden")):
            receipt, code = restore.execute(start=False)
        self.assertEqual(code, 0)
        self.assertEqual(receipt["started_in_this_attempt"], [])
        self.assertEqual(
            receipt["status"], "READY_OWNER_MUST_EXPLICITLY_OPT_IN_TO_START",
        )

    def test_start_exactly_four_and_never_init_bootstrap(self):
        report = safe_report()
        started = []
        def fake_exec(*args, **_kw):
            if args[0] == "start":
                started.append(args[1])
            return ""
        def ready(_name, _service):
            return {"ready": True, "state": {
                "status": "running", "oom_killed": False, "health": "healthy",
            }}
        found = {x["name"]: x for x in report["containers"]}
        with patch.object(restore, "build_report", return_value=report), \
             patch.object(restore, "inspect_container", side_effect=lambda n: found[n]), \
             patch.object(restore, "exec_local", side_effect=fake_exec), \
             patch.object(restore, "await_health", side_effect=ready), \
             patch.object(restore, "tcp_open", return_value=True):
            receipt, code = restore.execute(start=True)
        self.assertEqual(code, 0)
        self.assertEqual(receipt["status"], "FOUR_EXISTING_SERVICES_HEALTHY_UI_PORT_OPEN")
        self.assertEqual(started, [name for name, _ in restore.ORDER])
        self.assertTrue(all("init" not in n and "bootstrap" not in n for n in started))

    def test_unhealthy_driver_prevents_api_and_ui_start(self):
        report = safe_report()
        started = []
        def start_service(*args, **_kw):
            if args[0] == "start":
                started.append(args[1])
            return ""
        def status(_name, service):
            if service == "driver":
                return {"ready": False, "state": {
                    "status": "running", "health": "unhealthy", "oom_killed": False,
                }, "reason": "HEALTH_NOT_READY_IN_BOUNDED_OBSERVATION"}
            return {"ready": True, "state": {
                "status": "running", "health": "healthy", "oom_killed": False,
            }}
        found = {x["name"]: x for x in report["containers"]}
        with patch.object(restore, "build_report", return_value=report), \
             patch.object(restore, "inspect_container", side_effect=lambda n: found[n]), \
             patch.object(restore, "exec_local", side_effect=start_service), \
             patch.object(restore, "await_health", side_effect=status):
            receipt, code = restore.execute(start=True)
        self.assertEqual(code, 1)
        self.assertEqual(receipt["status"], "PARTIAL_START_STOP_ADVANCING_REVIEW_MANUALLY")
        self.assertEqual(started, ["zetaris-postgres-1", "zetaris-driver-1"])

    def test_remote_context_blocks_any_start(self):
        report = safe_report()
        report["docker_context"]["permitted"] = False
        with patch.object(restore, "build_report", return_value=report), \
             patch.object(restore, "exec_local",
                          side_effect=AssertionError("No Docker call allowed")):
            receipt, code = restore.execute(start=True)
        self.assertEqual(code, 2)
        self.assertEqual(receipt["started_in_this_attempt"], [])
        self.assertIn("DOCKER_CONTEXT_NOT_LOCAL", receipt["blockers"])


if __name__ == "__main__":
    unittest.main()
