from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_rag_confirmatory_experiment.py"
SPEC = importlib.util.spec_from_file_location("run_pilot_experiments", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(root: Path) -> dict[str, Path | str]:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    policy_dir = root / "scripts" / "confirmatory-policy"
    key = root / "authority-key"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
    allowed = policy_dir / "allowed_signers"
    allowed.parent.mkdir(parents=True, exist_ok=True)
    allowed.write_text(f"authority-1 {key.with_suffix('.pub').read_text(encoding='utf-8').strip()}\n", encoding="utf-8")
    trust = policy_dir / "trust-root-policy.json"
    write_json(trust, {"schema": "full-system.confirmatory-trust-root-v1", "namespace": "full-system.confirmatory.v1", "allowed_signers_sha256": digest(allowed), "approved_authorities": ["authority-1"]})
    tracked = root / "tracked.txt"
    tracked.write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "add", "scripts/confirmatory-policy", "tracked.txt"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=test@example.invalid", "-c", "user.name=test", "commit", "-qm", "fixture"], cwd=root, check=True)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()

    source = root / "agent-work" / "question-sets" / "p.json"
    write_json(source, {"document_status": "FROZEN", "formal_use_allowed": True, "questions": [{"question_id": "q-1", "project_id": "p", "question": "q"}]})
    corpus_source = root / "data" / "real" / "payload.txt"
    corpus_source.parent.mkdir(parents=True, exist_ok=True)
    corpus_source.write_text("ORIGINAL\n", encoding="utf-8")
    freeze = root / "agent-work" / "freeze" / "batch"
    question_manifest = freeze / "question-set-manifest.json"
    gold = freeze / "gold-facts.json"
    corpus = freeze / "corpus-manifest.json"
    questions = freeze / "questions.json"
    run_config = freeze / "run-config.json"
    analysis_config = freeze / "analysis-config.json"
    authority = freeze / "authority.json"
    signature = freeze / "authority.json.sig"
    setter = {"setter_id": "setter-1", "authority": "authority-1", "signed_at_utc": "2026-08-29T00:00:00Z"}
    write_json(question_manifest, {"status": "FROZEN", "formal_use_allowed": True, "external_setter": setter, "question_sets": [{"project_id": "p", "path": "agent-work/question-sets/p.json", "sha256": digest(source), "question_count": 1}]})
    write_json(gold, {"status": "FROZEN", "formal_use_allowed": True, "external_setter": setter, "gold_facts": []})
    write_json(corpus, {"status": "FROZEN", "formal_use_allowed": True, "external_setter": setter, "projects": {"p": {"formal_corpus_snapshot_hash": "b" * 64, "formal_graph_snapshot_hash": "c" * 64, "files": [{"path": "data/real/payload.txt", "sha256": digest(corpus_source)}]}}})
    write_json(questions, {"status": "FROZEN", "formal_use_allowed": True})
    write_json(run_config, {"status": "FROZEN", "formal_use_allowed": True})
    write_json(analysis_config, {"status": "FROZEN", "formal_use_allowed": True})
    runtime_contract = root / "docs" / "system-evidence" / "rust-runtime-contract-latest.json"
    write_json(runtime_contract, {"revision": head, "app_revision": head, "runtime_revision": head, "runtime": {"api_runtime": "rust-axum"}})
    image_digest = "sha256:" + "d" * 64
    write_json(root / "docs" / "system-evidence" / "container-image-latest.json", {"app_revision": head, "runtime_revision": head, "image_digest": image_digest, "image": {"image_id": image_digest}})
    write_json(authority, {"authority_id": "authority-1", "setter_id": "setter-1", "signed_at_utc": setter["signed_at_utc"], "namespace": "full-system.confirmatory.v1", "allowed_signers_sha256": digest(allowed), "trust_root_policy_sha256": digest(trust)})
    subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", str(key), "-n", "full-system.confirmatory.v1", str(authority)], check=True)
    freeze_manifest = freeze / "freeze-manifest.json"
    write_json(freeze_manifest, {"status": "FROZEN_EXTERNAL_SETTER", "formal_use_allowed": True, "provenance": {**setter, "external_setter_id": setter["setter_id"], "external_setter_authority": setter["authority"], "external_setter_signed_at_utc": setter["signed_at_utc"], "external_authority_artifact": "agent-work/freeze/batch/authority.json", "external_authority_sha256": digest(authority), "external_authority_signature": "agent-work/freeze/batch/authority.json.sig", "external_authority_signature_sha256": digest(signature), "allowed_signers": "scripts/confirmatory-policy/allowed_signers", "allowed_signers_sha256": digest(allowed), "trust_root_policy": "scripts/confirmatory-policy/trust-root-policy.json", "trust_root_policy_sha256": digest(trust)}, "design": {"projects": ["p"], "modes": list(MODULE.MODES), "repetitions": 1}, "runtime_binding": {"app_revision": head, "runtime_revision": head, "image_digest": image_digest}, "question_set_sha256": {"p": digest(source)}, "file_sha256": {"question-set-manifest.json": digest(question_manifest), "gold-facts.json": digest(gold), "corpus-manifest.json": digest(corpus), "questions.json": digest(questions), "run-config.json": digest(run_config), "analysis-config.json": digest(analysis_config), "authority.json": digest(authority), "authority.json.sig": digest(signature), "scripts/confirmatory-policy/allowed_signers": digest(allowed), "scripts/confirmatory-policy/trust-root-policy.json": digest(trust)}})
    return {"root": root, "freeze": freeze_manifest, "runs": root / "agent-work" / "runs", "head": head, "authority_key": key, "signature": signature, "allowed": allowed}


class ConfirmatoryRunnerPreflightTests(unittest.TestCase):
    def call_preflight(self, paths: dict[str, Path | str], keys: list[str] | None = None):
        return MODULE.confirmatory_preflight(keys or ["p"], root=paths["root"], freeze_manifest_path=paths["freeze"], runs_dir=paths["runs"], current_revision=paths["head"])

    def assert_create_blocked_without_post(self, paths: dict[str, Path | str]) -> None:
        class CountingTransport(MODULE.httpx.BaseTransport):
            def __init__(self): self.posts = []
            def handle_request(self, request):
                if request.method == "POST": self.posts.append(request.url.path)
                return MODULE.httpx.Response(500, request=request)

        transport = CountingTransport()
        api = object.__new__(MODULE.ApiClient)
        api.client = MODULE.httpx.Client(transport=transport, base_url="http://test")
        original = (MODULE.ROOT, MODULE.FREEZE_MANIFEST, MODULE.FREEZE_DIR, MODULE.RUNS_DIR)
        MODULE.ROOT = paths["root"]
        MODULE.FREEZE_MANIFEST = paths["freeze"]
        MODULE.FREEZE_DIR = paths["freeze"].parent
        MODULE.RUNS_DIR = paths["runs"]
        try:
            with self.assertRaises(MODULE.PreflightError):
                MODULE.create_confirmatory_experiment(api, "p", 1, "run", 1)
            self.assertEqual(transport.posts, [])
        finally:
            MODULE.ROOT, MODULE.FREEZE_MANIFEST, MODULE.FREEZE_DIR, MODULE.RUNS_DIR = original
            api.client.close()

    def assert_second_status_mutation_blocked(self, paths: dict[str, Path | str], mutate) -> None:
        class MutatingTransport(MODULE.httpx.BaseTransport):
            def __init__(self): self.status_gets = 0; self.posts = []
            def handle_request(self, request):
                if request.method == "GET" and request.url.path.endswith("/rag/status"):
                    self.status_gets += 1
                    if self.status_gets == 2: mutate()
                    return MODULE.httpx.Response(200, json={"corpus_snapshot": {"corpus_snapshot_hash": "b" * 64, "graph_snapshot_hash": "c" * 64}}, request=request)
                if request.method == "POST":
                    self.posts.append(request.url.path)
                    return MODULE.httpx.Response(200, json={"id": 1, "status": "queued"}, request=request)
                return MODULE.httpx.Response(500, request=request)

        transport = MutatingTransport()
        api = object.__new__(MODULE.ApiClient)
        api.client = MODULE.httpx.Client(transport=transport, base_url="http://test")
        original = (MODULE.ROOT, MODULE.FREEZE_MANIFEST, MODULE.FREEZE_DIR, MODULE.RUNS_DIR)
        MODULE.ROOT = paths["root"]
        MODULE.FREEZE_MANIFEST = paths["freeze"]
        MODULE.FREEZE_DIR = paths["freeze"].parent
        MODULE.RUNS_DIR = paths["runs"]
        try:
            with self.assertRaises(MODULE.PreflightError):
                MODULE.create_confirmatory_experiment(api, "p", 1, "run", 1)
            self.assertEqual(transport.status_gets, 2)
            self.assertEqual(transport.posts, [])
        finally:
            MODULE.ROOT, MODULE.FREEZE_MANIFEST, MODULE.FREEZE_DIR, MODULE.RUNS_DIR = original
            api.client.close()

    def test_valid_ssh_authority_passes_to_next_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = fixture(Path(directory))
            result = self.call_preflight(paths)
            self.assertEqual(result.head, paths["head"])

    def test_valid_create_posts_verified_payload_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = fixture(Path(directory))
            root = Path(directory)
            class Transport(MODULE.httpx.BaseTransport):
                def __init__(self): self.status_gets = 0; self.posts = []
                def handle_request(self, request):
                    if request.method == "GET" and request.url.path.endswith("/rag/status"):
                        self.status_gets += 1
                        return MODULE.httpx.Response(200, json={"corpus_snapshot": {"corpus_snapshot_hash": "b" * 64, "graph_snapshot_hash": "c" * 64}}, request=request)
                    if request.method == "POST":
                        self.posts.append(json.loads(request.content))
                        return MODULE.httpx.Response(200, json={"id": 1, "status": "queued"}, request=request)
                    return MODULE.httpx.Response(500, request=request)

            transport = Transport()
            api = object.__new__(MODULE.ApiClient)
            api.client = MODULE.httpx.Client(transport=transport, base_url="http://test")
            original = (MODULE.ROOT, MODULE.FREEZE_MANIFEST, MODULE.FREEZE_DIR, MODULE.RUNS_DIR)
            MODULE.ROOT = root
            MODULE.FREEZE_MANIFEST = paths["freeze"]
            MODULE.FREEZE_DIR = paths["freeze"].parent
            MODULE.RUNS_DIR = paths["runs"]
            try:
                run, questions = MODULE.create_confirmatory_experiment(api, "p", 1, "run", 1)
                self.assertEqual(run["id"], 1)
                self.assertEqual(questions, ["q"])
                self.assertEqual(transport.status_gets, 2)
                self.assertEqual(len(transport.posts), 1)
                self.assertEqual(transport.posts[0]["questions"], ["q"])
            finally:
                MODULE.ROOT, MODULE.FREEZE_MANIFEST, MODULE.FREEZE_DIR, MODULE.RUNS_DIR = original
                api.client.close()

    def test_authority_attacks_never_reach_experiment_post(self) -> None:
        for attack in ("artifact", "policy", "signature"):
            with tempfile.TemporaryDirectory() as directory:
                paths = fixture(Path(directory))
                root = Path(directory)
                if attack == "artifact":
                    authority = root / "agent-work/freeze/batch/authority.json"
                    authority.write_text(authority.read_text(encoding="utf-8").replace("authority-1", "authority-2"), encoding="utf-8")
                elif attack == "policy":
                    allowed = Path(paths["allowed"])
                    allowed.write_text(allowed.read_text(encoding="utf-8") + "# tampered\n", encoding="utf-8")
                else:
                    paths["signature"].unlink()
                    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(root / "other-key")], check=True)
                    subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", str(root / "other-key"), "-n", "full-system.confirmatory.v1", str(root / "agent-work/freeze/batch/authority.json")], check=True)
                    manifest_path = Path(paths["freeze"])
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest["provenance"]["external_authority_signature_sha256"] = digest(paths["signature"])
                    manifest["file_sha256"]["authority.json.sig"] = digest(paths["signature"])
                    write_json(manifest_path, manifest)

                class CountingTransport(MODULE.httpx.BaseTransport):
                    def __init__(self): self.posts = []
                    def handle_request(self, request):
                        if request.method == "POST": self.posts.append(request.url.path)
                        return MODULE.httpx.Response(500, request=request)

                transport = CountingTransport()
                api = object.__new__(MODULE.ApiClient)
                api.client = MODULE.httpx.Client(transport=transport, base_url="http://test")
                original = (MODULE.ROOT, MODULE.FREEZE_MANIFEST, MODULE.FREEZE_DIR, MODULE.RUNS_DIR)
                MODULE.ROOT = root
                MODULE.FREEZE_MANIFEST = paths["freeze"]
                MODULE.FREEZE_DIR = paths["freeze"].parent
                MODULE.RUNS_DIR = paths["runs"]
                try:
                    with self.assertRaises(MODULE.PreflightError):
                        MODULE.create_confirmatory_experiment(api, "p", 1, "run", 1)
                    self.assertEqual(transport.posts, [], attack)
                finally:
                    MODULE.ROOT, MODULE.FREEZE_MANIFEST, MODULE.FREEZE_DIR, MODULE.RUNS_DIR = original
                    api.client.close()

    def test_local_gate_attacks_never_reach_experiment_post(self) -> None:
        for attack in ("draft", "status", "setter", "corpus", "question", "image", "output", "dirty"):
            with tempfile.TemporaryDirectory() as directory:
                paths = fixture(Path(directory))
                root = Path(directory)
                if attack in {"draft", "status", "setter"}:
                    manifest_path = Path(paths["freeze"])
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    if attack == "draft": manifest["formal_use_allowed"] = False
                    if attack == "status": manifest["status"] = "AGENT_DRAFT"
                    if attack == "setter": manifest["provenance"].pop("external_setter_id")
                    write_json(manifest_path, manifest)
                elif attack == "corpus":
                    (root / "data/real/payload.txt").write_text("TAMPERED\n", encoding="utf-8")
                elif attack == "question":
                    write_json(root / "agent-work/question-sets/p.json", {"formal_use_allowed": True, "status": "FROZEN", "questions": [{"question": "missing bindings"}]})
                elif attack == "image":
                    image = root / "docs/system-evidence/container-image-latest.json"
                    payload = json.loads(image.read_text(encoding="utf-8"))
                    payload["image_digest"] = "sha256:" + "e" * 64
                    write_json(image, payload)
                elif attack == "output":
                    output = root / "agent-work/runs/p"
                    output.mkdir(parents=True)
                    (output / "reused").write_text("x\n", encoding="utf-8")
                else:
                    (root / "tracked.txt").write_text("dirty\n", encoding="utf-8")
                self.assert_create_blocked_without_post(paths)

    def test_second_status_get_local_toctou_never_reaches_experiment_post(self) -> None:
        for attack in ("qset", "gold", "run", "analysis", "corpus", "policy", "image", "dirty"):
            with tempfile.TemporaryDirectory() as directory:
                paths = fixture(Path(directory))
                root = Path(directory)
                if attack == "qset":
                    target, value = root / "agent-work/question-sets/p.json", {"formal_use_allowed": True, "status": "FROZEN", "questions": [{"question_id": "q-1", "project_id": "p", "question": "changed"}]}
                    mutate = lambda: write_json(target, value)
                elif attack == "gold":
                    target = root / "agent-work/freeze/batch/gold-facts.json"
                    mutate = lambda: target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
                elif attack == "run":
                    target = root / "agent-work/freeze/batch/run-config.json"
                    mutate = lambda: target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
                elif attack == "analysis":
                    target = root / "agent-work/freeze/batch/analysis-config.json"
                    mutate = lambda: target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
                elif attack == "corpus":
                    target = root / "data/real/payload.txt"
                    mutate = lambda: target.write_text("TAMPERED\n", encoding="utf-8")
                elif attack == "policy":
                    target = Path(paths["allowed"])
                    mutate = lambda: target.write_text(target.read_text(encoding="utf-8") + "# tampered\n", encoding="utf-8")
                elif attack == "image":
                    target = root / "docs/system-evidence/container-image-latest.json"
                    def mutate():
                        payload = json.loads(target.read_text(encoding="utf-8"))
                        payload["image_digest"] = "sha256:" + "e" * 64
                        write_json(target, payload)
                else:
                    target = root / "tracked.txt"
                    mutate = lambda: target.write_text("dirty\n", encoding="utf-8")
                self.assert_second_status_mutation_blocked(paths, mutate)

    def test_other_key_signature_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = fixture(Path(directory))
            other = Path(directory) / "other-key"
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(other)], check=True)
            paths["signature"].unlink()
            subprocess.run(["ssh-keygen", "-q", "-Y", "sign", "-f", str(other), "-n", "full-system.confirmatory.v1", str(Path(directory) / "agent-work/freeze/batch/authority.json")], check=True)
            manifest_path = Path(paths["freeze"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["provenance"]["external_authority_signature_sha256"] = digest(paths["signature"])
            manifest["file_sha256"]["authority.json.sig"] = digest(paths["signature"])
            write_json(manifest_path, manifest)
            with self.assertRaisesRegex(MODULE.PreflightError, "authority signature verification failed"):
                self.call_preflight(paths)

    def test_authority_artifact_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = fixture(Path(directory))
            authority = Path(directory) / "agent-work/freeze/batch/authority.json"
            authority.write_text(authority.read_text(encoding="utf-8").replace("authority-1", "authority-2"), encoding="utf-8")
            with self.assertRaises(MODULE.PreflightError):
                self.call_preflight(paths)

    def test_tracked_policy_change_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = fixture(Path(directory))
            allowed = Path(paths["allowed"])
            allowed.write_text(allowed.read_text(encoding="utf-8") + "# tampered\n", encoding="utf-8")
            with self.assertRaises(MODULE.PreflightError):
                self.call_preflight(paths)

    def test_agent_draft_and_unknown_status_are_rejected(self) -> None:
        for field, value in (("formal_use_allowed", False), ("status", "BOGUS")):
            with tempfile.TemporaryDirectory() as directory:
                paths = fixture(Path(directory))
                manifest = json.loads(Path(paths["freeze"]).read_text(encoding="utf-8"))
                manifest[field] = value
                write_json(Path(paths["freeze"]), manifest)
                with self.assertRaises(MODULE.PreflightError):
                    self.call_preflight(paths)

    def test_corpus_tamper_question_sha_and_duplicate_project_reject(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = fixture(Path(directory))
            Path(directory, "data/real/payload.txt").write_text("TAMPERED\n", encoding="utf-8")
            with self.assertRaises(MODULE.PreflightError):
                self.call_preflight(paths)
        with tempfile.TemporaryDirectory() as directory:
            paths = fixture(Path(directory))
            with self.assertRaises(MODULE.PreflightError):
                self.call_preflight(paths, ["p", "p"])

    def test_tracked_dirty_image_result_and_malformed_question_reject(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = fixture(Path(directory))
            Path(directory, "tracked.txt").write_text("dirty\n", encoding="utf-8")
            with self.assertRaises(MODULE.PreflightError):
                self.call_preflight(paths)
        with tempfile.TemporaryDirectory() as directory:
            paths = fixture(Path(directory))
            image = Path(directory, "docs/system-evidence/container-image-latest.json")
            payload = json.loads(image.read_text(encoding="utf-8")); payload["image_digest"] = "sha256:" + "e" * 64
            write_json(image, payload)
            with self.assertRaises(MODULE.PreflightError):
                self.call_preflight(paths)
        with tempfile.TemporaryDirectory() as directory:
            paths = fixture(Path(directory))
            source = Path(directory, "agent-work/question-sets/p.json")
            write_json(source, {"document_status": "FROZEN", "formal_use_allowed": True, "questions": [{"question": 7}]})
            with self.assertRaises(MODULE.PreflightError):
                self.call_preflight(paths)

    def test_direct_runner_does_not_accept_caller_binding(self) -> None:
        class CountingTransport(MODULE.httpx.BaseTransport):
            def __init__(self): self.posts = []
            def handle_request(self, request):
                if request.method == "POST": self.posts.append(request.url.path)
                return MODULE.httpx.Response(500, request=request)
        transport = CountingTransport()
        api = object.__new__(MODULE.ApiClient)
        api.client = MODULE.httpx.Client(transport=transport, base_url="http://test")
        try:
            with self.assertRaises(TypeError):
                MODULE.run_project(api, "p", {"project_name": "p", "seed": 1}, "run", object())
            self.assertEqual(transport.posts, [])
        finally:
            api.client.close()

    def test_main_current_real_freeze_blocks_before_client(self) -> None:
        original = {name: getattr(MODULE, name) for name in ("ROOT", "FREEZE_MANIFEST", "RUNS_DIR", "PROJECTS", "ApiClient")}
        calls = []
        class ForbiddenApiClient:
            def __init__(self): calls.append("client")
        try:
            MODULE.ApiClient = ForbiddenApiClient
            old_argv = sys.argv; sys.argv = [str(SCRIPT), "gse291942_arabidopsis_heat"]
            try:
                self.assertEqual(MODULE.main(), 1)
            finally:
                sys.argv = old_argv
        finally:
            for name, value in original.items(): setattr(MODULE, name, value)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
