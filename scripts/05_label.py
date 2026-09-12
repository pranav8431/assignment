#!/usr/bin/env python3
"""
Builds the churn label and emits the training + scoring frames.

LABEL (answers/part2-features.md):
    at cutoff T,  label = 1  if the member made ZERO purchases in (T, T+90]
                  label = 0  otherwise
`status` is NOT used -- its median last-transaction date is identical across
active/inactive/churned, so it carries no activity information.

TRAINING frame : T = max_txn_date - 90d = 2026-04-01  (latest cutoff with a complete
                 outcome window). Features <= T, label from (T, max].
SCORING  frame : T = max_txn_date = 2026-06-30. Same feature SQL, no label.
"""
import os, sqlite3, csv, datetime

BASE = os.path.join(os.path.dirname(__file__), "..")
DB   = os.path.join(BASE, "output", "loyalty.db")
FEAT_SQL = open(os.path.join(BASE, "scripts", "04_features.sql")).read()

con = sqlite3.connect(DB)
cur = con.cursor()

MAX_DATE = cur.execute("SELECT MAX(txn_date) FROM clean_transactions").fetchone()[0]
T_TRAIN  = (datetime.date.fromisoformat(MAX_DATE) - datetime.timedelta(days=90)).isoformat()
print(f"max clean transaction date : {MAX_DATE}")
print(f"training cutoff T          : {T_TRAIN}")
print(f"outcome window             : ({T_TRAIN}, {MAX_DATE}]")

def build(as_of, table):
    cur.execute("DROP TABLE IF EXISTS params")
    cur.execute("CREATE TABLE params (as_of_date TEXT)")
    cur.execute("INSERT INTO params VALUES (?)", (as_of,))
    con.commit()
    cur.executescript(FEAT_SQL)
    cur.execute(f"DROP TABLE IF EXISTS {table}")
    cur.execute(f"CREATE TABLE {table} AS SELECT * FROM member_features")
    con.commit()
    n = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  {table:20s} as_of={as_of}  rows={n:,}")
    return n

print("\nBuilding feature frames from the SAME 04_features.sql:")
build(T_TRAIN, "features_train")
build(MAX_DATE, "features_score")

# ---- attach the label to the training frame -----------------------------------------
cur.executescript(f"""
DROP TABLE IF EXISTS churn_training;
CREATE TABLE churn_training AS
WITH outcome AS (
    SELECT DISTINCT member_id
    FROM clean_transactions
    WHERE txn_date > '{T_TRAIN}' AND txn_date <= '{MAX_DATE}'
      AND is_orphan_member = 0
)
SELECT f.*,
       CASE WHEN o.member_id IS NULL THEN 1 ELSE 0 END AS churned_90d
FROM features_train f
LEFT JOIN outcome o ON o.member_id = f.member_id
-- COHORT: members active within 365d of T. Including members already dormant for
-- years inflates the base rate and lets a model win on the trivially obvious.
WHERE f.recency_days <= 365;
""")
con.commit()

n, ch = cur.execute("SELECT COUNT(*), SUM(churned_90d) FROM churn_training").fetchone()
print(f"\nTRAINING COHORT (active within 365d of T)")
print(f"  rows       : {n:,}")
print(f"  churned    : {ch:,}")
print(f"  base rate  : {100*ch/n:.1f}%")

print("\nbase rate under alternative cohort definitions (sensitivity):")
for lim, lbl in ((100000, "any member with a txn <= T"), (365, "active within 365d"), (180, "active within 180d")):
    r = cur.execute(f"""
        SELECT COUNT(*), SUM(CASE WHEN o.member_id IS NULL THEN 1 ELSE 0 END)
        FROM features_train f
        LEFT JOIN (SELECT DISTINCT member_id FROM clean_transactions
                   WHERE txn_date > '{T_TRAIN}' AND txn_date <= '{MAX_DATE}' AND is_orphan_member=0) o
               ON o.member_id = f.member_id
        WHERE f.recency_days <= {lim}""").fetchone()
    print(f"  {lbl:28s} n={r[0]:>7,}  churn={100*r[1]/r[0]:>5.1f}%")

# ---- export -------------------------------------------------------------------------
def export(table, path):
    rows = cur.execute(f"SELECT * FROM {table}").fetchall()
    cols = [d[0] for d in cur.description]
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(cols); w.writerows(rows)
    print(f"  wrote {path}  ({len(rows):,} rows x {len(cols)} cols)")

print("\nexports:")
export("churn_training", os.path.join(BASE, "output", "member_features.csv"))
export("features_score", os.path.join(BASE, "output", "member_features_scoring.csv"))

print(f"\nfeature count (excl. ids/label/meta): "
      f"{len([c for c in [d[0] for d in cur.execute('SELECT * FROM churn_training LIMIT 1').description] if c not in ('as_of_date','member_id','churned_90d','last_txn_date')])}")
con.close()
