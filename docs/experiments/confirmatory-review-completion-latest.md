# Confirmatory human review completion gate

Result: FAIL

| Check | Status | Detail |
| --- | --- | --- |
| final maturity gate passed before reporting review | FAIL | `{"failures_empty": false, "generated_at_present": true, "passed": false, "required_checks_present": ["external confirmatory human-review freeze passed", "final maturity evidence manifest verified", "internal release-candidate gate passed", "long soak evidence passed", "offsite encrypted backup evidence passed", "production configuration was checked in production mode", "real TLS deployment evidence passed"], "scope": "final maturity gate for confirmatory human review", "source": "/Users/yusong/Downloads/new/full-system/docs/experiments/final-maturity-gate-latest.json"}` |
| confirmatory freeze exists and validates | FAIL | `"missing: /Users/yusong/Downloads/new/full-system/docs/experiments/confirmatory-human-review-freeze.json"` |
| human review export exists | FAIL | `"missing: /Users/yusong/Downloads/new/full-system/docs/experiments/confirmatory-human-review-export.csv"` |
| confirmatory review evidence manifest verified | FAIL | `"missing: /Users/yusong/Downloads/new/full-system/docs/experiments/confirmatory-review-evidence-manifest.json"` |

## Blockers

- final maturity gate passed before reporting review
- confirmatory freeze exists and validates
- human review export exists
- confirmatory review evidence manifest verified
