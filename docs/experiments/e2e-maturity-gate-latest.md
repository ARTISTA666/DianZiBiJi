# Full-System Maturity Gate

- Generated: `2026-07-16T13:41:41.689564+00:00`
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
| rag_experiment | experiment completed kg cases | 12 | >= 12 | PASS |
| rag_experiment | experiment failed kg cases | 0 | == 0 | PASS |
| rag_experiment | kg micro fact coverage | 0.7812 | >= 0.85 | FAIL |
| rag_experiment | kg exact case accuracy | 0.5 | >= 0.6 | FAIL |
| rag_experiment | kg forbidden fact hits | 5 | <= 0 | FAIL |
| rag_experiment | citation indices in range | True | == True | PASS |
| rag_experiment | source marker answer rate | 0.75 | >= 0.95 | FAIL |
| rag_experiment | kg graph marker rate | 0.8333 | >= 0.95 | FAIL |
| agent | agent live maturity evidence | missing | present agent probe report | FAIL |

## Interpretation

This gate is deliberately stricter than the current development evidence. A failure means the project is not ready for human review or release-candidate freeze.
It does not replace independent frozen corpora, external reviewers, long soak tests, backup drills, or security review.

## First Failures

- rag_experiment: kg micro fact coverage is 0.7812 (target >= 0.85).
- rag_experiment: kg exact case accuracy is 0.5 (target >= 0.6).
- rag_experiment: kg forbidden fact hits is 5 (target <= 0).
- rag_experiment: source marker answer rate is 0.75 (target >= 0.95).
- rag_experiment: kg graph marker rate is 0.8333 (target >= 0.95).
- agent: agent live maturity evidence is missing (target present agent probe report).
