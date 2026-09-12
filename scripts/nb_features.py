"""Cell definitions for notebooks/01_feature_build.ipynb."""
from build_notebooks import md, code
from nb_discovery import STYLE


def cells():
    return [
md("""
# Feature build — from raw CSV to a churn-ready feature table

Companion to `00_discovery.ipynb`. That notebook found the problems; this one shows how each finding
becomes a **decision**, and what the alternative would have cost.

```
RAW  ->  CLEANED  ->  FEATURES  ->  LABELLED TRAINING FRAME
 |         |            |             |
 |         |            |             `- 05_label.py
 |         |            `- 04_features.sql   (as_of_date parameterised)
 |         `- 03_clean.sql                   (one transform per Part 1 finding)
 `- 02_build_db.py                           (all TEXT, no constraints, nothing fixed)
```

The pipeline loads both CSVs into SQLite — built into Python — so the cleaning and feature logic can
be written as **reviewable SQL** rather than opaque dataframe chains. This notebook queries that same
database, so what you see below is the shipped logic, not a re-implementation of it.
"""),

code("""
import sqlite3, os, subprocess, sys
import pandas as pd, numpy as np

pd.set_option("display.width", 120)
pd.set_option("display.max_columns", 40)

BASE = os.getcwd()
while not os.path.exists(os.path.join(BASE, "members.csv")) and BASE != os.path.dirname(BASE):
    BASE = os.path.dirname(BASE)
DB = os.path.join(BASE, "output", "loyalty.db")

def ensure_db():
    need = not os.path.exists(DB)
    if not need:
        c = sqlite3.connect(DB)
        have = {r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
        need = not {"clean_transactions", "churn_training"} <= have
        c.close()
    if need:
        print("building the database (run_all.sh does this too)...")
        for s in ("02_build_db.py", "03b_materialize.py", "05_label.py"):
            subprocess.run([sys.executable, os.path.join(BASE, "scripts", s)],
                           check=True, capture_output=True)
    return sqlite3.connect(DB)

con = ensure_db()
q = lambda sql: pd.read_sql_query(sql, con)
print(f"connected: {os.path.relpath(DB, BASE)}")
"""),

code(STYLE + '\nprint("chart style loaded")'),

md("""
## Layer 1 — RAW is deliberately broken

Every column is `TEXT` and no constraints are applied. That is not laziness: the raw layer must be a
faithful reproduction of what landed, so every later transformation can be diffed against it. Coercing
types on load would turn the three date formats into nulls and destroy the evidence.

The load script prints the constraints that *would* fail today:
"""),

code("""
q('''SELECT 'raw_members.member_id' AS natural_key,
        (SELECT COUNT(*) FROM (SELECT member_id FROM raw_members
                               GROUP BY member_id HAVING COUNT(*)>1)) AS duplicated_values
     UNION ALL
     SELECT 'raw_transactions.transaction_id',
        (SELECT COUNT(*) FROM (SELECT transaction_id FROM raw_transactions
                               GROUP BY transaction_id HAVING COUNT(*)>1))''')
"""),

md("""
## Decision 1 — deduplication: `ROW_NUMBER()`, not `SELECT DISTINCT`

`SELECT DISTINCT` is the reflex. It only works if duplicate rows are *identical*. Checking first:
"""),

code("""
dup = q('''SELECT COUNT(*) AS dup_groups,
             SUM(CASE WHEN distinct_payloads = 1 THEN 1 ELSE 0 END) AS byte_identical,
             SUM(CASE WHEN distinct_payloads > 1 THEN 1 ELSE 0 END) AS conflicting
        FROM (SELECT transaction_id,
                     COUNT(DISTINCT member_id||'|'||transaction_date||'|'||amount||'|'||
                           points_earned||'|'||points_redeemed) AS distinct_payloads
              FROM raw_transactions GROUP BY transaction_id HAVING COUNT(*)>1)''')
display(dup)
print(f"SELECT DISTINCT would silently double-count the {int(dup.conflicting[0])} conflicting groups.")
print("ROW_NUMBER with a deterministic ORDER BY keeps exactly one row per id, and is")
print("stable across re-runs -- which matters, because non-determinism is a reproducibility bug.")
"""),

md("""
## Decision 2 — sentinel amounts: NULL the value, keep the row

| option | effect |
|---|---|
| delete the row | biases *frequency* and *recency* down — the purchase did happen |
| winsorise to p99 | invents a price we have no basis for |
| **NULL the amount, keep the row** | `SUM`/`AVG` skip it; the row still counts toward frequency |

The third is why the feature SQL aggregates safely without special-casing anything:
"""),

code("""
q('''SELECT is_sentinel_amount, COUNT(*) AS rows, COUNT(amount) AS amount_not_null,
        ROUND(COALESCE(SUM(amount),0),2) AS spend_contributed
     FROM clean_transactions GROUP BY is_sentinel_amount''')
"""),

md("""
## Decision 3 — refunds: keep the row, reverse the points

2,012 rows carry a negative `amount` **and** positive `points_earned`, computed on `ABS(amount)`.
`ABS()` was the first suggestion and it launders a refund into a purchase. We keep the negative spend
(real, and exactly the behaviour a churn model should see) and zero the points the bug granted.
"""),

code("""
q('''SELECT is_refund, COUNT(*) AS rows, ROUND(SUM(amount),2) AS net_spend,
        ROUND(SUM(points_earned),0) AS points_kept,
        ROUND(SUM(points_reversed_on_refund),0) AS points_reversed
     FROM clean_transactions GROUP BY is_refund''')
"""),

md("""
## Decision 4 — null points: impute, but only because the rate is deterministic

Imputation is normally a smell. It is defensible **here and only here**, because the earn rate is not
an average — it is a constant. The rate is derived from the data, never hard-coded:
"""),

code("""
display(q("SELECT brand, earn_rate, n_rows FROM v_brand_earn_rate ORDER BY earn_rate DESC"))

grid = q('''SELECT m.tier,
        ROUND(SUM(CASE WHEN c.brand='PulseMart' THEN c.points_earned END)/
              SUM(CASE WHEN c.brand='PulseMart' THEN c.amount END),3) AS PulseMart,
        ROUND(SUM(CASE WHEN c.brand='PulseHome' THEN c.points_earned END)/
              SUM(CASE WHEN c.brand='PulseHome' THEN c.amount END),3) AS PulseHome,
        ROUND(SUM(CASE WHEN c.brand='PulseEats' THEN c.points_earned END)/
              SUM(CASE WHEN c.brand='PulseEats' THEN c.amount END),3) AS PulseEats
     FROM clean_transactions c JOIN clean_members m ON m.member_id=c.member_id
     WHERE c.is_sentinel_amount=0 AND c.is_refund=0 AND c.is_points_imputed=0
     GROUP BY m.tier''')
grid = grid.set_index("tier").loc[["Bronze", "Silver", "Gold", "Platinum"]]
display(grid)
print("Identical in every cell. Imputing amount * rate reproduces what the row would")
print("have carried, and every imputed row is flagged so a modeller can ablate them.")
print("\\nIt is also a product finding: Platinum earns exactly what Bronze earns.")
"""),

md("""
## The cleaning is reconciled, not silent

The rule the pipeline holds itself to: **every point removed must be accounted for.**
"""),

code("""
display(q("SELECT reason, n_rows, ROUND(points_removed,0) AS points_removed FROM clean_exclusions"))

raw = q("SELECT SUM(CASE WHEN trim(points_earned)='' THEN 0 ELSE CAST(points_earned AS REAL) END) v "
        "FROM raw_transactions").v[0]
rem = q("SELECT SUM(points_removed) v FROM clean_exclusions").v[0]
imp = q("SELECT SUM(points_earned) v FROM clean_transactions WHERE is_points_imputed=1").v[0]
cln = q("SELECT SUM(points_earned) v FROM clean_transactions WHERE is_orphan_member=0").v[0]
print(f"  raw      {raw:>14,.0f}")
print(f"  removed  {rem:>14,.0f}")
print(f"  imputed  {imp:>14,.0f}")
print(f"  clean    {cln:>14,.0f}")
print(f"\\n  {raw:,.0f} - {rem:,.0f} + {imp:,.0f} = {raw-rem+imp:,.0f}   "
      f"{'RECONCILES' if abs(raw-rem+imp-cln) < 1 else 'MISMATCH'}")
"""),

md("""
## The two-window frame

Features come from on-or-before a cutoff `T`; the label comes from the 90 days after it.
`T = 2026-04-01` is the last transaction date minus 90 days — the latest cutoff with a *complete*
outcome window.

```
|<------- observation window: features ------->|<-- outcome window: label -->|
2021-01-05                              T = 2026-04-01               2026-06-30
```

The same `04_features.sql` builds both frames. **Only the parameter changes** — that is what prevents
train/serve skew.
"""),

code("""
q('''SELECT 'features_train' AS frame, as_of_date, COUNT(*) AS members,
        MAX(last_txn_date) AS latest_data_seen FROM features_train GROUP BY as_of_date
     UNION ALL
     SELECT 'features_score', as_of_date, COUNT(*), MAX(last_txn_date)
     FROM features_score GROUP BY as_of_date''')
"""),

md("""
Note `latest_data_seen` on the training frame — no feature reaches past the cutoff.

### Why that bound is the whole design

Computed over *all* data, recency stops being a predictor and becomes a restatement of the label:
"""),

code("""
lk = q('''SELECT t.recency_days, t.churned_90d,
            CAST(julianday('2026-06-30') - julianday(s.last_txn_date) AS INT) AS recency_all_data
       FROM churn_training t JOIN features_score s ON s.member_id = t.member_id''')
print(f"corr(recency computed <= T,     label) = {lk.recency_days.corr(lk.churned_90d):.3f}   legitimate")
print(f"corr(recency computed over ALL, label) = {lk.recency_all_data.corr(lk.churned_90d):.3f}   leaks the answer")
print("\\nA single careless MAX(transaction_date) yields a model that validates")
print("near-perfectly and is worthless in production.")
"""),

md("""
## The feature table
"""),

code("""
train = q("SELECT * FROM churn_training")
skip = {"as_of_date", "member_id", "churned_90d", "last_txn_date"}
feats = [c for c in train.columns if c not in skip]
print(f"{len(feats)} features across {len(train):,} members   "
      f"| base rate {100*train.churned_90d.mean():.1f}% churned\\n")
for i in range(0, len(feats), 3):
    print("   " + "".join(f"{c:<28s}" for c in feats[i:i+3]))
"""),

code("""
train[["recency_days", "txn_count_lifetime", "monetary_lifetime",
       "points_balance", "redemption_rate", "avg_gap_days"]].describe().round(2)
"""),

md("""
## Validation — and the finding that changed the recommendation

Decile lift on recency: clean, near-monotonic separation.
"""),

code("""
d = train.dropna(subset=["recency_days"]).copy()
d["decile"] = pd.qcut(d.recency_days, 10, labels=False, duplicates="drop") + 1
lift = d.groupby("decile").agg(n=("churned_90d", "size"),
                               churn=("churned_90d", "mean"),
                               lo=("recency_days", "min"), hi=("recency_days", "max"))
lift["churn"] = (100 * lift.churn).round(1)

fig, ax = plt.subplots(figsize=(9, 3.9))
bars = ax.bar(lift.index, lift.churn, color=BLUE, edgecolor="#fcfcfb", linewidth=2, width=0.72)
for b, v in zip(bars, lift.churn):
    ax.annotate(f"{v:.0f}", (b.get_x()+b.get_width()/2, v), (0, 4), textcoords="offset points",
                ha="center", fontsize=9, color=INK)
clean_axes(ax)
ax.axhline(100*train.churned_90d.mean(), color=INK2, linewidth=1, linestyle=(0, (4, 3)))
ax.annotate(f"base rate {100*train.churned_90d.mean():.1f}%", (10.4, 100*train.churned_90d.mean()),
            (0, 4), textcoords="offset points", ha="right", color=INK2, fontsize=9)
ax.set_xticks(range(1, 11)); ax.set_xlabel("recency decile (1 = most recently active)")
ax.set_ylabel("churn rate (%)"); ax.set_ylim(0, 80)
ax.set_title(f"Recency separates churners by {lift.churn.iloc[-1]-lift.churn.iloc[0]:+.1f} points")
plt.tight_layout(); plt.show()
display(lift)
"""),

code("""
# the directional check -- does each feature behave the way domain knowledge expects?
# same ten features, same expected signs, as the table in answers/part2-features.md
expect = {"recency_days": "+", "avg_gap_days": "+", "recency_vs_own_cadence": "+",
          "txn_count_90d": "-", "freq_trend_ratio": "-", "txn_count_lifetime": "-",
          "monetary_lifetime": "-", "points_balance": "-", "ever_redeemed_flag": "-",
          "is_cross_brand": "-"}
rows = []
for f, e in expect.items():
    s = train[[f, "churned_90d"]].dropna()
    c = s[f].corr(s.churned_90d)
    rows.append({"feature": f, "corr": round(c, 3), "expected": e,
                 "actual": "+" if c > 0 else "-",
                 "verdict": "ok" if ("+" if c > 0 else "-") == e else "INVERTED"})
chk = pd.DataFrame(rows).sort_values("corr")
display(chk)

GOOD, CRITICAL = "#0ca30c", "#d03b3b"
fig, ax = plt.subplots(figsize=(9, 4.4))
colors = [GOOD if v == "ok" else CRITICAL for v in chk.verdict]
bars = ax.barh(chk.feature, chk["corr"], color=colors, edgecolor="#fcfcfb", linewidth=2, height=0.68)
for b, v, verdict in zip(bars, chk["corr"], chk.verdict):
    off = 4 if v >= 0 else -4
    ax.annotate(f"{v:+.3f}" + ("  ✗" if verdict == "INVERTED" else "  ✓"),
                (v, b.get_y()+b.get_height()/2), (off, 0), textcoords="offset points",
                va="center", ha="left" if v >= 0 else "right", fontsize=9, color=INK)
clean_axes(ax, ygrid=False)
ax.axvline(0, color=INK2, linewidth=1)
ax.set_xlim(-0.32, 0.34); ax.set_xlabel("correlation with churn")
n_bad = int((chk.verdict == "INVERTED").sum())
ax.set_title(f"{n_bad} of {len(chk)} features contradict domain expectation")
from matplotlib.patches import Patch
ax.legend(handles=[Patch(facecolor=GOOD, label="matches expectation ✓"),
                   Patch(facecolor=CRITICAL, label="inverted ✗")], loc="lower right")
plt.tight_layout(); plt.show()

bad = list(chk.loc[chk.verdict == "INVERTED", "feature"])
print(f"{len(bad)} inverted: " + ", ".join(bad))
print("\\nAll of them accumulate VOLUME. Root cause is 00_discovery.ipynb Catch 3:")
print("corr(txns before cutoff, txns after) is NEGATIVE, so observed volume is")
print("anti-predictive here. Recommendation: ship the recency/trend family, block the")
print("volume family pending an explanation from whoever generates this data.")
"""),

md("""
The colour here carries a verdict, so it is paired with a ✓/✗ glyph and the `verdict` column above —
never colour alone.

---

The hardened, assertion-backed version of every check in this notebook is `scripts/06_validate.py`.
Run `bash run_all.sh` to rebuild everything from the two CSVs.
"""),

code("""
con.close()
print("done")
"""),
    ]
