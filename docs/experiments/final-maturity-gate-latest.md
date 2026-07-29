# Final maturity gate

Result: FAIL

| Check | Status | Detail |
| --- | --- | --- |
| internal release-candidate gate passed | FAIL | `{"age_hours": 2.598972222222222e-05, "empty_or_invalid_required_groups": [], "evidence_level": "internal automated gate; not independent human review", "failures_empty": false, "fresh": true, "generated_at_present": true, "max_age_hours": 168, "passed": false, "required_groups_present": ["agent", "evidence_manifest", "rag_experiment", "retrieval", "system"], "scope": "full-system release-candidate maturity gate", "source": "/Users/yusong/Downloads/new/full-system/docs/experiments/main-maturity-gate-latest.json", "source_revision": null, "source_revision_valid": false, "timestamp_valid": true}` |
| production configuration was checked in production mode | FAIL | `{"embedded": {"checked_keys": ["APP_ENV", "APP_REVISION", "BOOTSTRAP_ADMIN_PASSWORD", "DEEPSEEK_API_KEY", "POSTGRES_PASSWORD", "SECRET_KEY", "SEED_DEMO_DATA"], "checks": {"app_env_is_production": true, "app_revision_present": true, "bootstrap_admin_password_non_default": true, "deepseek_api_key_present": true, "postgres_password_non_default": true, "secret_key_non_default": true, "seed_demo_data_disabled": true}, "env_file_sha256_present": true, "source": "/Users/yusong/Downloads/new/full-system/docs/system-evidence/validation-results.json", "status": "passed"}, "same_checked_keys": false, "same_checks": false, "same_env_file_sha256": false, "standalone": {"checked_keys": [], "checks": {"app_env_is_production": false, "app_revision_present": false, "bootstrap_admin_password_non_default": false, "deepseek_api_key_present": true, "postgres_password_non_default": false, "secret_key_non_default": false, "seed_demo_data_disabled": false}, "env_file_sha256_present": false, "source": "/Users/yusong/Downloads/new/full-system/docs/system-evidence/production-config-latest.json", "status": "skipped_non_production"}}` |
| external confirmatory human-review freeze passed | FAIL | `"missing: /Users/yusong/Downloads/new/full-system/docs/experiments/confirmatory-human-review-freeze.json"` |
| long soak evidence passed | FAIL | `{"checks": [{"name": "report ok", "passed": true}, {"actual": 30, "expected": 14400, "name": "duration seconds", "passed": false}, {"actual": 0, "expected": 1000, "name": "request count", "passed": false}, {"actual": 0, "name": "cycle records present", "passed": false}, {"actual": null, "expected": 0, "name": "summary cycle count matches records", "passed": false}, {"actual": 0, "expected": 0, "name": "summary requests match cycles", "passed": true}, {"actual": 7, "expected": 0, "name": "summary successful match cycles", "passed": false}, {"actual": 0, "name": "no errors", "passed": true}, {"actual": 0, "expected": 0, "name": "cycle errors match summary", "passed": true}, {"actual": 0, "expected": 0, "name": "all cycle requests succeeded", "passed": false}, {"name": "p95 latency present", "passed": false}, {"actual": 0, "expected": 2000, "name": "p95 latency ms", "passed": false}, {"actual": 0, "expected": 0, "name": "all cycle p95 latency present", "passed": false}, {"actual": 0, "expected": 2000, "name": "all cycle p95 latency ms", "passed": false}], "ok": false, "source": "/Users/yusong/Downloads/new/full-system/docs/system-evidence/long-soak-latest.json"}` |
| real TLS deployment evidence passed | FAIL | `"missing: /Users/yusong/Downloads/new/full-system/docs/system-evidence/tls-deployment-latest.json"` |
| offsite encrypted backup evidence passed | FAIL | `"missing: /Users/yusong/Downloads/new/full-system/docs/system-evidence/offsite-backup-latest.json"` |
| final maturity evidence manifest verified | FAIL | `"missing: /Users/yusong/Downloads/new/full-system/docs/experiments/final-maturity-evidence-manifest.json"` |

## Blockers

- internal release-candidate gate passed
- production configuration was checked in production mode
- external confirmatory human-review freeze passed
- long soak evidence passed
- real TLS deployment evidence passed
- offsite encrypted backup evidence passed
- final maturity evidence manifest verified
