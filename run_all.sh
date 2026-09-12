#!/usr/bin/env bash
# Reproduces every number in the write-up from the two raw CSVs.
# Python 3 standard library only -- no pandas, no installs.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p output

echo "== 1/7  Data quality audit (Part 1 evidence) =="
python3 scripts/01_profile.py > output/dq_findings.txt
echo "   -> output/dq_findings.txt"

echo "== 2/7  Load RAW layer into SQLite =="
python3 scripts/02_build_db.py

echo "== 3/7  Clean + conform (raw -> cleaned) =="
python3 scripts/03b_materialize.py

echo "== 4/7  Features + churn label (Part 2) =="
python3 scripts/05_label.py

echo "== 5/7  Section 2 analysis (Parts 6, 7, 8) =="
python3 scripts/07_section2.py > output/section2_findings.txt
echo "   -> output/section2_findings.txt"

echo "== 6/7  Notebooks (executed by a real Jupyter kernel) =="
if [ -x .venv/bin/python ]; then
  .venv/bin/python scripts/build_notebooks.py
else
  echo "   SKIPPED - no .venv. The notebooks need Jupyter:"
  echo "     python3 -m venv .venv && .venv/bin/pip install jupyterlab pandas matplotlib"
  echo "   Everything else in this pipeline is standard-library only and already ran."
fi

echo "== 7/7  Validation =="
python3 scripts/06_validate.py > output/validation.txt || { cat output/validation.txt; exit 1; }
tail -4 output/validation.txt

echo
echo "Done. Deliverables:"
ls -1 output/ | grep -v loyalty.db
echo "  (output/loyalty.db is a rebuildable ~90MB working file -- not part of the submission)"
