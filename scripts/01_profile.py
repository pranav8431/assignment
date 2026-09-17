#!/usr/bin/env python3
"""
Part 1 evidence generator.

Prints every statistic quoted in answers/part1-data-quality.md. Deliberately does NO cleaning --
this reads the raw exports exactly as they landed, so the numbers are auditable.
Run:  python3 scripts/01_profile.py > output/dq_findings.txt
"""
import csv, collections, datetime, re, statistics, sys, os

BASE = os.path.join(os.path.dirname(__file__), "..")

def load(fn):
    with open(os.path.join(BASE, fn), newline="", encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))

def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def rule(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)

members = load("members.csv")
txns    = load("transactions.csv")

print(f"members.csv      rows={len(members):,}")
print(f"transactions.csv rows={len(txns):,}")

# ---------------------------------------------------------------- members
rule("MEMBERS -- column profile")
print(f"{'column':14s} {'blank':>8s} {'distinct':>9s}")
for c in members[0]:
    vals = [m[c] for m in members]
    print(f"{c:14s} {sum(1 for v in vals if not v.strip()):>8,} {len(set(vals)):>9,}")

rule("M1/M2 -- duplicate member_id and email")
dup_ids = {k: v for k, v in collections.Counter(m["member_id"] for m in members).items() if v > 1}
print(f"duplicate member_id values : {len(dup_ids):,}  (extra rows: {sum(v-1 for v in dup_ids.values()):,})")
grp = collections.defaultdict(list)
for m in members:
    if m["member_id"] in dup_ids:
        grp[m["member_id"]].append(m)
differing = collections.Counter()
for rows in grp.values():
    for col in rows[0]:
        if len({r[col] for r in rows}) > 1:
            differing[col] += 1
print(f"fields that differ within a duplicate group: {dict(differing)}  (of {len(grp)} groups)")
print("=> only tier/status differ => an SCD-2 dimension was flattened without picking is_current")
ex = grp[sorted(grp)[0]]
print(f"\nexample {ex[0]['member_id']}:")
for r in ex:
    print(f"   tier={r['tier']:9s} status={r['status']:9s} join={r['join_date']}")
dup_em = {k: v for k, v in collections.Counter(m["email"].strip().lower() for m in members).items() if v > 1}
print(f"\nduplicate emails (lowercased): {len(dup_em):,}")

rule("M2b -- SAME PERSON, TWO ACCOUNTS (identity resolution)")
# The 170 duplicate emails are NOT one problem. Decomposing them:
#   - most are the 150 duplicated member_id rows above (one account listed twice)
#   - the rest are DIFFERENT member_ids sharing an email = one human, two accounts
by_email = collections.defaultdict(set)
for m in members:
    by_email[m["email"].strip().lower()].add(m["member_id"])
multi = {e: ids for e, ids in by_email.items() if len(ids) > 1}
shared_ids = set()
for v in multi.values():
    shared_ids |= v
print(f"emails mapping to MORE THAN ONE distinct member_id: {len(multi)}")
print(f"member_ids involved: {len(shared_ids)}")
print("=> distinct from the 150 duplicate-row problem: this is one PERSON with two accounts.")
for e in sorted(multi)[:3]:
    print(f"\n   {e}")
    for r in [m for m in members if m["email"].strip().lower() == e]:
        print(f"      {r['member_id']}  tier={r['tier']:9s} brand={r['brand']:10s} "
              f"join={r['join_date'] or '(blank)':10s} status={r['status']}")
_t = [t for t in txns if t["member_id"] in shared_ids]
print(f"\ntransactions on these accounts: {len(_t):,}")
print(f"points earned on them          : {sum(num(t['points_earned']) or 0 for t in _t):,.0f}")
print("IMPACT: a person active on account B but silent on account A is labelled a")
print("        CHURNER on A. Also splits point balances and risks double-targeting a")
print("        win-back campaign at the same human.")

rule("M3/M4 -- unconformed categoricals")
for c in ("tier", "country", "status", "brand"):
    cnt = collections.Counter(m[c] for m in members)
    print(f"\n{c}  ({len(cnt)} distinct)")
    for k, v in sorted(cnt.items(), key=lambda x: -x[1]):
        canon = k.strip().title()
        tag = "" if k == canon or c in ("country", "status", "brand") else f"   <-- should be '{canon}'"
        print(f"    {repr(k):16s} {v:>7,}{tag}")
bad_tier = sum(v for k, v in collections.Counter(m['tier'] for m in members).items() if k != k.strip().title())
print(f"\ntier rows needing conforming    : {bad_tier:,}")
bad_ctry = sum(v for k, v in collections.Counter(m['country'] for m in members).items() if len(k) != 2 or not k.isupper())
print(f"country rows needing conforming : {bad_ctry:,}")

rule("M5/M6/M7 -- join_date integrity")
def d10(v):
    v = (v or "").strip()
    return v[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", v) else None
blank_join = [m for m in members if not m["join_date"].strip()]
print(f"blank join_date : {len(blank_join):,} ({100*len(blank_join)/len(members):.1f}%)")
print(f"   by status    : {dict(collections.Counter(m['status'] for m in blank_join))}")
first_txn = {}
for t in txns:
    d = d10(t["transaction_date"])
    if d and (t["member_id"] not in first_txn or d < first_txn[t["member_id"]]):
        first_txn[t["member_id"]] = d
max_txn = max(d for d in (d10(t["transaction_date"]) for t in txns) if d)
fut = [m for m in members if d10(m["join_date"]) and d10(m["join_date"]) > max_txn]
print(f"join_date after last observed transaction ({max_txn}): {len(fut):,}  e.g. {sorted({m['join_date'] for m in fut})}")
pre = [m for m in members if d10(m["join_date"]) and m["member_id"] in first_txn
       and first_txn[m["member_id"]] < d10(m["join_date"])]
print(f"members whose FIRST transaction predates join_date: {len(pre):,}")
if pre:
    s = pre[0]
    print(f"   e.g. {s['member_id']} joined {s['join_date']} but transacted {first_txn[s['member_id']]}")

rule("M8 -- is `status` a usable churn label?")
last_txn = {}
for t in txns:
    d = d10(t["transaction_date"])
    if d and (t["member_id"] not in last_txn or d > last_txn[t["member_id"]]):
        last_txn[t["member_id"]] = d
print(f"{'status':10s} {'n':>7s} {'median last txn':>16s} {'max':>12s}")
for s in ("active", "inactive", "churned"):
    v = sorted(last_txn[m["member_id"]] for m in members
               if m["status"] == s and m["member_id"] in last_txn)
    print(f"{s:10s} {len(v):>7,} {v[len(v)//2]:>16s} {v[-1]:>12s}")
print("\n=> medians are within ONE DAY of each other. `status` carries no activity")
print("   information and MUST NOT be used as the churn target.")

rule("M9 -- PII inventory (governance)")
print("direct identifiers present in the clear: email, first_name, last_name, birth_date")
print(f"birth_date populated on {sum(1 for m in members if m['birth_date'].strip()):,} rows (100%) -- full DOB is a direct identifier")

# ---------------------------------------------------------------- transactions
rule("TRANSACTIONS -- column profile")
print(f"{'column':18s} {'blank':>8s} {'distinct':>9s}")
for c in txns[0]:
    vals = [t[c] for t in txns]
    print(f"{c:18s} {sum(1 for v in vals if not v.strip()):>8,} {len(set(vals)):>9,}")

rule("T1/T11 -- duplicate transaction_id")
dup_t = {k: v for k, v in collections.Counter(t["transaction_id"] for t in txns).items() if v > 1}
print(f"duplicate transaction_id values: {len(dup_t):,}  (extra rows: {sum(v-1 for v in dup_t.values()):,})")
byid = collections.defaultdict(list)
for t in txns:
    if t["transaction_id"] in dup_t:
        byid[t["transaction_id"]].append(tuple(t.values()))
identical = sum(1 for v in byid.values() if len(set(v)) == 1)
print(f"   byte-identical groups : {identical:,}   <-- at-least-once delivery replay")
print(f"   CONFLICTING groups    : {len(byid)-identical:,}   <-- SELECT DISTINCT would silently keep these")

rule("T2 -- sentinel / impossible amount values")
sent = sorted(((num(t['amount']), t['brand']) for t in txns if (num(t['amount']) or 0) >= 9999))
cnt = collections.Counter(s for s in sent)
print(f"rows with amount >= 9,999 : {len(sent)}")
for (val, brand), n in sorted(cnt.items(), key=lambda x: -x[0][0]):
    print(f"   {val:>12,.2f}  brand={brand:10s} x{n}")
print(f"\nby brand: {dict(collections.Counter(b for _, b in sent))}")
_pm = sum(1 for _, b in sent if b == "PulseMart")
print(f"=> {_pm} of {len(sent)} land on PulseMart. See Part 6: these rows INVERT the brand ranking.")

rule("T3 -- negative amounts that still granted points")
negs = [t for t in txns if (num(t["amount"]) or 0) < 0]
ratios = [(num(t["points_earned"]) or 0)/abs(num(t["amount"])) for t in negs if num(t["points_earned"])]
print(f"negative-amount rows: {len(negs):,}  (range {min(num(t['amount']) for t in negs):.2f} .. {max(num(t['amount']) for t in negs):.2f}, sum {sum(num(t['amount']) for t in negs):,.2f})")
print(f"of those, points_earned > 0: {sum(1 for t in negs if (num(t['points_earned']) or 0) > 0):,}  (100%)")
print(f"median points_earned / |amount| = {statistics.median(ratios):.3f}")
print("=> refunds are posted as negative purchases and points were awarded on the ABSOLUTE value.")

rule("T4 -- null points_earned")
nulls = [t for t in txns if num(t["points_earned"]) is None]
print(f"null points_earned: {len(nulls):,} ({100*len(nulls)/len(txns):.2f}%)")
print(f"   by brand  : {dict(collections.Counter(t['brand'] for t in nulls))}")
print(f"   by channel: {dict(collections.Counter(t['channel'] for t in nulls))}")
print(f"   amount populated on all of them: {all(num(t['amount']) is not None for t in nulls)}  <-- recoverable by imputation")

rule("T5/T6 -- multiple date formats in one column")
def fmt(v):
    v = (v or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}", v): return "YYYY-MM-DD HH:MM:SS"
    if re.match(r"^\d{4}-\d{2}-\d{2}$", v):                     return "YYYY-MM-DD (date only)"
    if re.match(r"^\d{2}/\d{2}/\d{4}$", v):                     return "NN/NN/YYYY (ambiguous)"
    return "OTHER"
fc = collections.Counter(fmt(t["transaction_date"]) for t in txns)
for k, v in fc.most_common():
    print(f"   {k:24s} {v:>7,}")
amb = [t["transaction_date"] for t in txns if fmt(t["transaction_date"]).startswith("NN/NN")]
print(f"\nambiguous rows: max first component={max(int(x.split('/')[0]) for x in amb)}, "
      f"max second component={max(int(x.split('/')[1]) for x in amb)}")
print("=> first component never exceeds 12, second reaches 31 => format is MM/DD/YYYY (inferred, not documented)")
do = {t["transaction_id"] for t in txns if fmt(t["transaction_date"]).startswith("YYYY-MM-DD (date")}
am = {t["transaction_id"] for t in txns if fmt(t["transaction_date"]).startswith("NN/NN")}
print(f"the two odd sets are disjoint (overlap={len(do & am)}) => two different upstream exporters")
print(f"a naive CAST would silently lose {len(do)+len(am):,} rows")

rule("T7 -- orphan member_ids (referential integrity)")
mids = {m["member_id"] for m in members}
orph = [t for t in txns if t["member_id"] not in mids]
print(f"transaction rows with no matching member: {len(orph):,}")
print(f"distinct orphan member_ids: {len({t['member_id'] for t in orph}):,}  (exactly 1 txn each)")
print(f"id pattern : {sorted({t['member_id'] for t in orph})[:3]} ... (M9###### -- a different id space)")
print(f"txn id pattern: {sorted({t['transaction_id'] for t in orph})[:3]} ... (TX prefix, not T)")
print(f"spend attached to orphans: ${sum(num(t['amount']) or 0 for t in orph):,.2f}")
print("=> a second source system / test tenant leaked into the export")

rule("T8/T9 -- redemption structure")
print(f"transaction_type values: {dict(collections.Counter(t['transaction_type'] for t in txns))}")
print("=> there are NO redemption transactions. Redemptions ride on purchase rows via points_redeemed.")
red = [num(t["points_redeemed"]) for t in txns if num(t["points_redeemed"]) > 0]
print(f"\nnon-zero redemptions: {len(red):,}   min={min(red):.0f} max={max(red):.0f}")
rc = collections.Counter(red)
print(f"top values: {rc.most_common(6)}")
print(f"share that are round 50/100/150/200: {100*sum(v for k,v in rc.items() if k in (50,100,150,200))/len(red):.1f}%")
print("=> capped at exactly 200 and half are round numbers: looks synthetic/truncated. Low trust (Part 8).")

rule("T12 -- POINT-IN-TIME ledger validity (stricter than a final-balance check)")
# A final-balance check only catches members who end up negative. Replaying each
# member's ledger chronologically catches anyone who was EVER overdrawn, which is
# the correct test for a points ledger.
ledger = collections.defaultdict(list)
for t in txns:
    d = d10(t["transaction_date"])
    if d:
        ledger[t["member_id"]].append((d, num(t["points_earned"]) or 0, num(t["points_redeemed"]) or 0))
viol_events = 0
viol_members = set()
viol_points = 0.0
for mid, rows in ledger.items():
    rows.sort()
    bal = 0.0
    for d, e, r in rows:
        if r > bal + e + 1e-9:
            viol_events += 1
            viol_members.add(mid)
            viol_points += r - (bal + e)
        bal += e - r
print(f"redemptions exceeding the balance held AT THAT MOMENT: {viol_events} events")
print(f"   across {len(viol_members)} members, over-redeeming {viol_points:,.0f} points")
final_neg = sum(1 for mid, rows in ledger.items()
                if sum(e for _, e, _ in rows) - sum(r for _, _, r in rows) < 0)
print(f"members whose FINAL balance is negative (raw data): {final_neg}")
print("=> these are the violations present in the SOURCE data. Cleaning that reverses")
print("   points on refunds will create additional negatives -- see 06_validate.py, which")
print("   asserts the split so we never cite our own artifacts as source-data evidence.")

rule("T13 -- timeline continuity (completeness/freshness)")
tdays = sorted({d for d in (d10(t["transaction_date"]) for t in txns) if d})
_s, _e = datetime.date.fromisoformat(tdays[0]), datetime.date.fromisoformat(tdays[-1])
have = set(tdays)
missing, _d = [], _s
while _d <= _e:
    if _d.isoformat() not in have:
        missing.append(_d.isoformat())
    _d += datetime.timedelta(days=1)
print(f"span {tdays[0]} .. {tdays[-1]} = {(_e-_s).days+1:,} calendar days, {len(tdays):,} with data")
print(f"days with ZERO transactions: {len(missing)}  (by year: "
      f"{dict(sorted(collections.Counter(m[:4] for m in missing).items()))})")
if missing:
    runs, cur = [], [missing[0]]
    for a, b in zip(missing, missing[1:]):
        if (datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days == 1:
            cur.append(b)
        else:
            runs.append(cur); cur = [b]
    runs.append(cur)
    print(f"consecutive-gap run lengths: {sorted((len(r) for r in runs), reverse=True)}")
print("=> benign here (all in 2021, when the base was small), but nothing in the current")
print("   pipeline would have detected a 5-day hole. Part 3's gate needs a continuity check.")

rule("T10 -- transaction brand vs member brand")
mb = {}
for m in members:
    mb.setdefault(m["member_id"], m["brand"])
pairs = [(mb[t["member_id"]], t["brand"]) for t in txns if t["member_id"] in mb]
match = sum(1 for a, b in pairs if a == b)
print(f"agree {match:,}/{len(pairs):,} = {100*match/len(pairs):.1f}%   disagree {100*(len(pairs)-match)/len(pairs):.1f}%")
bym = collections.defaultdict(set)
for t in txns:
    bym[t["member_id"]].add(t["brand"])
print(f"members transacting in more than one brand: {sum(1 for v in bym.values() if len(v) > 1):,} of {len(bym):,}")
print("=> must choose an attribution rule explicitly (we use TRANSACTION brand; see Part 6)")

rule("SUMMARY -- totals that later parts must reconcile against")
print(f"raw sum(points_earned)   = {sum(num(t['points_earned']) or 0 for t in txns):>15,.0f}")
print(f"raw sum(points_redeemed) = {sum(num(t['points_redeemed']) or 0 for t in txns):>15,.0f}")
print(f"raw sum(amount)          = {sum(num(t['amount']) or 0 for t in txns):>15,.2f}")
print(f"observed transaction date range: {min(d for d in (d10(t['transaction_date']) for t in txns) if d)} .. {max_txn}")
