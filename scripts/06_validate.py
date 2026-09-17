#!/usr/bin/env python3
"""
Validation. Nothing in the write-up is quoted unless it is asserted here.

Covers:
  1. structural assertions (grain, reconciliation, derived earn rates)
  2. LEAKAGE assertion  -- features at T must not move when data after T arrives
  3. decile lift        -- do the features actually separate churners?
  4. directional sanity -- does each feature's sign match domain expectation?
  5. grouped holdout    -- does the lift survive out of sample?
"""
import os, sqlite3, statistics, random

BASE = os.path.join(os.path.dirname(__file__), "..")
con  = sqlite3.connect(os.path.join(BASE, "output", "loyalty.db"))
cur  = con.cursor()
FAIL = []

def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{('  -- ' + detail) if detail else ''}")
    if not cond:
        FAIL.append(name)

def rule(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)

rule("1. STRUCTURAL ASSERTIONS")
n_feat, n_dist = cur.execute("SELECT COUNT(*), COUNT(DISTINCT member_id) FROM churn_training").fetchone()
check("one row per member in the training frame", n_feat == n_dist, f"{n_feat:,} rows / {n_dist:,} members")
n_m, n_dm = cur.execute("SELECT COUNT(*), COUNT(DISTINCT member_id) FROM clean_members").fetchone()
check("clean_members is deduplicated", n_m == n_dm == 50010, f"{n_m:,} rows")
n_t = cur.execute("SELECT COUNT(*) FROM clean_transactions").fetchone()[0]
check("clean_transactions = raw - duplicates", n_t == 194311 - 1995, f"{n_t:,}")

rates = dict(cur.execute("SELECT brand, earn_rate FROM v_brand_earn_rate").fetchall())
check("brand earn rates derived, deterministic",
      rates == {"PulseEats": 1.75, "PulseHome": 2.0, "PulseMart": 2.3}, str(rates))

raw = cur.execute("SELECT SUM(CASE WHEN trim(points_earned)='' THEN 0 ELSE CAST(points_earned AS REAL) END) FROM raw_transactions").fetchone()[0]
removed = cur.execute("SELECT SUM(points_removed) FROM clean_exclusions").fetchone()[0]
imputed = cur.execute("SELECT SUM(points_earned) FROM clean_transactions WHERE is_points_imputed=1").fetchone()[0]
clean = cur.execute("SELECT SUM(points_earned) FROM clean_transactions WHERE is_orphan_member=0").fetchone()[0]
check("points reconcile: raw - removed + imputed == clean",
      abs(raw - removed + imputed - clean) < 1,
      f"{raw:,.0f} - {removed:,.0f} + {imputed:,.0f} = {raw-removed+imputed:,.0f} vs {clean:,.0f}")

base = cur.execute("SELECT AVG(churned_90d) FROM churn_training").fetchone()[0]
check("base rate is 58.8% +/- 0.1", abs(base - 0.588) < 0.001, f"{100*base:.1f}%")

rule("1b. HONESTY ASSERTIONS -- do not cite our own artifacts as source-data evidence")
# Part 8 originally claimed "21 members have a negative point balance,
# which proves the source ledger is incomplete." Only 5 of those exist in the source.
# The other 16 are created by OUR refund-points reversal. These assertions pin the
# split so the claim can never silently drift back.
src_neg = cur.execute("""
    SELECT COUNT(*) FROM (
      SELECT member_id,
             SUM(CASE WHEN is_refund = 1 THEN points_reversed_on_refund ELSE points_earned END)
             - SUM(points_redeemed) AS b
      FROM clean_transactions WHERE is_orphan_member = 0
      GROUP BY member_id HAVING b < 0)""").fetchone()[0]
post_neg = cur.execute("""
    SELECT COUNT(*) FROM (
      SELECT member_id, SUM(points_earned) - SUM(points_redeemed) AS b
      FROM clean_transactions WHERE is_orphan_member = 0
      GROUP BY member_id HAVING b < 0)""").fetchone()[0]
print(f"  negative balances in the SOURCE data            : {src_neg}")
print(f"  negative balances AFTER our refund reversal     : {post_neg}")
print(f"  created by our own fix                          : {post_neg - src_neg}")
check("source-data negative balances == 5", src_neg == 5, f"{src_neg}")
check("post-cleaning negative balances == 21", post_neg == 21, f"{post_neg}")
# the write-up is split by part; read every markdown file so the prose checks
# below don't silently pass just because a section moved to another file
import glob as _glob
_files = sorted(_glob.glob(os.path.join(BASE, "answers", "*.md")))
_ans = "\n".join(open(f).read() for f in _files)
print(f"  write-up spans {len(_files)} files, {len(_ans.split()):,} words")
check("the write-up states the corrected claim (5 in source, 16 self-inflicted)",
      "Five members have a negative points balance in the source data" in _ans
      and "The other 16 were created by my own refund fix" in _ans
      and "is **5, not 21**" in _ans,
      "asserts the prose, not just the data")
check("the write-up no longer asserts 21 as source-data evidence",
      "21 members have a negative point balance.** Impossible" not in _ans)
_expected = {f"part{i}" for i in range(1, 9)} | {"decision-log"}
_found = {os.path.basename(f).split("-")[0] if os.path.basename(f).startswith("part")
          else os.path.basename(f)[:-3] for f in _files}
check("all 8 part files and the decision log are present in answers/",
      _expected <= _found, f"missing: {sorted(_expected - _found) or 'none'}")

# Identity resolution: emails shared across DIFFERENT member_ids (Part 1, M2b)
import csv as _csv, collections as _c
_sh = _c.defaultdict(set)
for _m in _csv.DictReader(open(os.path.join(BASE, "members.csv"))):
    _sh[_m["email"].strip().lower()].add(_m["member_id"])
_multi = {e: v for e, v in _sh.items() if len(v) > 1}
_ids = set()
for _v in _multi.values():
    _ids |= _v
print(f"  emails mapping to >1 member_id: {len(_multi)}  ({len(_ids)} member_ids)")
check("shared-email accounts == 20 emails / 40 member_ids",
      len(_multi) == 20 and len(_ids) == 40, f"{len(_multi)}/{len(_ids)}")
_inb = cur.execute(
    f"SELECT COUNT(*) FROM churn_training WHERE member_id IN ({','.join('?'*len(_ids))})",
    list(_ids)).fetchone()[0]
print(f"  of those, present in the training cohort: {_inb}  <- label noise")
check("shared-email label noise is quantified, not hand-waved", _inb > 0, f"{_inb} members")

rule("2. LEAKAGE ASSERTION (the failure mode this design exists to prevent)")
# recency in the TRAINING frame must be computed only from data <= T. If it were
# computed over all data it would encode the outcome window directly.
rows = cur.execute("""
    SELECT t.member_id, t.recency_days, t.churned_90d,
           CAST(julianday('2026-06-30') - julianday(s.last_txn_date) AS INT) AS recency_all_data
    FROM churn_training t JOIN features_score s ON s.member_id = t.member_id
""").fetchall()

def corr(x, y):
    mx, my = statistics.mean(x), statistics.mean(y)
    cv = sum((a-mx)*(b-my) for a, b in zip(x, y)) / len(x)
    sx, sy = statistics.pstdev(x), statistics.pstdev(y)
    return cv / (sx*sy) if sx and sy else 0.0

lab   = [r[2] for r in rows]
right = [r[1] for r in rows]
wrong = [r[3] for r in rows]
c_r, c_w = corr(right, lab), corr(wrong, lab)
print(f"  corr(recency computed <= T      , label) = {c_r:.3f}   <- legitimate")
print(f"  corr(recency computed over ALL  , label) = {c_w:.3f}   <- leaks the answer")
check("point-in-time recency is materially weaker than the leaked version",
      c_w > c_r + 0.3, f"gap = {c_w - c_r:.3f}")

# no feature in the training frame may reference a date after T
mx = cur.execute("SELECT MAX(last_txn_date) FROM churn_training").fetchone()[0]
check("no training feature uses data after the cutoff", mx <= "2026-04-01", f"max last_txn_date = {mx}")

rule("3. DECILE LIFT -- do the features separate churners?")
def lift(col, label="churned_90d", table="churn_training", n_bins=10):
    rs = [r for r in cur.execute(
        f"SELECT {col}, {label} FROM {table} WHERE {col} IS NOT NULL").fetchall()]
    rs.sort(key=lambda r: r[0])
    if not rs: return None
    step = max(1, len(rs)//n_bins)
    print(f"\n  {col}   (n={len(rs):,})")
    print(f"    {'decile':>6} {'range':>18} {'n':>7} {'churn':>8}")
    out = []
    for i in range(n_bins):
        g = rs[i*step:(i+1)*step] if i < n_bins-1 else rs[(n_bins-1)*step:]
        if not g: continue
        cr = sum(r[1] for r in g)/len(g)
        out.append(cr)
        print(f"    {i+1:>6} {f'{g[0][0]:g}-{g[-1][0]:g}':>18} {len(g):>7,} {100*cr:>7.1f}%")
    print(f"    spread (last - first decile): {100*(out[-1]-out[0]):+.1f} pts")
    return out

r_lift = lift("recency_days")
check("recency separates churners by >20 points", r_lift[-1]-r_lift[0] > 0.20,
      f"{100*(r_lift[-1]-r_lift[0]):+.1f} pts")
mono = sum(1 for i in range(len(r_lift)-1) if r_lift[i+1] >= r_lift[i])
check("recency lift is near-monotonic", mono >= 8, f"{mono}/9 steps increase")

f_lift = lift("txn_count_lifetime")
lift("recency_vs_own_cadence")

rule("4. DIRECTIONAL SANITY -- does each feature behave as domain knowledge expects?")
print(f"  {'feature':28s} {'corr w/ churn':>14s}  {'expected':>9s}  verdict")
expectations = {
    "recency_days":            "+",
    "txn_count_lifetime":      "-",
    "txn_count_90d":           "-",
    "monetary_lifetime":       "-",
    "freq_trend_ratio":        "-",
    "points_balance":          "-",
    "ever_redeemed_flag":      "-",
    "is_cross_brand":          "-",
    "avg_gap_days":            "+",
    "recency_vs_own_cadence":  "+",
}
anomalies = []
for f, exp in expectations.items():
    rs = cur.execute(f"SELECT {f}, churned_90d FROM churn_training WHERE {f} IS NOT NULL").fetchall()
    c = corr([r[0] for r in rs], [r[1] for r in rs])
    got = "+" if c > 0 else "-"
    ok = (got == exp) or abs(c) < 0.02
    if not ok: anomalies.append((f, c, exp))
    print(f"  {f:28s} {c:>+14.3f}  {exp:>9s}  {'ok' if ok else '*** INVERTED ***'}")

print(f"\n  {len(anomalies)} feature(s) contradict domain expectation:")
for f, c, exp in anomalies:
    print(f"    - {f}: corr={c:+.3f}, expected sign {exp}")

# Root cause: is there a fixed lifetime transaction budget per member?
before_after = cur.execute("""
    SELECT f.txn_count_lifetime,
           (SELECT COUNT(*) FROM clean_transactions c
             WHERE c.member_id = f.member_id AND c.txn_date > '2026-04-01')
    FROM features_train f
""").fetchall()
cba = corr([r[0] for r in before_after], [r[1] for r in before_after])
print(f"\n  corr(txns BEFORE cutoff, txns AFTER cutoff) = {cba:+.3f}")
print( "    real behaviour  => POSITIVE (frequent buyers keep buying)")
print( "    measured        => NEGATIVE = each member has a near-fixed lifetime")
print( "                       transaction budget, so frequency is ANTI-predictive here.")
check("frequency anomaly is detected and explained, not silently shipped",
      cba < 0 and len(anomalies) > 0, f"corr={cba:+.3f}")

rule("5. GROUPED HOLDOUT -- does the lift survive out of sample?")
ids = [r[0] for r in cur.execute("SELECT DISTINCT member_id FROM churn_training").fetchall()]
random.seed(42); random.shuffle(ids)
hold = set(ids[:len(ids)//5])
rs = cur.execute("SELECT member_id, recency_days, churned_90d FROM churn_training").fetchall()
for nm, sel in (("train (80%)", lambda m: m not in hold), ("holdout (20%)", lambda m: m in hold)):
    g = sorted([r for r in rs if sel(r[0])], key=lambda r: r[1])
    step = len(g)//10
    d1 = sum(r[2] for r in g[:step])/step
    d10 = sum(r[2] for r in g[9*step:])/len(g[9*step:])
    print(f"  {nm:14s} n={len(g):>6,}  decile1 churn={100*d1:.1f}%  decile10 churn={100*d10:.1f}%  spread={100*(d10-d1):+.1f} pts")
g = sorted([r for r in rs if r[0] in hold], key=lambda r: r[1]); step = len(g)//10
check("holdout spread still exceeds 20 points",
      (sum(r[2] for r in g[9*step:])/len(g[9*step:]) - sum(r[2] for r in g[:step])/step) > 0.20)

rule("RESULT")
print(f"  {len(FAIL)} failed check(s)" + (": " + ", ".join(FAIL) if FAIL else " -- all assertions passed"))
con.close()
raise SystemExit(1 if FAIL else 0)
