# Repository Scripts Directory

This directory contains offline data processing, CI/CD evidence verification, audit, and experiment evaluation scripts.

> **Architecture Note**: Production services run entirely via Rust (`backend/src/`) and Next.js (`frontend/src/`).
> Python scripts here are exclusively for offline tasks, gate validation, reproducible experiments, and operational utilities.

## Directory Structure

| Subdirectory | Purpose | Key Scripts & Examples |
| :--- | :--- | :--- |
| **`gates/`** | Deployment & maturity gates, config validation, security checks | `check_production_config.py`, `final_maturity_gate.py`, `release_maturity_gate.py`, `controlled_beta_gate.py`, `check_backup_policy.py`, `check_tls_deployment.py` |
| **`freeze/`** | Cryptographic evidence freezing, hash manifests, runtime evidence export | `freeze_system_evidence.py`, `freeze_preregistration.py`, `freeze_rust_g5a_runtime.py`, `export_runtime_evidence.py`, `export_rust_contract_evidence.py` |
| **`experiments/`** | Benchmark evaluations, ablation studies, reproducible experiment runners | `evaluate_rust_retrieval.py`, `run_innovation_ablation.py`, `run_rag_confirmatory_experiment.py`, `evaluate_agent_quality.py`, `evaluate_ocr.py`, `validate_gse111619.py` |
| **`data/`** | Dataset preparation, format normalization, synthetic/mock seeding | `import_gse111619_via_api.py`, `prepare_new_geo_datasets.py`, `prepare_rukopys_ocr_subset.py`, `populate_mock_data.py` |
| **`render/`** | Chart generation, thesis figures, paper material rendering | `generate_thesis_diagrams.py`, `generate_rag_chart.py`, `render_rag_five_mode_paper_material.py`, `summarize_system_reviews.py` |
| **`ops/`** | Shell runbooks, Docker Compose wrappers, database test harnesses, smoke tests | `docker-compose-with-revision.sh`, `run-rust-db-tests.sh`, `run-system-e2e.sh`, `backup-system.sh`, `restore-system.sh`, `load_smoke.py`, `soak_smoke.py` |
| **`audit/`** | Consistency audits, KG relation validations, bundle verification | `audit_kg_relations.py`, `audit_rag_csv_consistency.py`, `audit_rag_five_mode_bundle.py` |

## Testing Scripts

Each functional script is paired with a corresponding `test_*.py` test file in the same subdirectory.

To run all script tests:

```bash
python -m pytest -q scripts/*/test_*.py
```

Or run tests for a specific functional group:

```bash
python -m pytest -q scripts/gates/test_*.py
python -m pytest -q scripts/freeze/test_*.py
python -m pytest -q scripts/experiments/test_*.py
```
