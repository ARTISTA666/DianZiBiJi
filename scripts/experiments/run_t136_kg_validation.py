"""Run frozen KG inputs against isolated Rust API; never implements extraction."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import unicodedata
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
CONTENT = {"uses_reagent", "uses_instrument", "uses_sample", "produces_result"}
META = {"has_note", "created_by", "has_experiment_type"}
REVISION = "b6cd3a24f6edb5bdf971d8d76cc7635139b32954"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def normalize(label: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", label).casefold().split())


def verify_freeze(work: Path) -> dict:
    manifest_path = work / "freeze-manifest.json"
    if sha(manifest_path) != (work / "freeze.sha256").read_text().strip():
        raise ValueError("freeze manifest drift")
    manifest = json.loads(manifest_path.read_text())
    required = {"scripts/experiments/run_t136_kg_validation.py",
                "docs/experiments/kg-heldout-T136-protocol-v1.md",
                str((work / "inputs" / "cases.json").resolve().relative_to(ROOT)),
                str((work / "inputs" / "operator.json").resolve().relative_to(ROOT))}
    if not required.issubset({item["path"] for item in manifest["files"]}):
        raise ValueError("missing required freeze entries")
    for item in manifest["files"]:
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("frozen input drift: " + item["path"])
    return manifest


def key(row: dict) -> tuple[str, ...]:
    return tuple(normalize(str(row[k])) for k in (
        "record_id", "source_type", "source_label", "source_identity",
        "relation_type", "target_type", "target_label", "target_identity"))


def score(expected: list[dict], actual: list[dict]) -> dict:
    gold = {key(row) for row in expected}
    counts = Counter(key(row) for row in actual)
    pred = set(counts)
    tp, fp, fn = len(gold & pred), len(pred - gold), len(gold - pred)
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        "exact": gold == pred,
        "raw_row_count": len(actual),
        "duplicate_relation_ids": len([r for r in actual if "relation_id" in r]) - len({r["relation_id"] for r in actual if "relation_id" in r}),
        "duplicate_rows": sum(n - 1 for n in counts.values()),
        "false_positives": sorted(pred - gold),
        "false_negatives": sorted(gold - pred),
    }


def decode_graph(graph: dict, item: dict, project_id: int, note_id: int, owner_id: int) -> tuple[list[dict], list[dict]]:
    if graph["project_id"] != project_id or len({e["id"] for e in graph["entities"]}) != len(graph["entities"]):
        raise ValueError("graph integrity mismatch")
    entities = {e["id"]: e for e in graph["entities"]}
    rows, excluded = [], []
    identities = {("project", project_id): item["project_name"], ("note", note_id): item["record_id"], ("user", owner_id): "operator"}
    def identity(entity: dict) -> str:
        kind = entity["entity_type"]
        if kind not in {"project", "note", "user"}:
            return ""
        if entity.get("source_type") != kind:
            return "unmapped-origin:" + str(entity.get("source_type"))
        return identities.get((kind, entity.get("source_id")), "unmapped:" + str(entity.get("source_id")))
    for relation in graph["relations"]:
        if relation["project_id"] != project_id or relation.get("source_id") != note_id or relation.get("source_type") not in {"note", "note_extraction"}:
            raise ValueError("unexpected graph provenance")
        kind = relation["relation_type"]
        if kind in META | CONTENT and relation["source_type"] != ("note" if kind in META else "note_extraction"):
            raise ValueError("relation origin mismatch")
        source = entities[relation["source_entity_id"]]
        target = entities[relation["target_entity_id"]]
        if source["project_id"] != project_id or target["project_id"] != project_id:
            raise ValueError("cross-project entity")
        row = {
            "record_id": item["record_id"], "source_type": source["entity_type"],
            "source_label": source["label"], "source_identity": identity(source),
            "relation_type": relation["relation_type"], "target_type": target["entity_type"],
            "target_label": target["label"], "target_identity": identity(target),
            "relation_id": relation["id"], "origin_type": relation["source_type"],
            "confidence": relation["confidence"], "properties": relation["properties"],
        }
        if row["relation_type"] in CONTENT | META:
            rows.append(row)
        else:
            excluded.append(row)
    return rows, excluded


def validate_cases(items: list[dict]) -> None:
    pairs = [(item["arm"], item["record_id"]) for item in items]
    if len(pairs) != len(set(pairs)):
        raise ValueError("duplicate input identity")
    if {r for a, r in pairs if a == "body"} != {r for a, r in pairs if a == "fields"}:
        raise ValueError("unpaired input arms")
    for item in items:
        references = item["expected"]
        if any(r["record_id"] != item["record_id"] or r["relation_type"] not in META | CONTENT for r in references):
            raise ValueError("invalid reference scope")
        if len({key(r) for r in references}) != len(references):
            raise ValueError("duplicate reference key")
        metadata = [r["relation_type"] for r in references if r["relation_type"] in META]
        if Counter(metadata) != Counter(META):
            raise ValueError("metadata reference must contain exactly three relations")


class Api:
    def __init__(self, base: str, work: Path):
        self.base, self.work, self.token, self.counter = base, work, None, 0

    def request(self, path: str, payload: dict | None = None) -> dict:
        method = "GET" if payload is None else "POST"
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        data = None if payload is None else json.dumps(payload).encode()
        self.counter += 1
        log = {"utc": datetime.now(timezone.utc).isoformat(), "path": path, "method": method,
               "request": {"username": payload["username"], "password": "REDACTED"} if path == "/auth/login" else payload}
        try:
            with urllib.request.urlopen(urllib.request.Request(self.base + path, data=data, headers=headers), timeout=45) as response:
                result = json.load(response)
                log.update(status=response.status, response={"authenticated": True} if path == "/auth/login" else result)
            return result
        except Exception as error:
            log["error"] = str(error)
            raise
        finally:
            save(self.work / "http" / f"{self.counter:04d}.json", log)


def summarize(items: list[dict], observations: list[dict]) -> dict:
    result = {}
    for arm in sorted({item["arm"] for item in items}):
        selected = [item for item in items if item["arm"] == arm]
        arm_result = {}
        for group, kinds in [("content", CONTENT), ("metadata", META), ("all", CONTENT | META)]:
            expected, actual, individual = [], [], []
            for item in selected:
                observed = next(o for o in observations if o["record_id"] == item["record_id"] and o["arm"] == arm)
                e = [r for r in item["expected"] if r["relation_type"] in kinds]
                a = [r for r in observed["relations"] if r["relation_type"] in kinds]
                expected.extend(e); actual.extend(a)
                individual.append({"record_id": item["record_id"], **score(e, a)})
            aggregate = score(expected, actual)
            nonempty = [r["f1"] for r in individual if r["f1"] is not None]
            aggregate.update(note_count=len(selected), exact_note_count=sum(r["exact"] for r in individual),
                             macro_f1=sum(nonempty) / len(nonempty) if nonempty else None,
                             macro_nonempty_count=len(nonempty), per_note=individual)
            arm_result[group] = aggregate
        arm_result["by_relation"] = {kind: score(
            [r for item in selected for r in item["expected"] if r["relation_type"] == kind],
            [r for o in observations if o["arm"] == arm for r in o["relations"] if r["relation_type"] == kind]
        ) for kind in sorted(CONTENT | META)}
        arm_result["out_of_scope"] = dict(Counter(r["relation_type"] for o in observations if o["arm"] == arm for r in o["out_of_scope"]))
        result[arm] = arm_result
    return result


def rescore(work: Path) -> dict:
    """Recompute from saved raw graphs, rather than trusting saved relation lists."""
    verify_freeze(work)
    items = json.loads((work / "inputs" / "cases.json").read_text())
    validate_cases(items)
    raw = json.loads((work / "run" / "official" / "observations.json").read_text())
    owner_id = json.loads((work / "inputs" / "operator.json").read_text())["id"]
    raw_index = {(o["arm"], o["record_id"]): o for o in raw}
    if len(raw_index) != len(raw) or set(raw_index) != {(i["arm"], i["record_id"]) for i in items}:
        raise ValueError("saved output/input identity mismatch")
    observations = []
    for item in items:
        observed = raw_index[(item["arm"], item["record_id"])]
        rows, excluded = decode_graph(observed["graph"], item, observed["project_id"], observed["note_id"], owner_id)
        observations.append(observed | {"relations": rows, "out_of_scope": excluded})
    return summarize(items, observations)


def run(work: Path, base: str) -> None:
    manifest = verify_freeze(work)
    output = work / "run" / "official"
    if output.exists():
        raise ValueError("refuse to overwrite official run")
    output.mkdir(parents=True)
    api = Api(base, output)
    ready = api.request("/ready")
    if ready.get("revision") != REVISION or ready.get("status") != "ready":
        raise ValueError("runtime revision/ready mismatch")
    auth = api.request("/auth/login", {"username": "t136-admin", "password": "t136-local-admin-only"})
    api.token = auth["access_token"]
    operator = api.request("/auth/me")
    if operator != json.loads((work / "inputs" / "operator.json").read_text()):
        raise ValueError("operator drift")
    items = json.loads((work / "inputs" / "cases.json").read_text())
    validate_cases(items)
    projects, observations = {}, []
    for item in items:
        name = item["project_name"]
        if name not in projects:
            project = api.request("/projects", {"name": name, "approval_enabled": True})
            projects[name] = project["id"]
        project_id = projects[name]
        note = api.request(f"/projects/{project_id}/notes", item["payload"])
        note_id = note["id"]
        api.request(f"/notes/{note_id}/submit", {})
        approved = api.request(f"/notes/{note_id}/approve", {"comment": "T136 isolated functional test"})
        if approved["status"] != "approved":
            raise ValueError("approval state mismatch")
        graph = api.request(f"/notes/{note_id}/kg/graph")
        relations, excluded = decode_graph(graph, item, project_id, note_id, operator["id"])
        observations.append({"arm": item["arm"], "record_id": item["record_id"], "project_id": project_id,
                             "note_id": note_id, "graph": graph, "relations": relations, "out_of_scope": excluded})
        save(output / "observations.json", observations)
    save(output / "metrics.json", summarize(items, observations))
    repeats = []
    for item, observed in zip(items, observations):
        extraction = api.request(f"/notes/{observed['note_id']}/kg/extract", {"rebuild": True})
        graph = api.request(f"/notes/{observed['note_id']}/kg/graph")
        if (extraction["status"], extraction["project_id"], extraction["note_id"], extraction["triggered_by"]) != ("completed", observed["project_id"], observed["note_id"], operator["id"]):
            raise ValueError("rebuild status/provenance mismatch")
        if extraction["extracted_relations"] != len({r["id"] for r in graph["relations"]}):
            raise ValueError("rebuild relation count mismatch")
        rows, excluded = decode_graph(graph, item, observed["project_id"], observed["note_id"], operator["id"])
        comparison = score(observed["relations"], rows)
        repeats.append({"record_id": item["record_id"], "arm": item["arm"], "extract_response": extraction,
                        "graph": graph, "relations": rows, "out_of_scope": excluded, "comparison": comparison,
                        "content_stable": score([r for r in observed["relations"] if r["relation_type"] in CONTENT], [r for r in rows if r["relation_type"] in CONTENT])["exact"],
                        "metadata_stable": score([r for r in observed["relations"] if r["relation_type"] in META], [r for r in rows if r["relation_type"] in META])["exact"],
                        "out_of_scope_stable": score(observed["out_of_scope"], excluded)["exact"]})
        save(output / "rebuild-check.json", repeats)
    verify_freeze(work)
    save(output / "completion.json", {"finished_utc": datetime.now(timezone.utc).isoformat(),
         "freeze_sha256": sha(work / "freeze-manifest.json"), "revision": ready["revision"],
         "case_count": len(items), "rebuild_stable_count": sum(r["comparison"]["exact"] for r in repeats),
         "frozen_at": manifest["frozen_at"]})
    print(json.dumps({arm: {group: {k: v for k, v in values.items() if k in {"tp", "fp", "fn", "precision", "recall", "f1", "exact_note_count", "note_count"}} for group, values in groups.items() if group in {"content", "metadata", "all"}} for arm, groups in summarize(items, observations).items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--base", default="http://127.0.0.1:18036")
    parser.add_argument("--rescore", action="store_true")
    arguments = parser.parse_args()
    if arguments.rescore:
        print(json.dumps(rescore(arguments.work), ensure_ascii=False, indent=2))
    else:
        run(arguments.work, arguments.base)
