# GSE111619 real-data validation package

This directory contains public NCBI GEO data and locally generated validation artifacts for the `full-system` project.

## Source

- GEO series: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE111619
- Family SOFT: https://ftp.ncbi.nlm.nih.gov/geo/series/GSE111nnn/GSE111619/soft/GSE111619_family.soft.gz
- Series matrix: https://ftp.ncbi.nlm.nih.gov/geo/series/GSE111nnn/GSE111619/matrix/GSE111619_series_matrix.txt.gz
- Processed HTSeq counts: https://ftp.ncbi.nlm.nih.gov/geo/series/GSE111nnn/GSE111619/suppl/GSE111619_RNAseq_H226_shp63_analysis_HTSeq_counts.txt.gz

The downloaded count matrix is processed gene-level count data. It is not raw FASTQ data and it is not a local laboratory notebook.

## Artifact scopes

- `validation_report.json` and `validation_report.md`: offline SQLite/service preflight only.
- `system_import_report.json`: formal API import into the running PostgreSQL system.
- `gse111619_paired_experiment.csv` and `gse111619_paired_experiment_report.json`: formal paired DeepSeek experiment from the running system.

Thesis claims about the implemented system must use the latter two artifact groups, not the offline preflight metrics.

## Verification

- Status: ANALYZED
- Fingerprint: `54e4e477ddb927e252f5988ce1b4ec73ee68f05f04947b13795408074c26ccf2`
- Sample accessions: GSM3035185, GSM3035186, GSM3035187, GSM3035188
- Gene rows: 25369
- Script: `../../../scripts/validate_gse111619.py`

Run from the repository root with:

```bash
backend/.venv/bin/python scripts/validate_gse111619.py
```

The first full run may download the 90 MB `BAAI/bge-small-zh-v1.5` embedding model into `model-cache/`.
