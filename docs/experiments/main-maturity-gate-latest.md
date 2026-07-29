# Full-System Maturity Gate

- Generated: `2026-07-29T16:41:15.597917+00:00`
- Result: **FAIL**
- Evidence level: internal automated gate; not independent human review

## Checks

| Group | Check | Actual | Target | Result |
| --- | --- | ---: | ---: | --- |
| retrieval | retrieval question count | 20 | >= 20 | PASS |
| retrieval | retrieval gold fact count | 56 | >= 50 | PASS |
| retrieval | retrieval corpus chunk count | 984 | >= 500 | PASS |
| retrieval | graph Recall@10 | 0.902381 | >= 0.9 | PASS |
| retrieval | graph nDCG@10 | 0.607235 | >= 0.6 | PASS |
| retrieval | graph Recall@10 delta over hybrid | 0.339286 | >= 0.1 | PASS |
| rag_experiment | experiment required method coverage | [] | == [] | PASS |
| rag_experiment | experiment required methods completed cases | [] | == [] | PASS |
| rag_experiment | experiment required methods failed cases | [] | == [] | PASS |
| rag_experiment | experiment completed kg cases | 36 | >= 12 | PASS |
| rag_experiment | experiment failed kg cases | 0 | == 0 | PASS |
| rag_experiment | kg micro fact coverage | 0.9062 | >= 0.85 | PASS |
| rag_experiment | kg exact case accuracy | 0.8333 | >= 0.6 | PASS |
| rag_experiment | kg forbidden fact hits | 0 | <= 0 | PASS |
| rag_experiment | citation indices in range | True | == True | PASS |
| rag_experiment | kg source marker rate | 0.9722 | >= 0.95 | PASS |
| rag_experiment | kg graph marker rate | 1.0 | >= 0.95 | PASS |
| agent | agent completed runs | 4 | >= 4 | PASS |
| agent | agent failed runs | 0 | <= 0 | PASS |
| agent | agent needs_review runs | 0 | <= 0 | PASS |
| agent | agent invalid citations | 0 | <= 0 | PASS |
| agent | agent required task coverage | True | == True | PASS |
| system | system evidence freshness hours | 312.8103638880556 | <= 168 | FAIL |
| system | runtime evidence freshness hours | 312.80996946722223 | <= 168 | FAIL |
| system | playwright evidence freshness hours | 1000000000.0 | <= 168 | FAIL |
| system | runtime checks | True | == True | PASS |
| system | runtime metrics endpoint | True | == True | PASS |
| system | runtime metrics total requests | 361 | >= 1 | PASS |
| system | runtime metrics p95 latency ms | 18 | <= 2000 | PASS |
| system | load smoke ok | True | == True | PASS |
| system | load smoke successful requests | 90 | >= 60 | PASS |
| system | load smoke p95 latency ms | 31 | <= 2000 | PASS |
| system | experiment restart recovery | False | == True | FAIL |
| system | experiment interruption observed | None | == True | FAIL |
| system | experiment resume completed | None | == completed | FAIL |
| system | short soak smoke ok | True | == True | PASS |
| system | short soak smoke cycles | 3 | >= 2 | PASS |
| system | short soak smoke p95 latency ms | 15 | <= 2000 | PASS |
| system | npm production audit vulnerabilities | 0 | == 0 | PASS |
| system | production config preflight | passed | == passed | PASS |
| system | secret hygiene | True | == True | PASS |
| system | secret rotation runbook | True | == True | PASS |
| system | backup policy runbook | True | == True | PASS |
| system | monitoring alerts | True | == True | PASS |
| system | reverse proxy TLS template | True | == True | PASS |
| system | playwright expected tests | 3 | >= 4 | FAIL |
| system | playwright critical flow coverage | ['系统管理员完成账号、小组和审计闭环'] | == [] | FAIL |
| system | playwright unexpected tests | 0 | == 0 | PASS |
| system | playwright skipped tests | 0 | == 0 | PASS |
| system | playwright result count | 3 | == 3 | PASS |
| system | playwright unique test titles | 3 | == 3 | PASS |
| system | playwright all test results passed | True | == True | PASS |
| system | backup smoke verified | True | == True | PASS |
| system | backup dump readable | True | == True | PASS |
| system | restore drill verified | True | == True | PASS |
| system | restore drill public tables | 26 | >= 1 | PASS |
| system | restore drill storage restored | True | == True | PASS |
| system | knowledge graph audit F1 | 1.0 | >= 0.8 | PASS |
| evidence_manifest | maturity evidence manifest verified | False | == True | FAIL |
| evidence_manifest | maturity evidence manifest matches current checkout | False | == True | FAIL |
| evidence_manifest | maturity evidence manifest file count | 15 | >= 10 | PASS |
| evidence_manifest | maturity evidence manifest covers gate inputs | [] | == [] | PASS |

## Interpretation

This gate is deliberately stricter than the current development evidence. A failure means the project is not ready for human review or release-candidate freeze.
It does not replace independent frozen corpora, external reviewers, long soak tests, backup drills, or security review.

## First Failures

- system: system evidence freshness hours is 312.8103638880556 (target <= 168).
- system: runtime evidence freshness hours is 312.80996946722223 (target <= 168).
- system: playwright evidence freshness hours is 1000000000.0 (target <= 168).
- system: experiment restart recovery is False (target == True).
- system: experiment interruption observed is None (target == True).
- system: experiment resume completed is None (target == completed).
- system: playwright expected tests is 3 (target >= 4).
- system: playwright critical flow coverage is ['系统管理员完成账号、小组和审计闭环'] (target == []).
- evidence_manifest: maturity evidence manifest verified is False (target == True).
- evidence_manifest: maturity evidence manifest matches current checkout is False (target == True).
