"""Finite isolated CRUD smoke. This is not a capacity or long-duration test."""
from pathlib import Path
from functools import partial
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
import httpx

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "scripts/ops"))
from load_smoke import run
from soak_smoke import run_soak

def save(name, value):
    with (OUT / name).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

def command(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()

def database_counts(project_id, note_id):
    query = f"""SELECT json_build_object(
      'notes', (SELECT count(*) FROM experiment_notes WHERE project_id={project_id}),
      'versions', (SELECT count(*) FROM note_versions v JOIN experiment_notes n ON n.id=v.note_id WHERE n.project_id={project_id}),
      'fixture_versions', (SELECT count(*) FROM note_versions WHERE note_id={note_id}),
      'note_audits', (SELECT count(*) FROM audit_logs a WHERE a.target_type='note' AND a.target_id IN (SELECT id FROM experiment_notes WHERE project_id={project_id})),
      'server_version', current_setting('server_version'),
      'database', current_database());"""
    return json.loads(command("docker", "exec", "eln-t148-e2e-db-1", "psql", "-U", "eln_e2e", "-d", "eln_e2e", "-At", "-c", query))

with httpx.Client(base_url="http://127.0.0.1:18000", timeout=15, trust_env=False) as client:
    login = client.post("/auth/login", json={"username":"admin", "password":"admin123"})
    login.raise_for_status()
    client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
    me = client.get("/auth/me"); me.raise_for_status()
    created = client.post("/projects", json={"name":"T148 synthetic mixed CRUD smoke", "description":"Isolated synthetic fixture; no scientific correctness data", "owner_user_id":me.json()["id"]})
    created.raise_for_status(); pid=created.json()["id"]
    payload={"title":"T148 synthetic draft", "experiment_type":"T148 synthetic", "fixed_fields_json":{"sample":["T148-A, atomic sample","T148-B"],"reagents":["T148 synthetic reagent"]}, "content_json":{"text":"Synthetic evidence fixture for bounded request validation."}}
    note=client.post(f"/projects/{pid}/notes", json=payload); note.raise_for_status(); nid=note.json()["id"]
    initialized=client.post(f"/projects/{pid}/rag/init"); initialized.raise_for_status()
    plan=[{"path":"/projects"}, {"path":f"/projects/{pid}/notes?limit=20"}, {"path":f"/projects/{pid}/rag/status"},
          {"method":"POST", "path":f"/projects/{pid}/notes", "json":payload},
          {"method":"PATCH", "path":f"/notes/{nid}", "json":{"content_json":{"text":"T148 synthetic updated draft"},"change_summary":"T148 bounded smoke"}}]
    identities={}
    for service in ("backend","frontend","db"):
        inspected=json.loads(command("docker", "inspect", f"eln-t148-e2e-{service}-1"))[0]
        identities[service]={"image":inspected["Image"],"configured_image":inspected["Config"]["Image"]}
    identity={"task":"T148", "captured_at":datetime.now(timezone.utc).isoformat(), "project":"eln-t148-e2e", "images":identities,
              "source_manifests":{name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in ("backend-build-inputs.json","frontend-build-inputs.json")},
              "host":{"system":platform.system(),"machine":platform.machine(),"processor":platform.processor(),"cpu_count":command("sysctl","-n","hw.logicalcpu"),"memory_bytes":command("sysctl","-n","hw.memsize")},
              "embedding":"hash mode from owned backend; no remote embeddings", "rate_limits":{"read_per_minute":10000,"write_per_minute":2000},
              "fixture":{"project_id":pid,"note_id":nid,"synthetic":True,"before":database_counts(pid,nid)},
              "request_mix":"60% reads, 20% create draft, 20% patch one draft; no approval or heavy upload", "scope":"Finite local container CRUD smoke, no capacity or production SLA conclusion"}
    save("mixed-request-plan.json",plan); save("mixed-identity.json",identity)
    load=run("http://127.0.0.1:18000","admin","admin123",200,8,request_plan=plan,identity=identity)
    save("mixed-load.json",load)
    with (OUT/"mixed-load-records.jsonl").open("x",encoding="utf-8") as stream:
        for record in load["records"]: stream.write(json.dumps(record,ensure_ascii=False)+"\n")
    after_load=database_counts(pid,nid); save("mixed-after-load.json",after_load)
    print(json.dumps({"phase":"load","requests":load["requests"],"successful":load["successful"],"p95_ms":load["p95_ms"],"after":after_load}),flush=True)
    soak=run_soak(api_base="http://127.0.0.1:18000",username="admin",password="admin123",requests=50,concurrency=8,duration_seconds=60,interval_seconds=10,
                  runner=partial(run,request_plan=plan,identity=identity))
    save("mixed-short-soak.json",soak)
    records=[record for cycle in soak["cycles"] for record in cycle["records"]]
    with (OUT/"mixed-short-soak-records.jsonl").open("x",encoding="utf-8") as stream:
        for record in records: stream.write(json.dumps(record,ensure_ascii=False)+"\n")
    after=database_counts(pid,nid); save("mixed-after-soak.json",after)
    posts=sum(r["method"]=="POST" and r["error"] is None for r in load["records"]+records)
    patches=sum(r["method"]=="PATCH" and r["error"] is None for r in load["records"]+records)
    before=identity["fixture"]["before"]
    validation={"total_records":len(load["records"])+len(records),"unique_request_ids":len({r["request_id"] for r in load["records"]+records}),
                "successful_posts":posts,"successful_patches":patches,"note_delta":after["notes"]-before["notes"],
                "version_delta":after["versions"]-before["versions"],"fixture_version_delta":after["fixture_versions"]-before["fixture_versions"],
                "all_requests_succeeded":not load["errors"] and soak["summary"]["ok"],
                "writes_match":after["notes"]-before["notes"]==posts and after["versions"]-before["versions"]==posts+patches and after["fixture_versions"]-before["fixture_versions"]==patches,
                "duration_seconds":soak["duration_seconds"],"target_duration_seconds":60,"bounded_only":True}
    save("mixed-validation.json",validation)
    print(json.dumps({"phase":"short_soak","summary":soak["summary"],"validation":validation}),flush=True)
    if not validation["all_requests_succeeded"] or not validation["writes_match"]: raise SystemExit(1)
