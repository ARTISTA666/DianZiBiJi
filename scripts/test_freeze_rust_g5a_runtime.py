from __future__ import annotations

import importlib.util
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/freeze_rust_g5a_runtime.py"
SPEC = importlib.util.spec_from_file_location("freeze_rust_g5a_runtime", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

COMMIT = "a" * 40


def write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def snapshot_sha256(entries: list[tuple[str, str]]) -> str:
    canonical = [{"path": path, "sha256": digest} for path, digest in sorted(entries)]
    encoded = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def make_inputs(root: Path, valid: bool = True) -> dict[str, Path]:
    revision = COMMIT if valid else "unversioned"
    corpus_data = root / "corpus-data.txt"
    corpus_data.write_text("immutable corpus bytes\n", encoding="utf-8")
    corpus_entries = [(corpus_data.name, MODULE.sha256_file(corpus_data))]
    return {
        "contract": write_json(root / "runtime-contract.json", {"app_revision": revision, "runtime_revision": revision, "runtime": {"api_runtime": "rust-axum"}}),
        "config": write_json(root / "runtime-config.json", {"schema": "runtime-config-v1", "app_revision": COMMIT, "runtime_revision": COMMIT}),
        "image": write_json(root / "container-image.json", {"image_digest": "sha256:" + "b" * 64, "app_revision": COMMIT, "runtime_revision": COMMIT, "oci_revision": COMMIT, "endpoint_revision": COMMIT, "projection_sha256": "c" * 64}),
        "corpus": write_json(root / "corpus-manifest.json", {
            "dataset_id": "synthetic-test-corpus",
            "provenance": {"source": "unit-test fixture"},
            "snapshot_sha256": snapshot_sha256(corpus_entries),
            "files": [{"path": path, "sha256": digest} for path, digest in corpus_entries],
        }),
    }


def make_package(root: Path, valid: bool = True) -> dict:
    paths = make_inputs(root, valid)
    return MODULE.build_package(
        root=root,
        runtime_contract=paths["contract"],
        runtime_config=paths["config"],
        container_image=paths["image"],
        corpus_manifest=paths["corpus"],
        checkout={"head_revision": COMMIT, "tracked_worktree_clean": True, "worktree_clean": True},
    )


class G5ARuntimeFreezeTests(unittest.TestCase):
    def test_complete_bindings_wait_for_external_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = make_package(Path(directory))
            self.assertEqual(package["status"], "STRUCTURE_VALID_AWAITING_AUTHORITY")
            self.assertFalse(package["blockers"])
            self.assertTrue(all(item["status"] == "PASS" for item in package["bindings"].values()))
            self.assertEqual(package["checks"]["external_authority"]["status"], "AWAITING_AUTHORITY")

    def test_missing_or_unversioned_inputs_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = make_package(root, valid=False)
            self.assertEqual(package["status"], "BLOCKED")
            self.assertIn("app_revision", package["blockers"])
            self.assertIsNone(package["bindings"]["app_revision"]["value"])

            paths = make_inputs(root)
            package = MODULE.build_package(root=root, runtime_contract=paths["contract"], runtime_config=root / "missing-config.json", container_image=root / "missing-image.json", corpus_manifest=root / "missing-corpus.json", checkout={"head_revision": COMMIT, "tracked_worktree_clean": True, "worktree_clean": True})
            self.assertTrue({"runtime_config", "container_image", "corpus_manifest"}.issubset(package["blockers"]))

    def test_revision_and_dirty_checkout_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = make_inputs(root)
            package = MODULE.build_package(root=root, runtime_contract=paths["contract"], runtime_config=paths["config"], container_image=paths["image"], corpus_manifest=paths["corpus"], checkout={"head_revision": "d" * 40, "tracked_worktree_clean": True, "worktree_clean": False})
            self.assertEqual(package["status"], "BLOCKED")
            self.assertIn("revision_match", package["blockers"])
            self.assertIn("worktree_clean", package["blockers"])

    def test_container_identity_requires_oci_endpoint_and_projection_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = make_inputs(root)
            image = json.loads(paths["image"].read_text(encoding="utf-8"))
            image["oci_revision"] = "d" * 40
            paths["image"].write_text(json.dumps(image) + "\n", encoding="utf-8")
            package = MODULE.build_package(
                root=root,
                runtime_contract=paths["contract"],
                runtime_config=paths["config"],
                container_image=paths["image"],
                corpus_manifest=paths["corpus"],
                checkout={"head_revision": COMMIT, "tracked_worktree_clean": True, "worktree_clean": True},
            )
            self.assertIn("container_image", package["blockers"])

    def test_manifest_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = make_package(root)
            package_path, manifest_path = root / "package.json", root / "manifest.json"
            MODULE.write_package(package, package_path, manifest_path, root)
            self.assertTrue(MODULE.verify_package(package_path, manifest_path, root)["ok"])
            (root / "runtime-config.json").write_text("tampered\n", encoding="utf-8")
            self.assertFalse(MODULE.verify_package(package_path, manifest_path, root)["ok"])

    def test_manifest_cannot_replace_package_file_list_or_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = make_package(root)
            package_path, manifest_path = root / "package.json", root / "manifest.json"
            MODULE.write_package(package, package_path, manifest_path, root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"] = []
            manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
            self.assertFalse(MODULE.verify_package(package_path, manifest_path, root)["ok"])

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"] = package["source_files"]
            manifest["package_file"] = "decoy.json"
            manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
            self.assertFalse(MODULE.verify_package(package_path, manifest_path, root)["ok"])

    def test_supplied_malformed_authority_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = make_inputs(root)
            authority = write_json(root / "authority.json", {"authority_id": "id-only"})
            package = MODULE.build_package(
                root=root,
                runtime_contract=paths["contract"],
                runtime_config=paths["config"],
                container_image=paths["image"],
                corpus_manifest=paths["corpus"],
                authority_evidence=authority,
                checkout={"head_revision": COMMIT, "tracked_worktree_clean": True, "worktree_clean": True},
            )
            self.assertEqual(package["checks"]["external_authority"]["status"], "BLOCKED")
            self.assertIn("external_authority", package["blockers"])

    def test_malformed_inputs_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = make_package(root)
            package_path, manifest_path = root / "package.json", root / "manifest.json"
            MODULE.write_package(package, package_path, manifest_path, root)
            malformed_manifest = root / "malformed.json"
            malformed_manifest.write_bytes(b"\xff\xfe\xfd")
            report = MODULE.verify_package(package_path, malformed_manifest, root)
            self.assertFalse(report["ok"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"] = ["not-an-object"]
            manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
            self.assertFalse(MODULE.verify_package(package_path, manifest_path, root)["ok"])

    def test_corpus_requires_recomputed_manifest_and_file_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = make_inputs(root)
            package = make_package(root)
            self.assertEqual(package["checks"]["corpus_manifest"]["status"], "PASS")
            self.assertEqual(package["checks"]["corpus_manifest"]["value"]["manifest_sha256"], MODULE.sha256_file(paths["corpus"]))
            self.assertEqual(
                package["checks"]["corpus_manifest"]["value"]["snapshot_sha256"],
                package["checks"]["corpus_manifest"]["value"]["computed_snapshot_sha256"],
            )

            corpus = json.loads(paths["corpus"].read_text(encoding="utf-8"))
            corpus["snapshot_sha256"] = "d" * 64
            paths["corpus"].write_text(json.dumps(corpus) + "\n", encoding="utf-8")
            blocked = MODULE.build_package(
                root=root,
                runtime_contract=paths["contract"],
                runtime_config=paths["config"],
                container_image=paths["image"],
                corpus_manifest=paths["corpus"],
                checkout={"head_revision": COMMIT, "tracked_worktree_clean": True, "worktree_clean": True},
            )
            self.assertEqual(blocked["checks"]["corpus_manifest"]["status"], "BLOCKED")
            self.assertFalse(blocked["checks"]["corpus_manifest"]["value"]["snapshot_matches"])

    def test_verify_separates_integrity_from_freeze_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = make_package(root, valid=False)
            package_path, manifest_path = root / "package.json", root / "manifest.json"
            MODULE.write_package(package, package_path, manifest_path, root)
            report = MODULE.verify_package(package_path, manifest_path, root)
            self.assertTrue(report["ok"])
            self.assertTrue(report["integrity_ok"])
            self.assertFalse(report["freeze_ready"])
            self.assertEqual(report["freeze_status"], "BLOCKED")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root), "--verify", str(package_path), str(manifest_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            output = json.loads(result.stdout)
            self.assertTrue(output["integrity_ok"])
            self.assertFalse(output["freeze_ready"])

    def test_blocked_cli_returns_nonzero_and_writes_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, manifest = root / "package.json", root / "manifest.json"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(ROOT), "--runtime-contract", str(root / "missing-contract.json"), "--runtime-config", str(root / "missing-config.json"), "--container-image", str(root / "missing-image.json"), "--corpus-manifest", str(root / "missing-corpus.json"), "--output", str(output), "--manifest-output", str(manifest)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(output.is_file())
            self.assertTrue(manifest.is_file())


if __name__ == "__main__":
    unittest.main()
