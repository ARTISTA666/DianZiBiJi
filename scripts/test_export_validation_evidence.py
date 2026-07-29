from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "export_validation_evidence.py"
SPEC = importlib.util.spec_from_file_location("export_validation_evidence", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ExportValidationEvidenceTests(unittest.TestCase):
    def test_runtime_probes_match_the_rust_production_image(self) -> None:
        commands = MODULE.runtime_probe_commands("eln_user", "eln")
        flattened = [token for command in commands for token in command]

        self.assertNotIn("alembic", flattened)
        self.assertNotIn("python", flattened)
        self.assertIn("psql", flattened)
        self.assertTrue(any("rust_schema_versions" in token for token in flattened))
        self.assertTrue(any("< 2" in token for token in flattened))

    def test_failed_runtime_causes_nonzero_cli_exit(self) -> None:
        self.assertEqual(MODULE.report_exit_code({"runtime": {"ok": False}}), 1)
        self.assertEqual(MODULE.report_exit_code({"runtime": {"ok": True}}), 0)

    def test_extracts_playwright_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.json"
            path.write_text(
                json.dumps(
                    {
                        "stats": {"expected": 1, "startTime": "2026-07-28T00:00:00Z"},
                        "suites": [
                            {
                                "specs": [
                                    {
                                        "title": "flow",
                                        "tests": [{"results": [{"status": "passed", "duration": 12}]}],
                                    }
                                ]
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = MODULE.playwright_results(path)

            self.assertEqual(result["tests"], [{"title": "flow", "status": "passed", "duration_ms": 12}])
            self.assertEqual(result["captured_at"], "2026-07-28T00:00:00Z")
            self.assertEqual(len(result["source"]["sha256"]), 64)
            self.assertEqual(result["source"]["path"], str(path.resolve()))

    def test_graph_metrics_are_computed_from_verdicts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.csv"
            path.write_text(
                "gold_verdict,author_signoff\nTP,signed\nTP,\nFP,\nFN,\n",
                encoding="utf-8",
            )

            result = MODULE.graph_results(path)

            self.assertEqual(result["verdicts"], {"FN": 1, "FP": 1, "TP": 2})
            self.assertEqual(result["author_signoff_count"], 1)
            self.assertAlmostEqual(result["f1"], 2 / 3)

    def test_backup_results_verify_manifest_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "database.dump"
            storage = root / "storage.tar.gz"
            database.write_bytes(b"db")
            storage.write_bytes(b"storage")
            manifest = root / "manifest.txt"
            manifest.write_text(
                "\n".join(
                    (
                        "manifest_version=1",
                        f"database_sha256={MODULE.sha256(database)}",
                        f"storage_sha256={MODULE.sha256(storage)}",
                    )
                ),
                encoding="utf-8",
            )

            result = MODULE.backup_results(root)

            self.assertTrue(result["ok"])
            self.assertEqual(result["checks"], {"database.dump": True, "storage.tar.gz": True})
            self.assertIsNone(result["dump_readable"])

    def test_load_smoke_results_require_successes_without_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "load.json"
            path.write_text(
                json.dumps({"requests": 3, "successful": 3, "errors": [], "p95_ms": 10}),
                encoding="utf-8",
            )

            result = MODULE.load_smoke_results(path)

            self.assertTrue(result["ok"])
            self.assertEqual(result["successful"], 3)

    def test_restart_recovery_results_require_interruption_and_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "restart.json"
            path.write_text(
                json.dumps({"run_id": 7, "interrupted": True, "resumed_status": "completed"}),
                encoding="utf-8",
            )

            result = MODULE.restart_recovery_results(path)

            self.assertTrue(result["ok"])
            self.assertEqual(result["run_id"], 7)

    def test_soak_smoke_results_use_summary_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "soak.json"
            path.write_text(
                json.dumps({"summary": {"ok": True, "cycles": 2, "p95_ms": 10}}),
                encoding="utf-8",
            )

            result = MODULE.soak_smoke_results(path)

            self.assertTrue(result["ok"])
            self.assertEqual(result["summary"]["cycles"], 2)

    def test_npm_audit_results_require_zero_vulnerabilities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "npm-audit.json"
            path.write_text(
                json.dumps({"metadata": {"vulnerabilities": {"low": 0, "high": 0, "total": 0}}}),
                encoding="utf-8",
            )

            result = MODULE.npm_audit_results(path)

            self.assertTrue(result["ok"])
            self.assertEqual(result["vulnerabilities"]["total"], 0)

    def test_production_config_results_include_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "production-config.json"
            path.write_text(
                json.dumps({"ok": True, "status": "skipped_non_production", "app_env": "development"}),
                encoding="utf-8",
            )

            result = MODULE.production_config_results(path)

            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], "skipped_non_production")

    def test_secret_hygiene_results_include_leaks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "secret-hygiene.json"
            path.write_text(json.dumps({"ok": True, "leaks": []}), encoding="utf-8")

            result = MODULE.secret_hygiene_results(path)

            self.assertTrue(result["ok"])
            self.assertEqual(result["leaks"], [])

    def test_secret_rotation_results_include_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "secret-rotation.json"
            path.write_text(json.dumps({"ok": True, "checks": [{"name": "rollback"}]}), encoding="utf-8")

            result = MODULE.secret_rotation_results(path)

            self.assertTrue(result["ok"])
            self.assertEqual(result["checks"][0]["name"], "rollback")

    def test_backup_policy_results_include_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backup-policy.json"
            path.write_text(json.dumps({"ok": True, "checks": [{"name": "offsite copy"}]}), encoding="utf-8")

            result = MODULE.backup_policy_results(path)

            self.assertTrue(result["ok"])
            self.assertEqual(result["checks"][0]["name"], "offsite copy")

    def test_restore_drill_results_include_database_and_storage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "restore-drill.json"
            path.write_text(
                json.dumps({"ok": True, "database": {"public_table_count": 12}, "storage": {"file_count": 2}}),
                encoding="utf-8",
            )

            result = MODULE.restore_drill_results(path)

            self.assertTrue(result["ok"])
            self.assertEqual(result["database"]["public_table_count"], 12)

    def test_monitoring_alerts_results_include_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "monitoring.json"
            path.write_text(json.dumps({"ok": True, "checks": [{"name": "p95"}]}), encoding="utf-8")

            result = MODULE.monitoring_alerts_results(path)

            self.assertTrue(result["ok"])
            self.assertEqual(result["checks"][0]["name"], "p95")

    def test_reverse_proxy_results_include_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reverse-proxy.json"
            path.write_text(json.dumps({"ok": True, "checks": [{"name": "https listener"}]}), encoding="utf-8")

            result = MODULE.reverse_proxy_results(path)

            self.assertTrue(result["ok"])
            self.assertEqual(result["checks"][0]["name"], "https listener")

    def test_metrics_url_is_derived_from_backend_health_url(self) -> None:
        self.assertEqual(
            MODULE.metrics_url_from_backend("http://127.0.0.1:8001/health"),
            "http://127.0.0.1:8001/metrics",
        )

    def test_includes_rukopys_holdout_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_dir = root / "data" / "real" / "rukopys_university" / "holdout" / "final_otsu"
            result_dir.mkdir(parents=True)
            (result_dir / "evaluation_report.json").write_text(
                json.dumps(
                    {
                        "sample_count": 10,
                        "summary": {
                            "raw": {
                                "micro_character_error_rate": 0.78,
                                "micro_compact_character_error_rate": 0.82,
                                "numeric_tokens": {"f1": 0.19},
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            (result_dir / "run.json").write_text(
                json.dumps({"engine": "tesseract", "manifest_sha256": "abc"}),
                encoding="utf-8",
            )
            htrflow_dir = result_dir.parent / "runs" / "htrflow-holdout-simple"
            htrflow_dir.mkdir(parents=True)
            (htrflow_dir / "evaluation.json").write_text(
                json.dumps(
                    {
                        "sample_count": 10,
                        "summary": {
                            "raw": {
                                "micro_character_error_rate": 1.11,
                                "micro_compact_character_error_rate": 1.21,
                                "numeric_tokens": {"f1": 0.44},
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            (htrflow_dir / "run.json").write_text(
                json.dumps({"engine": "HTRflow", "manifest_sha256": "def"}),
                encoding="utf-8",
            )

            result = MODULE.ocr_results(root)

            self.assertEqual(len(result), 2)
            self.assertEqual({item["dataset"] for item in result}, {"rukopys_university"})
            self.assertEqual({item["split"] for item in result}, {"holdout"})
            self.assertEqual({item["name"] for item in result}, {"final_otsu", "htrflow-holdout-simple"})
            self.assertEqual({item["sample_count"] for item in result}, {10})


if __name__ == "__main__":
    unittest.main()
