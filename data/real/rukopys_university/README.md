---
language:
- uk
license: cc-by-nc-sa-4.0
task_categories:
- object-detection
- image-to-text
tags:
- handwriting-recognition
- htr
- ocr
- bounding-box
- ukrainian
- document-analysis
- cyrillic
size_categories:
- 10K<n<100K
pretty_name: "RUKOPYS: Ukrainian Handwritten Text Recognition Dataset"
authors:
- Dmytro Voitekh
- Volodymyr Zmiivskyyi
- Oleksii Molchanovskyi
organizations:
- Ukrainian Catholic University
configs:
- config_name: full
  default: true
  data_files:
  - split: train
    path:
      - "train/metadata.jsonl"
      - "train/images/**"
  - split: silver
    path:
      - "silver/metadata.jsonl"
      - "silver/images/**"
- config_name: gt_only
  data_files:
  - split: train
    path:
      - "train/metadata.jsonl"
      - "train/images/**"
- config_name: test
  data_files:
  - split: test
    path:
      - "test/metadata.jsonl"
      - "test/images/**"
---

# RUKOPYS: Ukrainian Handwritten Text Recognition Dataset

**RUKOPYS** (Ukrainian: *рукопис* — manuscript) is the first large-scale open dataset for Ukrainian handwritten text recognition (HTR). It spans over a century of Ukrainian handwriting — from 1920s archival documents to present-day school homework — and is designed for end-to-end document understanding: region detection, type classification, and text transcription.

Ukrainian is among the largest Slavic languages (45M+ native speakers) yet had no dedicated open HTR dataset prior to RUKOPYS.

> **Competition:** RUKOPYS powers the [Handwritten to Data](https://www.kaggle.com/competitions/handwritten-to-data) challenge on Kaggle (April 16 — June 15, 2026). Submit your HTR model predictions and compete for $7,000 in prizes.

---

## What Makes RUKOPYS Different

Most HTR datasets are built from a single source — one archive, one corpus, one handwriting style. RUKOPYS is deliberately the opposite.

It combines four sources that differ across every dimension that makes handwriting recognition hard:

| Dimension | Range in RUKOPYS |
|-----------|-----------------|
| **Time period** | 1919–1935 (archival pen & ink) → 2020–2025 (modern ballpoint, pencil) |
| **Writers** | School children (grades 5–11), university students, adult citizens |
| **Document type** | Archival state documents, personal dictation sheets, exam papers, homework |
| **Capture method** | Flatbed scanner (archive, university) vs phone camera (dictation, school) |
| **Orthography** | Archaic pre-reform spelling (1920s) → contemporary Ukrainian |
| **Content** | Prose, formulas, chemistry, tables, teacher annotations |

This breadth is intentional. A model trained only on clean archival scans will fail on a phone photo of a student notebook — and vice versa. RUKOPYS is designed so that the models trained on it generalize across real-world variation, not just perform well on a narrow slice of it.

Although RUKOPYS is primarily a handwriting dataset, many pages naturally contain **printed text** alongside handwriting — preprinted headers, textbook excerpts, map captions, teacher stamps, table rulings and so on. These printed regions are annotated with the same schema (`type: printed`) and kept in the dataset deliberately: most downstream use cases (search, digitization, classroom assistive tools) need to process a full page end-to-end, not just the handwritten strokes. Training detectors that must distinguish `handwritten` vs `printed` on mixed-content pages is a first-class task supported by RUKOPYS.

---

## Splits

| Split | Images | GT Regions | `annotation_source` | Description |
|-------|--------|-----------|---------------------|-------------|
| **train** | 1,330 | 25,651 | `annotator` / `volunteer` | Human-annotated — full bboxes + verified transcription |
| **silver** | 8,207 | 161,065 | `auto` | Auto-annotated by Qwen3-VL 8B + Gemini — for self-training |
| **test** | 385 | — (hidden) | — | Images only — submit predictions to the [Kaggle competition](https://www.kaggle.com/competitions/handwritten-to-data) |
| **private benchmark** | 21 | — (hidden until June 15) | — | Held-out set withheld during the competition; published after the online stage closes as a reusable community benchmark |

Use `annotation_source` to distinguish professional-annotator ground truth from volunteer and auto-annotations when combining splits.

### Train Composition by Source & Annotation Source

| Source | Professional | Volunteer | Total |
|--------|--------------|-----------|-------|
| `dictation` | 221 | 138 | 359 |
| `archive` | 90 | 37 | 127 |
| `university` | 136 | 26 | 162 |
| `school` | 398 | 284 | 682 |
| **Total** | **845** | **485** | **1,330** |

Professional annotations were produced by the [Keymakr](https://keymakr.com/) team following a detailed brief. Volunteer annotations were contributed by community members. Both follow the same schema; volunteer data may have slightly higher transcription variance — the `annotation_source` field lets you filter or weight them differently during training.

---

## Data Sources

| Source | ID | Period | Images (train+test) | Description |
|--------|----|--------|---------------------|-------------|
| National Dictation | `dictation` | 2020–2025 | 509 | Phone photos of handwritten Ukrainian National Dictation. One canonical text per year, thousands of unique handwriting styles. |
| State Archive | `archive` | 1919–1935 | 178 | Scanned documents from 12 archival funds of the Central State Archive of Ukraine (ЦДАВО). Pen & ink, archaic orthography. |
| University (KNUTE) | `university` | 2024–2025 | 246 | Scanned student exam work from 5 faculties: text, math formulas, chemistry, tables. |
| School Homework | `school` | 2024–2025 | 782 | Phone photos of school homework (grades 5–11, 20+ subjects) from Opornyi Lyceum s. Zymne (Опорний ліцей с. Зимне) and Mriia volunteer contributors. |

---

## Dataset Structure

```
train/                         # Human-annotated (1,330 images)
  images/{uuid}.jpg
  metadata.jsonl               # bbox + type + language + legibility + text

silver/                        # Auto-annotated (8,210 images)
  images/{uuid}.jpg
  metadata.jsonl               # same schema as train

test/                          # Test images, no annotations (385 images)
  images/{uuid}.jpg
  metadata.jsonl               # file_name, image_width, image_height, source (regions: null)
```

`train` and `silver` share the same schema and can be combined freely with `concatenate_datasets`.

---

## Loading

### With `datasets` (recommended — loads images as PIL, regions as structured fields)

```python
from datasets import load_dataset, concatenate_datasets

ds = load_dataset("UkrainianCatholicUniversity/rukopys")

# Human-annotated train
gt_train = ds["train"]
example = gt_train[0]
print(example["image"])             # PIL Image
print(example["source"])            # "dictation"
print(example["annotation_source"]) # "annotator"
print(example["regions"])           # [{bbox, type, language, legibility, text}, ...]

# Combine GT + silver
full_train = concatenate_datasets([gt_train, ds["silver"]])

# GT-only config (no silver):
ds_gt = load_dataset("UkrainianCatholicUniversity/rukopys", "gt_only")
```

### With `pandas`

```python
import pandas as pd
df_train = pd.read_json("hf://datasets/UkrainianCatholicUniversity/rukopys/train/metadata.jsonl", lines=True)
```

### With `polars`

```python
import polars as pl
df_train = pl.read_ndjson("hf://datasets/UkrainianCatholicUniversity/rukopys/train/metadata.jsonl")
```

### Direct download with `huggingface_hub`

```python
from huggingface_hub import snapshot_download
path = snapshot_download(repo_id="UkrainianCatholicUniversity/rukopys", repo_type="dataset")
# All files under `path` in the original folder structure (train/, silver/, test/)
```

---

## Annotation Schema

Each record in `train` and `silver` has a `regions` field — a list of annotated content regions:

```json
{
  "file_name": "images/abc123.jpg",
  "image_width": 3024,
  "image_height": 4032,
  "source": "dictation",
  "annotation_source": "annotator",
  "regions": [
    {
      "bbox": [134, 766, 3754, 1197],
      "type": "handwritten",
      "language": "uk",
      "legibility": "legible",
      "text": "Спочатку був брехунець. У нього кожного дня: „Клац!""
    }
  ]
}
```

`bbox` format: `[x1, y1, x2, y2]` — pixel coordinates, top-left origin.

### Region Types

| Type | Description | Transcription |
|------|-------------|---------------|
| `handwritten` | Handwritten text line | Exact text, 1 bbox = 1 line |
| `printed` | Printed/typed text line | Exact text, 1 bbox = 1 line |
| `formula` | Standalone math/chemistry expression | LaTeX |
| `table` | Full table | Pipe-separated values |
| `annotation` | Teacher marks, grades, numbering | Short text |
| `image` | Stamps, seals, drawings | Empty |
| `graph` | Charts, plots | Empty |

### Special Text Markers

| Marker | Meaning |
|--------|---------|
| `~~word~~` | Strikethrough text |
| `~~old~~{new}` | Strikethrough with correction |
| `[illegible]` | Unreadable word within a legible line |

### Region Attributes

| Attribute | Values |
|-----------|--------|
| `language` | `uk`, `other` |
| `legibility` | `legible`, `illegible` |
| `annotation_source` | `annotator`, `volunteer`, `auto` |

`annotation_source` values:

| Value | Meaning |
|-------|---------|
| `annotator` | Labeled by [Keymakr](https://keymakr.com/) — professional human annotation service |
| `volunteer` | Labeled by community volunteers; spot-checked for quality |
| `auto` | Auto-generated by the VLM pipeline (silver split only) |

---

## Anti-Leakage Design

| Source | Train | Test | Guarantee |
|--------|-------|------|-----------|
| **Dictation** | Year 2024 | Years 2020, 2022, 2025 | Different canonical texts |
| **Archive** | Archival file set A | Archival file set B | Non-overlapping archival document sets |
| **University** | Exam PDF group A | Exam PDF group B | Different students' exam files |
| **School** | Grades 5, 6, 7, 9, 11 | Grades 8, 10 | Different grade bands |

---

## Silver Split

The `silver` split contains 8,210 auto-annotated images generated by a multi-stage VLM pipeline:

```
Stage 1: Qwen3-VL 8B block detection
Stage 2: Gemini Flash block classification
Stage 3: Qwen3-VL 8B line segmentation within text blocks
Stage 4: Gemini Flash transcription
```

Known limitations: bbox sequence drift on dense text; axis-aligned boxes may clip skewed lines; ~440 archive files contain mixed Ukrainian/Russian text from the 1919–1935 period.

---

## Acknowledgements

Professional annotation was provided by [Keymakr](https://keymakr.com/), a human-in-the-loop data annotation company.

Additional annotations were contributed by volunteers. The full list of contributors will be published shortly. All volunteer annotations underwent spot-checking for quality assurance.

All images were reviewed prior to publication to remove personally identifiable information (PII).

---

## Roadmap

This is the first public release of RUKOPYS. The dataset will grow incrementally — both through additional sources and through expanded coverage of existing ones.

We welcome collaboration from:
- **Annotators** interested in contributing human-verified labels
- **Researchers** working on better automatic annotation approaches (layout analysis, HTR pre-annotation, active learning)

If you'd like to contribute, reach out via the [Kaggle competition forum](https://www.kaggle.com/competitions/handwritten-to-data/discussion) or open an issue on HuggingFace.

---

## Potential Uses

- Fine-tune HTR models on `train`, evaluate on `test` via the [Kaggle competition](https://www.kaggle.com/competitions/handwritten-to-data)
- Pseudo-labeling: GT text for each dictation year is publicly known — use it for text-line alignment
- Self-training / semi-supervised learning with the `silver` split
- Multi-source domain adaptation (modern handwriting → historical documents)

---

## License

**CC BY-NC-SA 4.0** — Attribution, Non-Commercial, Share-Alike.

- **National Dictation** images: provided under a data sharing agreement for academic research and publication
- **State Archive** (ЦДАВО): provided under a data sharing agreement for academic research and publication
- **KNUTE** and **Opornyi Lyceum s. Zymne (Опорний ліцей с. Зимне)**: provided under data sharing agreements for academic research and publication

---

## Changelog

### v1.6 — 2026-05-19

**Train: annotation refinement pass. Train: 25,523 → 25,651 regions (+128). No image, split, or schema changes.**

Merged community pull request [#7](https://huggingface.co/datasets/UkrainianCatholicUniversity/rukopys/discussions/7) (thanks to @VmFox) which proposed transcription and labelling corrections on 169 train pages. Reviewed page-by-page; accepted 124 pages as proposed, partially-accepted 30 (mixed accept/reject), reverted 14, and applied additional maintainer cleanup on top:

- **Image vs graph reclassification:** 15 region type-changes + 1 artifact region dropped. Standardized so that `graph` covers geometric figures, coordinate systems, and plots; `image` covers photo-like content. Earlier school pages were inconsistent on this.
- **Formula cleanup:**
  - 36 formula regions hand-edited to valid LaTeX (`√x` → `\sqrt{x}`, `\frac{}{}`, `\partial`, `\pm`, `\cdot`, proper subscripts/superscripts).
  - 15 cyrillic-dominant `formula` regions retyped to `handwritten` (e.g. `D = 22 тис. грн/га · 15 га`) — text-heavy rows now correctly use the handwritten normalization path.
  - 2 `\fraq` typos → `\frac`; 1 `\tons` typo → `\cdots`; 1 region (Vieta's formula) rewritten from broken-LaTeX to valid form.
- **Empty-region legibility correction:** 40 regions with empty `text` and `legibility=legible` switched to `legibility=illegible` — prevents transcription models from learning to emit empty strings on visually similar content.
- **Matrix syntax:** 42 regions with student-style matrix notation `(a b / c d)` converted to the canonical `(a b; c d)` form that the evaluation metric normalizes.

**Evaluation metric (`kaggle_metric.py`) expanded** to cover commands that appeared in the corrected ground truth (no breaking changes — all previously normalized inputs still normalize to the same canonical form):

- Trig/log/lim: `\sin`, `\cos`, `\tan`, `\log`, `\ln`, `\lim`, `\arcsin`, `\sinh`, … → strip backslash + space (so `\sin\alpha` and `sin α` collapse to the same form).
- Matrix environments: added `aligned`, `align`, `gathered`, `cases`, `smallmatrix`, `split` alongside the existing `matrix`/`pmatrix`/`bmatrix`/`vmatrix`/`array`/`tabular`.
- Arrow commands: `\xrightarrow[...]{...}` / `\xleftarrow[...]{...}` → `→` / `←` (label discarded); `\uparrow`/`\downarrow`/`\Uparrow`/`\Downarrow`.
- Sizing: `\big`, `\Big`, `\bigg`, `\Bigg`, `\bigl/r`, `\biggl/r` → strip.
- Math styles: `\mathrm{}`, `\mathbf{}`, `\mathit{}`, `\mathbb{}`, `\mathcal{}`, `\mathfrak{}`, `\operatorname{}`, `\boldsymbol{}` → strip wrapper.
- Cancel/overset/underset: `\cancel{x}` → `x`; `\overset{a}{b}` → `b`; `\underset{a}{b}` → `b` (applied iteratively for nested cases like the structural chemistry notation `\overset{1}{CH_3}`).
- Symbols added: `\vee`, `\wedge`, `\setminus`, `\mid`, `\lvert/\rvert`, `\lfloor/\rfloor/\lceil/\rceil`, `\male`, `\female`.
- Table decorations: `\hline`, `\cline{...}`, `\phantom{...}`, `\underline{x}` → x (visual-only, no semantic value).
- Student-style row separator `(1 2 \n 3 4)` inside plain parens — normalized to multiline like an explicit matrix env.
- **Reading-order fix:** page-level text concatenation now sorts regions by `(center_y // 15, center_x)` instead of `(top_y, left_x)`. The previous sort scrambled the page text whenever detection split one GT line into multiple predicted bboxes whose top-y differed by a few pixels — disproportionately punishing models that produced more granular line splits.

### v1.5 — 2026-05-13

**Test set: 386 → 385 images. No changes to train, silver, or private benchmark.**

- **Removed 1 test page** whose annotation produced inconsistent results across different models we evaluated against it. Model outputs frequently contradicted the ground-truth annotation in ways that suggested the annotation itself, not the model predictions, was the source of the disagreement. Rather than re-annotate one page in isolation, we dropped it from the test set. Image and metadata row removed; no schema changes.

### v1.3 — 2026-04-22

**Region-type corrections. No image or split changes.**

- **Silver — archive `handwritten` → `printed` reclassification:** 19,028 regions across 1,016 archive images corrected. The original auto-annotation pipeline marked every 1920s archival text region as `handwritten`, including typewritten letterheads, official stamps, and typeset forms. A per-block reclassification pass (Gemini 2.0 Flash, ~16.5K blocks) split handwritten vs printed. Counts for the archive split of silver: handwritten 106,811 → 87,786; printed 0 → 19,046. Bounding boxes and transcriptions are unchanged — only `type` differs.
- **Train — 2 bboxes `pii` → `annotation`:** a stray internal service label leaked into public metadata on 2 archive-volunteer images; remapped to the correct public type `annotation`. Bounding boxes and transcriptions unchanged.
- **Test set unchanged:** same 386 images, same regions, same `solution.csv`.

### v1.2 — 2026-04-22

**Annotation quality pass + image orientation normalization. Train: 25,768 → 25,523 regions (−245). Silver: 8,210 → 8,207 images, 163,081 → 161,065 regions.**

- **Annotation cleanup** (applied across all splits):
  - Text normalization: repeated-character loops (`aaaa…` → `aaa`), n-gram loops, control chars, whitespace.
  - **Type correction:** 755 regions reclassified from `handwritten` → `formula` where content is pure math notation (136 train + 619 silver).
  - Bounding box sanity: inverted coordinates auto-swapped, clamped to image bounds, degenerate boxes dropped.
  - Text cleared on structural region types (`image`, `graph`) per schema.
  - Dedup of overlapping same-text boxes (IoU ≥ 0.5).
- **Image orientation normalized:** rotation baked into pixels and EXIF orientation tags removed on 193 images, so loading is consistent across viewers and libraries.
- **Silver refinements:** 4 images removed due to annotation artifacts (hallucinated column of tiny bboxes with empty text); 7 images re-annotated via the full layout+transcription pipeline where earlier annotations had collapsed.
- **Test set unchanged:** same 386 images, same UUIDs. Kaggle evaluation set stable.

### v1.1 — 2026-04-21

**Train expanded: 770 → 1,330 images (+560), 16,381 → 25,768 regions (+9,387).**

- **School (professional, batch 2):** added 398 professionally-annotated school homework images (grades 5/6/7/9/11). Every image went through a manual QA review — bboxes verified, rotations corrected, EXIF orientation fixed on affected images, PII regions masked.
- **Volunteer batches:** added 167 additional volunteer annotations — 53 dictation, 11 archive, 103 school. Same QA review pipeline applied; rotations and image transforms from Label Studio propagated to bbox coordinates.
- **Field normalization:** `legibility` and `language` fields normalized to lowercase across all sources.
- **Anti-leakage preserved:** professional and volunteer school train contain grades 5/6/7/9/11 only; grades 8/10 remain exclusive to test. 24 newly-contributed volunteer school images with grades 8/10 were deliberately excluded rather than added to test, to keep the Kaggle evaluation set stable.
- **Test set unchanged:** 386 images, identical `solution.csv` — the mid-competition evaluation set is stable.

### v1.0 — 2026-04-13

Initial public release of RUKOPYS v1 alongside the Kaggle competition launch.

---

## Citation

```bibtex
@dataset{rukopys_2026,
  title        = {{RUKOPYS}: Ukrainian Handwritten Text Recognition Dataset},
  author       = {Dmytro Voitekh and Volodymyr Zmiivskyi and Oleksii Molchanovskyi},
  organization = {Ukrainian Catholic University},
  year         = {2026},
  license      = {CC BY-NC-SA 4.0},
  url          = {https://huggingface.co/UkrainianCatholicUniversity/rukopys},
  note         = {First large-scale Ukrainian HTR dataset; from 1920s archival documents to 2025 school homework and exams}
}
```
