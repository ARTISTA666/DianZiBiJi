from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "freeze_preregistration.py"
SPEC = importlib.util.spec_from_file_location("freeze_preregistration", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FreezePreregistrationTests(unittest.TestCase):
    def test_builds_portable_manifest_and_verifies_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "bundle" / "rules.txt"
            source.parent.mkdir()
            source.write_text("frozen rules\n", encoding="utf-8")
            output = root / "manifest.json"

            manifest = MODULE.build_manifest([source], root)
            MODULE.write_manifest(manifest, output)
            report = MODULE.verify_manifest(output, root)

            self.assertEqual(manifest["format_version"], 2)
            self.assertEqual(manifest["files"][0]["path"], "bundle/rules.txt")
            self.assertTrue(report["ok"])

    def test_verification_detects_changed_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "rules.txt"
            source.write_text("before\n", encoding="utf-8")
            output = root / "manifest.json"
            MODULE.write_manifest(MODULE.build_manifest([source], root), output)

            source.write_text("after\n", encoding="utf-8")
            report = MODULE.verify_manifest(output, root)

            self.assertFalse(report["ok"])
            self.assertFalse(report["checks"][0]["sha256_matches"])

    def test_evidence_revision_is_deterministic_and_excludes_manifest_self(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "rules.txt"
            source.write_text("before\n", encoding="utf-8")
            output = root / "manifest.json"
            # A real output path exists at freeze time but is deliberately not
            # an evidence input; including it would make the digest recursive.
            output.write_text("placeholder\n", encoding="utf-8")

            manifest = MODULE.build_manifest(
                [source, output],
                root,
                runtime_source_revision="r" * 40,
                experiment_tooling_revision="t" * 40,
                manifest_path=output,
            )
            MODULE.write_manifest(manifest, output, replace=True)
            first = MODULE.verify_manifest(output, root)
            self.assertTrue(first["ok"])
            self.assertTrue(first["evidence_revision_valid"])
            self.assertEqual([entry["path"] for entry in manifest["files"]], ["rules.txt"])

            revision_tampered = json.loads(output.read_text(encoding="utf-8"))
            revision_tampered["experiment_tooling_revision"] = "x" * 40
            output.write_text(json.dumps(revision_tampered), encoding="utf-8")
            self.assertFalse(MODULE.verify_manifest(output, root)["ok"])
            MODULE.write_manifest(manifest, output, replace=True)

            source.write_text("tampered\n", encoding="utf-8")
            tampered = MODULE.verify_manifest(output, root)
            self.assertFalse(tampered["ok"])
            self.assertTrue(tampered["evidence_revision_valid"])
            self.assertFalse(tampered["checks"][0]["sha256_matches"])

            source.write_text("before\n", encoding="utf-8")
            rewritten = json.loads(output.read_text(encoding="utf-8"))
            rewritten["evidence_revision"]["sha256"] = "0" * 64
            output.write_text(json.dumps(rewritten), encoding="utf-8")
            evidence_tampered = MODULE.verify_manifest(output, root)
            self.assertFalse(evidence_tampered["ok"])
            self.assertFalse(evidence_tampered["evidence_revision_valid"])

    def test_verification_rejects_absolute_paths_outside_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root.parent / "outside.txt"
            outside.write_text("outside\n", encoding="utf-8")
            output = root / "manifest.json"
            output.write_text(
                json.dumps(
                    {
                        "files": [
                            {
                                "path": str(outside),
                                "size_bytes": outside.stat().st_size,
                                "sha256": MODULE.sha256_file(outside),
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = MODULE.verify_manifest(output, root)

            self.assertFalse(report["ok"])
            self.assertFalse(report["checks"][0]["inside_root"])
            self.assertFalse(report["checks"][0]["exists"])

    def test_verification_rejects_parent_traversal_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root.parent / "outside.txt"
            outside.write_text("outside\n", encoding="utf-8")
            output = root / "manifest.json"
            output.write_text(
                json.dumps(
                    {
                        "files": [
                            {
                                "path": "../outside.txt",
                                "size_bytes": outside.stat().st_size,
                                "sha256": MODULE.sha256_file(outside),
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = MODULE.verify_manifest(output, root)

            self.assertFalse(report["ok"])
            self.assertFalse(report["checks"][0]["inside_root"])

    def test_verification_rejects_dot_and_lexical_alias_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "rules.txt"
            source.write_text("rules\n", encoding="utf-8")
            output = root / "manifest.json"
            entries = [
                {"path": "./rules.txt", "size_bytes": source.stat().st_size, "sha256": MODULE.sha256_file(source)},
                {"path": "sub/../rules.txt", "size_bytes": source.stat().st_size, "sha256": MODULE.sha256_file(source)},
            ]
            output.write_text(json.dumps({"format_version": 2, "path_base": "root_argument", "files": entries}), encoding="utf-8")

            report = MODULE.verify_manifest(output, root)

            self.assertFalse(report["ok"])
            self.assertTrue(all(not item["inside_root"] for item in report["checks"]))

    def test_verification_rejects_symlink_alias_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "rules.txt"
            source.write_text("rules\n", encoding="utf-8")
            alias = root / "alias.txt"
            alias.symlink_to(source)
            output = root / "manifest.json"
            entries = [
                {"path": "rules.txt", "size_bytes": source.stat().st_size, "sha256": MODULE.sha256_file(source)},
                {"path": "alias.txt", "size_bytes": source.stat().st_size, "sha256": MODULE.sha256_file(source)},
            ]
            output.write_text(json.dumps({"format_version": 2, "path_base": "root_argument", "files": entries}), encoding="utf-8")

            report = MODULE.verify_manifest(output, root)

            self.assertFalse(report["ok"])
            self.assertTrue(report["checks"][0]["inside_root"])
            self.assertFalse(report["checks"][1]["inside_root"])

    def test_verification_rejects_windows_absolute_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "manifest.json"
            output.write_text(
                json.dumps({"files": [{"path": "C:\\\\evidence\\\\freeze.json", "size_bytes": 1, "sha256": "x"}]}),
                encoding="utf-8",
            )

            report = MODULE.verify_manifest(output, root)

            self.assertFalse(report["ok"])
            self.assertFalse(report["checks"][0]["inside_root"])

    def test_verification_reports_corrupt_manifest_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "manifest.json"
            output.write_text("{not json", encoding="utf-8")

            report = MODULE.verify_manifest(output, root)

            self.assertFalse(report["ok"])
            self.assertEqual(report["file_count"], 0)
            self.assertIn("error", report["checks"][0])

    def test_verification_rejects_non_object_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "manifest.json"
            output.write_text("[]", encoding="utf-8")

            report = MODULE.verify_manifest(output, root)

            self.assertFalse(report["ok"])
            self.assertEqual(report["checks"][0]["error"], "manifest must contain a JSON object")

    def test_verification_rejects_legacy_manifest_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "rules.txt"
            source.write_text("rules\n", encoding="utf-8")
            output = root / "manifest.json"
            output.write_text(
                json.dumps(
                    {
                        "files": [
                            {
                                "path": "rules.txt",
                                "size_bytes": source.stat().st_size,
                                "sha256": MODULE.sha256_file(source),
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = MODULE.verify_manifest(output, root)

            self.assertFalse(report["ok"])
            self.assertFalse(report["valid_shape"])

    def test_verification_rejects_duplicate_manifest_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "rules.txt"
            source.write_text("rules\n", encoding="utf-8")
            output = root / "manifest.json"
            entry = {
                "path": "rules.txt",
                "size_bytes": source.stat().st_size,
                "sha256": MODULE.sha256_file(source),
            }
            output.write_text(
                json.dumps({"format_version": 2, "path_base": "root_argument", "files": [entry, entry]}),
                encoding="utf-8",
            )

            report = MODULE.verify_manifest(output, root)

            self.assertFalse(report["ok"])
            self.assertEqual(report["duplicate_paths"], ["rules.txt"])

    def test_existing_manifest_is_not_overwritten_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "manifest.json"
            output.write_text("{}\n", encoding="utf-8")

            with self.assertRaisesRegex(FileExistsError, "already exists"):
                MODULE.write_manifest({"files": []}, output)


if __name__ == "__main__":
    unittest.main()
