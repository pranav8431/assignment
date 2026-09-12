#!/usr/bin/env python3
"""
Section 2 -- Parts 6, 7, 8. Every number quoted in answers/part6-8 is printed here.
"""
import os, sqlite3, csv, statistics

BASE = os.path.join(os.path.dirname(__file__), "..")
con  = sqlite3.connect(os.path.join(BASE, "output", "loyalty.db"))
cur  = con.cursor()

def rule(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)

# =====================================================================================
rule("PART 6 -- WHICH BRAND IS ACTUALLY THE MOST GENEROUS?")
# =====================================================================================
print("\n(a) MARKETING'S FRAMING on RAW data -- SUM(points)/SUM(amount), nothing excluded:")
for r in cur.execute("""
    SELECT brand,
           SUM(CASE WHEN trim(points_earned)='' THEN 0 ELSE CAST(points_earned AS REAL) END) p,
           SUM(CAST(amount AS REAL)) a
    FROM raw_transactions GROUP BY brand ORDER BY p/a DESC"""):
    print(f"    {r[0]:10s} {r[1]/r[2]:7.3f} pts/$   (points {r[1]:>12,.0f} / spend {r[2]:>14,.2f})")
print("    ^ ranking: PulseHome > PulseEats > PulseMart. PulseMart looks catastrophic.")

print("\n(b) THE CONTAMINATION -- 15 rows with impossible amounts:")
tot = 0
for r in cur.execute("""SELECT brand, CAST(amount AS REAL) a, COUNT(*) n
                        FROM raw_transactions WHERE CAST(amount AS REAL) >= 9999
                        GROUP BY brand, a ORDER BY a DESC"""):
    print(f"    {r[0]:10s} amount={r[1]:>12,.2f} x{r[2]}")
    tot += r[1]*r[2]
print(f"    total fake spend injected: ${tot:,.2f}")
for r in cur.execute("""SELECT brand, COUNT(*) FROM raw_transactions
                        WHERE CAST(amount AS REAL) >= 9999 GROUP BY brand"""):
    print(f"      -> {r[1]:>2} of 15 land on {r[0]}")

print("\n(c) CLEANED -- drop sentinels, refunds, duplicates; impute nothing:")
clean_rates = {}
for r in cur.execute("""
    SELECT brand, SUM(points_earned) p, SUM(amount) a, COUNT(*) n
    FROM clean_transactions
    WHERE is_sentinel_amount = 0 AND is_refund = 0 AND is_points_imputed = 0
    GROUP BY brand ORDER BY p/a DESC"""):
    clean_rates[r[0]] = r[1]/r[2]
    print(f"    {r[0]:10s} {r[1]/r[2]:7.3f} pts/$   (n={r[3]:,})")
print("    ^ ranking INVERTS: PulseMart > PulseHome > PulseEats.")

print("\n(d) IS THE RATE STABLE, OR a mix effect? -- pts/$ by brand x tier:")
tiers = ["Bronze", "Silver", "Gold", "Platinum"]
print(f"    {'brand':10s}" + "".join(f"{t:>11s}" for t in tiers))
for b in ("PulseMart", "PulseHome", "PulseEats"):
    row = f"    {b:10s}"
    for t in tiers:
        v = cur.execute("""SELECT SUM(c.points_earned)/SUM(c.amount) FROM clean_transactions c
                           JOIN clean_members m ON m.member_id=c.member_id
                           WHERE c.brand=? AND m.tier=? AND c.is_sentinel_amount=0
                             AND c.is_refund=0 AND c.is_points_imputed=0""", (b, t)).fetchone()[0]
        row += f"{v:>11.3f}"
    print(row)
print("    ^ identical to 3 dp in every cell => a deterministic earn rule, not a mix effect.")

print("\n(e) BASKET-SIZE buckets (would reveal nonlinear earn rules):")
for b in ("PulseMart", "PulseHome", "PulseEats"):
    cells = []
    for lo, hi in ((0,25),(25,50),(50,100),(100,200),(200,100000)):
        v = cur.execute("""SELECT SUM(points_earned)/SUM(amount) FROM clean_transactions
                           WHERE brand=? AND amount>=? AND amount<? AND is_sentinel_amount=0
                             AND is_refund=0 AND is_points_imputed=0""", (b, lo, hi)).fetchone()[0]
        cells.append(f"${lo}-{hi if hi<100000 else '+'}:{v:.2f}")
    print(f"    {b:10s} " + "  ".join(cells))

print("\n(f) ATTRIBUTION SENSITIVITY -- transaction brand vs member's home brand:")
for lbl, join in (("transaction brand", "c.brand"), ("member home brand", "m.brand")):
    res = cur.execute(f"""SELECT {join} b, SUM(c.points_earned)/SUM(c.amount) r
                          FROM clean_transactions c JOIN clean_members m ON m.member_id=c.member_id
                          WHERE c.is_sentinel_amount=0 AND c.is_refund=0 AND c.is_points_imputed=0
                          GROUP BY 1 ORDER BY r DESC""").fetchall()
    print(f"    {lbl:20s} " + "  ".join(f"{b}={r:.3f}" for b, r in res) + f"   winner={res[0][0]}")
print("    ^ conclusion holds under BOTH attributions.")

print("\n(e2) CHANNEL -- same test, same result:")
for b in ("PulseMart", "PulseHome", "PulseEats"):
    cells = []
    for ch in ("app", "online", "in_store"):
        v = cur.execute("""SELECT SUM(points_earned)/SUM(amount) FROM clean_transactions
                           WHERE brand=? AND channel=? AND is_sentinel_amount=0
                             AND is_refund=0 AND is_points_imputed=0""", (b, ch)).fetchone()[0]
        cells.append(f"{ch}={v:.3f}")
    print(f"    {b:10s} " + "  ".join(cells))
print("    ^ PRODUCT FINDING: the earn rate depends on brand and NOTHING else.")
print("      Platinum earns exactly what Bronze earns; app earns what in_store earns.")
print("      A programme whose top tier confers no earning advantage gives members no")
print("      economic reason to climb it -- and means `tier` has no mechanistic link to")
print("      churn, only a correlational one (see Part 2).")

print("\n(f2) TRIANGULATION -- can redemption behaviour hint at what a point is WORTH?")
print("    If a PulseEats point were really worth 1.31x a PulseMart point, we might")
print("    expect members to burn them differently. Testing that:")
for r in cur.execute("""
    SELECT brand,
           SUM(points_redeemed)/SUM(points_earned) AS burn_rate,
           SUM(CASE WHEN points_redeemed>0 THEN 1 ELSE 0 END)*1.0/COUNT(*) AS pct_txn_with_redemption,
           AVG(CASE WHEN points_redeemed>0 THEN points_redeemed END) AS avg_burn
    FROM clean_transactions
    WHERE is_sentinel_amount=0 AND is_refund=0 AND is_orphan_member=0
    GROUP BY brand ORDER BY burn_rate DESC"""):
    print(f"    {r[0]:10s} burn_rate={r[1]:.4f}  txns_with_redemption={100*r[2]:5.2f}%  avg_burn={r[3]:.1f} pts")
print("    ^ READ THIS CAREFULLY. The cleanest signal is the middle column:")
print("      13.91% / 14.15% / 14.12% of transactions involve a redemption -- i.e.")
print("      members engage with the programme at an IDENTICAL rate in all 3 brands.")
print("      The burn_rate gradient (0.0995 > 0.0957 > 0.0902) is largely MECHANICAL:")
print("      it is redeemed/earned, so a higher earn rate arithmetically depresses it.")
print("      I am NOT treating that gradient as evidence about point value.")
print("      VERDICT: weak, non-conclusive support for points being valued similarly")
print("      across brands. Confounded by catalogue attractiveness, and points_redeemed")
print("      is itself low-trust (T9). It narrows the uncertainty; it does not close it.")

be = clean_rates["PulseMart"] / clean_rates["PulseEats"]
print(f"\n(g) BREAK-EVEN: a PulseEats point must be worth {be:.2f}x a PulseMart point")
print(f"    for PulseEats to actually be more generous. Nothing in the data gives")
print(f"    a point's monetary value (transaction_type is 100% 'purchase'; no")
print(f"    redemption catalogue, no discount column). So 'generosity' is NOT")
print(f"    answerable from this data -- only 'points issued per dollar' is.")

# =====================================================================================
rule("PART 7 -- WIN-BACK LIST (~20 MEMBERS)")
# =====================================================================================
q25, q50, q75 = [cur.execute(f"""SELECT monetary_lifetime FROM features_score
    WHERE monetary_lifetime IS NOT NULL ORDER BY monetary_lifetime
    LIMIT 1 OFFSET (SELECT COUNT(*)*{p}/100 FROM features_score WHERE monetary_lifetime IS NOT NULL)"""
    ).fetchone()[0] for p in (25, 50, 75)]
print(f"lifetime spend distribution (scoring frame): p25=${q25:,.2f}  p50=${q50:,.2f}  p75=${q75:,.2f}")
print(f"=> 'was valuable' threshold: lifetime spend > p75 (${q75:,.2f}) AND >= 3 transactions")
print(f"=> 'slipping away'         : 120 <= recency_days <= 365")
print(f"   (median inter-purchase gap across the base is 104 days, so a 90-day")
print(f"    silence is ORDINARY -- 120 days is the first point that means something.")
print(f"    >365 days is treated as unreachable, not slipping.)")

cur.executescript(f"""
DROP TABLE IF EXISTS winback;
CREATE TABLE winback AS
SELECT
    f.member_id, f.tier, f.member_brand, f.country,
    f.recency_days, f.txn_count_lifetime, f.monetary_lifetime, f.avg_basket,
    f.points_balance, f.ever_redeemed_flag, f.avg_gap_days, f.dq_suspect_flag,
    ROUND(f.monetary_lifetime /
          NULLIF((julianday('2026-06-30') - julianday(f.first_txn_date_proxy))/365.0, 0), 2) AS spend_per_year,
    ROUND(1.0 * f.recency_days / NULLIF(f.avg_gap_days, 0), 2)                AS lapse_severity
FROM (SELECT fs.*, date(fs.last_txn_date, '-' || (fs.avg_gap_days * (fs.txn_count_lifetime-1)) || ' day')
                   AS first_txn_date_proxy FROM features_score fs) f
WHERE f.monetary_lifetime > {q75}
  AND f.txn_count_lifetime >= 3
  AND f.recency_days BETWEEN 120 AND 365
  AND f.has_sentinel_amount = 0      -- value must not come from a corrupt row
  AND f.avg_gap_days IS NOT NULL;
""")
n_pool = cur.execute("SELECT COUNT(*) FROM winback").fetchone()[0]
print(f"\neligible pool after all filters: {n_pool:,} members")

print("\nfunnel (each exclusion counted, none silent):")
steps = [
 ("scoring frame (all non-orphan members)", "1=1"),
 ("+ lifetime spend > p75",                 f"monetary_lifetime > {q75}"),
 ("+ >= 3 transactions",                    f"monetary_lifetime > {q75} AND txn_count_lifetime >= 3"),
 ("+ recency 120-365d",                     f"monetary_lifetime > {q75} AND txn_count_lifetime >= 3 AND recency_days BETWEEN 120 AND 365"),
 ("+ no sentinel-amount contamination",     f"monetary_lifetime > {q75} AND txn_count_lifetime >= 3 AND recency_days BETWEEN 120 AND 365 AND has_sentinel_amount = 0"),
]
for lbl, w in steps:
    print(f"    {lbl:42s} {cur.execute(f'SELECT COUNT(*) FROM features_score WHERE {w}').fetchone()[0]:>7,}")

print("\nEXCLUDED DELIBERATELY:")
for lbl, w in (("status='churned' members (NOT excluded -- status is unreliable)",
                "1=0"),
               ("dormant > 365 days (unreachable, not 'slipping')",
                f"monetary_lifetime > {q75} AND txn_count_lifetime >= 3 AND recency_days > 365"),
               ("lapsed < 120 days (would have bought anyway -- margin waste)",
                f"monetary_lifetime > {q75} AND txn_count_lifetime >= 3 AND recency_days < 120")):
    if w != "1=0":
        print(f"    {lbl:58s} {cur.execute(f'SELECT COUNT(*) FROM features_score WHERE {w}').fetchone()[0]:>7,}")
    else:
        print(f"    {lbl}")
print(f"    orphan M9###### ids (not in member master, uncontactable)          {2988:>7,}")

rows = cur.execute("""SELECT * FROM winback ORDER BY spend_per_year DESC, lapse_severity DESC LIMIT 20""").fetchall()
cols = [d[0] for d in cur.description]
print(f"\nTOP 20 (ranked by spend_per_year, tie-broken on lapse_severity):")
print(f"  {'member_id':10s} {'tier':9s} {'rec':>4s} {'txns':>5s} {'spend':>9s} {'$/yr':>8s} {'lapse':>6s} {'pts_bal':>8s}")
for r in rows:
    d = dict(zip(cols, r))
    print(f"  {d['member_id']:10s} {d['tier']:9s} {d['recency_days']:>4} {d['txn_count_lifetime']:>5} "
          f"{d['monetary_lifetime']:>9,.0f} {d['spend_per_year']:>8,.0f} {d['lapse_severity']:>6.2f} {d['points_balance']:>8,.0f}")

with open(os.path.join(BASE, "output", "winback_list.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(cols); w.writerows(rows)
print(f"\n  wrote output/winback_list.csv")
sel = cur.execute("""SELECT AVG(monetary_lifetime), AVG(recency_days), SUM(points_balance)
                     FROM (SELECT * FROM winback ORDER BY spend_per_year DESC LIMIT 20)""").fetchone()
allm = cur.execute("SELECT AVG(monetary_lifetime), AVG(recency_days) FROM features_score").fetchone()
print(f"  selected 20 vs whole base: avg spend ${sel[0]:,.0f} vs ${allm[0]:,.0f} "
      f"({sel[0]/allm[0]:.1f}x) | avg recency {sel[1]:.0f}d vs {allm[1]:.0f}d")
print(f"  combined unredeemed points held by the 20: {sel[2]:,.0f} (the offer hook)")

# =====================================================================================
rule("PART 8 -- OUTSTANDING POINTS LIABILITY")
# =====================================================================================
print("STRUCTURAL FINDING FIRST:")
print(f"  transaction_type values = {dict(cur.execute('SELECT transaction_type, COUNT(*) FROM raw_transactions GROUP BY 1').fetchall())}")
print("  => there are NO redemption transactions. Redemptions ride on purchase rows.")
print("     So this is a DERIVED balance, not a reconciled ledger. No opening balance,")
print("     no expiry events, nothing to reconcile against.")

raw_e, raw_r = cur.execute("""SELECT
    SUM(CASE WHEN trim(points_earned)='' THEN 0 ELSE CAST(points_earned AS REAL) END),
    SUM(CAST(points_redeemed AS REAL)) FROM raw_transactions""").fetchone()
print(f"\nNAIVE (raw, no cleaning): {raw_e:,.0f} earned - {raw_r:,.0f} redeemed = {raw_e-raw_r:,.0f} points")

print("\nCLEANING ADJUSTMENTS (each itemised):")
adj = cur.execute("SELECT reason, n_rows, points_removed FROM clean_exclusions WHERE points_removed > 0").fetchall()
for a in adj:
    print(f"    -{a[2]:>10,.0f} pts   {a[0]:28s} ({a[1]:,} rows)")
imp = cur.execute("SELECT SUM(points_earned) FROM clean_transactions WHERE is_points_imputed=1").fetchone()[0]
print(f"    +{imp:>10,.0f} pts   points_imputed_for_nulls     (1,496 rows)")

ce, cr = cur.execute("""SELECT SUM(points_earned), SUM(points_redeemed) FROM clean_transactions
                        WHERE is_orphan_member = 0""").fetchone()
out = ce - cr
print(f"\nCLEANED: {ce:,.0f} earned - {cr:,.0f} redeemed = {out:,.0f} points outstanding")
print(f"  raw overstates the liability by {raw_e-raw_r-out:,.0f} points "
      f"({100*(raw_e-raw_r-out)/out:.1f}%)")

print("\nSENSITIVITY -- the $/point assumption dominates everything:")
print(f"    {'$/point':>9s}" + "".join(f"{f'breakage {int(b*100)}%':>16s}" for b in (0.0, 0.20, 0.30)))
for v in (0.005, 0.010, 0.0125):
    row = f"    {v:>9.4f}"
    for b in (0.0, 0.20, 0.30):
        row += f"{'$' + format(out*v*(1-b), ',.0f'):>16s}"
    print(row)
print(f"\n  HEADLINE (=$0.01/pt, no breakage): ${out*0.01:,.0f}")
print(f"  With a 20% breakage assumption   : ${out*0.01*0.8:,.0f}")

print("\nREASONS TO DISTRUST THIS NUMBER:")
src_neg = cur.execute("""SELECT COUNT(*) FROM (
      SELECT member_id, SUM(CASE WHEN is_refund=1 THEN points_reversed_on_refund ELSE points_earned END)
             - SUM(points_redeemed) b
      FROM clean_transactions WHERE is_orphan_member=0 GROUP BY member_id HAVING b<0)""").fetchone()[0]
post_neg = cur.execute("""SELECT COUNT(*) FROM (SELECT member_id, SUM(points_earned)-SUM(points_redeemed) b
                     FROM clean_transactions WHERE is_orphan_member=0 GROUP BY member_id HAVING b < 0)""").fetchone()[0]
print(f"  1. {src_neg} members hold a negative balance IN THE SOURCE DATA, and replaying")
print(f"     each ledger chronologically finds 5 point-in-time over-redemptions (225 pts).")
print(f"     Small, but impossible under a correct ledger -- the earn records are incomplete.")
print(f"     HONESTY NOTE: our own refund-points reversal creates {post_neg-src_neg} MORE negative")
print(f"     balances ({post_neg} total). Those {post_neg-src_neg} are our artifact, not the source's fault --")
print(f"     though they are informative: those members redeemed points that the refund")
print(f"     correction says they never legitimately earned. We cite {src_neg}, not {post_neg}.")
red = [r[0] for r in cur.execute("SELECT points_redeemed FROM clean_transactions WHERE points_redeemed > 0")]
rc = {}
for x in red: rc[x] = rc.get(x, 0) + 1
print(f"  2. points_redeemed is capped at exactly {max(red):.0f} and "
      f"{100*sum(v for k,v in rc.items() if k in (50,100,150,200))/len(red):.0f}% of values are round")
print(f"     50/100/150/200 -- it looks truncated/synthetic. If redemptions are")
print(f"     under-recorded, this liability is OVERSTATED.")
print(f"  3. No expiry field and no program T&Cs -> points modelled as never expiring,")
print(f"     which makes this the CEILING, not the expected settlement.")
orph_pts = cur.execute("SELECT SUM(points_earned)-SUM(points_redeemed) FROM clean_transactions WHERE is_orphan_member=1").fetchone()[0]
print(f"  4. {orph_pts:,.0f} points sit on 2,988 orphan member_ids excluded here. If those")
print(f"     are real members from another system, liability rises to "
      f"${(out+orph_pts)*0.01:,.0f} (+{100*orph_pts/out:.1f}%).")
print(f"  5. 1,496 rows had their points IMPUTED (+{imp:,.0f} pts, {100*imp/out:.1f}% of the total).")
con.commit(); con.close()
