# Take-Home Submission — Product Analyst (Data Engineering)

**Start in the `answers/` folder.** The write-up is split by part there, so you can read whichever
section you care about without scrolling past the rest.

The two notebooks in `notebooks/` are the working: `00_discovery.ipynb` shows how the problems were
found (including the dead ends and one self-correction), `01_feature_build.ipynb` shows how each
finding became a cleaning or feature decision.

## Run it

```bash
bash run_all.sh          # ~30 seconds
```

**The pipeline itself is Python 3 standard library only** — no pandas, no duckdb, no installs. Data is
loaded into SQLite (built into Python) so the cleaning and feature logic can be written as reviewable
SQL. That is deliberate: `run_all.sh` reproduces every figure in the write-up on any machine with
Python 3 and nothing else.

**The two notebooks are the one exception** and need Jupyter:

```bash
python3 -m venv .venv
.venv/bin/pip install jupyterlab pandas matplotlib
bash run_all.sh                       # now builds and executes the notebooks too
.venv/bin/jupyter lab notebooks/      # to read them interactively
```

Without `.venv`, `run_all.sh` skips the notebook step and says so; everything else still runs.

## What's here

| Path | |
|---|---|
| `ANSWERS.md` | **Start here.** Index, how to run it, and what to expect |
| `answers/part1-data-quality.md` … `part8-…` | The response, one file per part |
| `answers/decision-log.md` | Per part: decisions, rejected alternatives, where AI got it wrong |
| `scripts/01_profile.py` | Data quality audit — generates every figure quoted in Part 1 |
| `scripts/02_build_db.py` | Loads both CSVs into SQLite as an untouched RAW layer |
| `scripts/03_clean.sql` | RAW → CLEANED. Each transformation maps to a numbered Part 1 finding |
| `scripts/03b_materialize.py` | Snapshots the cleaned views into tables (120s → 1.8s) |
| `scripts/04_features.sql` | Member-level churn features, parameterised by `as_of_date` |
| `scripts/05_label.py` | Builds the 90-day churn label + training and scoring frames |
| `scripts/06_validate.py` | **Asserts every number quoted in the write-up** |
| `scripts/07_section2.py` | Parts 6, 7, 8 |
| `notebooks/00_discovery.ipynb` | **How the problems were found** — 4 catches, 3 dead ends |
| `notebooks/01_feature_build.ipynb` | Raw → cleaned → features, with the rejected alternatives shown |
| `scripts/build_notebooks.py` | Builds the notebooks, executing every cell to capture real output |
| `output/` | Generated — evidence files, feature tables, win-back list |

`output/` is rebuilt by `run_all.sh`; nothing in it needs to be kept.

## Design notes

- **The raw layer is deliberately uncleaned** — every column is TEXT and no constraints are applied,
  so that the defects in Part 1 are visible in the data rather than only described. `02_build_db.py`
  prints the primary keys that *would* fail today.
- **Cleaning is reconciled, not silent.** `clean_exclusions` accounts for every point the cleaning
  removes, and validation asserts `raw − removed + imputed == clean`.
- **`04_features.sql` builds both the training and scoring frames**, changing only `as_of_date`.
  That is what prevents train/serve skew, and validation asserts no training feature uses data past
  the cutoff.
- **Runs are deterministic** — two consecutive runs produce byte-identical outputs.
- **The notebooks are generated and executed, never hand-edited.** `build_notebooks.py` assembles
  them with `nbformat` and runs every cell through a real **ipykernel** via `nbclient`. Every output
  and figure committed in the `.ipynb` is a genuine kernel result — nothing is transcribed by hand.
  Cell ids and stream fragments are normalised and execution timings stripped, so **rebuilding
  produces byte-identical notebooks**.
- **Charts** use a categorical palette validated for colour-vision deficiency against the chart
  surface (worst adjacent pair ΔE 9.2 deutan / 27.6 normal). Where colour carries a verdict it is
  always paired with a ✓/✗ glyph and a text column, never colour alone.
# assignment
