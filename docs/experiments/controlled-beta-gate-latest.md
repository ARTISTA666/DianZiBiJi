# Controlled beta launch gate

Result: FAIL

人工评审不是受控试运行的前置条件；生产安全与自动化门禁仍是前置条件。

| Check | Status | Detail |
| --- | --- | --- |
| evidence report passed: main-maturity-gate-latest.json | FAIL | `{"exists": true, "failures": [{"actual": ["api_runtime", "corpus_sha256", "embedding_backend", "embedding_dimension", "embedding_model", "embedding_model_sha256", "git_revision", "image_digest", "questions_sha256", "retrieval_parameters_sha256"], "expected": [], "group": "retrieval", "name": "retrieval evidence binding completeness", "operator": "==", "passed": false}, {"actual": "missing", "expected": "runtime evidence manifest", "group": "retrieval", "name": "retrieval runtime evidence manifest", "operator": "present", "passed": false}, {"actual": null, "expected": "rust-axum", "group": "retrieval", "name": "retrieval runtime", "operator": "==", "passed": false}, {"actual": false, "expected": true, "group": "retrieval", "name": "retrieval reproducibility", "operator": "==", "passed": false}, {"actual": null, "expected": "4721edb85c333e08d20e0a3301eb9ecba7787534fa0e088a790670f150180652", "group": "retrieval", "name": "retrieval parameters hash", "operator": "==", "passed": false}, {"actual": null, "expected": "ef12ac88e4bebb0ef8cba991f6496f08c612dd420ba75bd5fa93e080c796cb07", "group": "retrieval", "name": "retrieval corpus hash binding", "operator": "==", "passed": false}, {"actual": null, "expected": "f1f4f8e2726129cdf54e4c65cfcc09d6fb9314ca30498ccbd854533fc6f2fe4a", "group": "retrieval", "name": "retrieval question-set hash binding", "operator": "==", "passed": false}, {"actual": "skipped_non_production", "expected": "passed", "group": "system", "name": "production config preflight", "operator": "==", "passed": false}, {"actual": false, "expected": true, "group": "evidence_manifest", "name": "maturity evidence manifest verified", "operator": "==", "passed": false}, {"actual": false, "expected": true, "group": "evidence_manifest", "name": "maturity evidence manifest matches current checkout", "operator": "==", "passed": false}, {"actual": ["output/release-evidence/rag-runtime-manifest.json"], "expected": [], "group": "evidence_manifest", "name": "maturity evidence manifest covers gate inputs", "operator": "==", "passed": false}], "passed": false, "scope": "full-system release-candidate maturity gate", "source": "/Users/yusong/Downloads/new/full-system/docs/experiments/main-maturity-gate-latest.json"}` |
| production configuration passed | FAIL | `{"checks": {"app_env_is_production": false, "app_revision_present": false, "bootstrap_admin_password_non_default": false, "deepseek_api_key_present": true, "postgres_password_non_default": false, "secret_key_non_default": false, "seed_demo_data_disabled": false}, "missing_checks": [], "source": "/Users/yusong/Downloads/new/full-system/docs/system-evidence/production-config-latest.json", "status": "skipped_non_production"}` |
| evidence report passed: tls-deployment-latest.json | FAIL | `{"exists": false, "failures": null, "passed": null, "scope": null, "source": "/Users/yusong/Downloads/new/full-system/docs/system-evidence/tls-deployment-latest.json"}` |
| evidence report passed: offsite-backup-latest.json | FAIL | `{"exists": false, "failures": null, "passed": null, "scope": null, "source": "/Users/yusong/Downloads/new/full-system/docs/system-evidence/offsite-backup-latest.json"}` |
| runtime endpoint healthy: http://127.0.0.1:8001/health | PASS | `{"body": "{\"status\":\"ok\"}", "header_ok": true, "status": 200, "url": "http://127.0.0.1:8001/health"}` |
| runtime endpoint healthy: http://127.0.0.1:8001/ready | PASS | `{"body": "{\"checks\":{\"database\":\"ok\",\"storage\":\"ok\"},\"revision\":\"unversioned\",\"status\":\"ready\"}", "header_ok": true, "status": 200, "url": "http://127.0.0.1:8001/ready"}` |
| Docker Compose configuration valid | PASS | `{"returncode": 0, "stderr": ""}` |

## Blockers

- evidence report passed: main-maturity-gate-latest.json
- production configuration passed
- evidence report passed: tls-deployment-latest.json
- evidence report passed: offsite-backup-latest.json
