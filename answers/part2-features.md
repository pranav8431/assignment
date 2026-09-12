# Part 2 — Feature Engineering for a Churn Model

The code runs in three steps: `scripts/03_clean.sql` cleans, `scripts/04_features.sql` builds the
features, `scripts/05_label.py` attaches the churn label. Output is `output/member_features.csv`,
31,712 members across 38 columns.

## Deciding who counts as churned

I couldn't use the `status` column. Part 1 covers why: members marked active, inactive and churned
all last bought within a day of each other, so the field tells you nothing about behaviour. It's
tempting because it's right there and it produces clean code, but it would have meant training a
model on noise.

So it comes from purchases instead. Pick a cut-off date, then:

> A member has churned if they made no purchases at all in the 90 days after the cut-off.

## Two windows, and why the cut-off matters

```
|<--- everything before the cut-off: build features here --->|<-- next 90 days: did they buy? -->|
2021-01-05                                           2026-04-01                          2026-06-30
```

The cut-off is 2026-04-01, which is the last day in the data minus 90. Any later and there wouldn't
be a full 90 days left to check the outcome against.

For scoring live members the same code runs with the cut-off set to 2026-06-30 and no answer
attached, which covers 49,996 members. Only the date changes between the two. That matters more than
it sounds: if training used different logic from live scoring, the model would behave differently in
production than it did in testing, and you'd have no way of knowing until it cost you something.

Who's included: members who bought something in the year before the cut-off, so 31,712 people. Of
those, 58.8% churned. If I widen it to everyone who ever bought, that goes to 61.5%; narrowing to the
last 180 days gives 55.3%.

## The rule everything else hangs on

Every calculation uses only transactions from on or before the cut-off. This sounds obvious and it's
very easy to get wrong, so here's the proof it matters:

| How "days since last purchase" was worked out | How strongly it predicts churn |
|---|---|
| Using all the data, including after the cut-off | 0.76, but it's cheating |
| Using only data up to the cut-off | 0.16, and this one is real |

The first version looks like an outstanding predictor because it has quietly seen the answer. Build a
model that way and it scores beautifully in testing, then falls apart the day it meets real data. The
validation script confirms no feature in the training set touches anything after the cut-off.

## The code

This is the heart of the feature build, trimmed to the parts where an actual decision gets made. Full
version in `scripts/04_features.sql`.

```sql
-- Every total below is limited to transactions on or before `as_of_date`.
-- The SAME file builds the training data (cut-off 2026-04-01) and the live
-- scoring data (cut-off 2026-06-30). Only the date changes.
WITH p AS (
    SELECT as_of_date,
           date(as_of_date,'-90 day')  AS w90,     -- last 90 days
           date(as_of_date,'-180 day') AS w180,    -- the 90 days before that
           date(as_of_date,'-365 day') AS w365
    FROM params
),
tx AS (                                     -- ONLY transactions up to the cut-off
    SELECT ct.* FROM clean_transactions ct, p
    WHERE ct.txn_date <= p.as_of_date       -- <-- this one line is the safeguard
      AND ct.is_orphan_member = 0           -- drop the 2,988 members who don't exist
),
agg AS (
  SELECT tx.member_id,
    CAST(julianday((SELECT as_of_date FROM p))
         - julianday(MAX(tx.txn_date)) AS INT)                        AS recency_days,
    COUNT(*)                                                          AS txn_count_lifetime,
    SUM(CASE WHEN tx.txn_date >  (SELECT w90  FROM p) THEN 1 ELSE 0 END) AS txn_count_90d,
    SUM(CASE WHEN tx.txn_date <= (SELECT w90  FROM p)
              AND tx.txn_date >  (SELECT w180 FROM p) THEN 1 ELSE 0 END) AS txn_count_prev_90d,
    -- the 15 junk amounts are blanked, so spending totals skip them while the
    -- transaction still counts towards how often someone shops. That's the whole
    -- reason for blanking rather than deleting the row.
    ROUND(SUM(tx.amount),2)                                           AS monetary_lifetime,
    ROUND(SUM(tx.points_earned) - SUM(tx.points_redeemed),0)          AS points_balance,
    MAX(CASE WHEN tx.points_redeemed > 0 THEN 1 ELSE 0 END)           AS ever_redeemed_flag,
    COUNT(DISTINCT tx.brand)                                          AS distinct_brands,
    -- these mark anyone whose data I repaired, so a modeller can test
    -- what happens with those members excluded
    MAX(tx.is_points_imputed)  AS has_imputed_points,
    MAX(tx.is_sentinel_amount) AS has_sentinel_amount,
    MAX(tx.is_refund)          AS has_refund
  FROM tx GROUP BY tx.member_id
)
SELECT (SELECT as_of_date FROM p) AS as_of_date, m.member_id, m.tier,
    a.recency_days, a.txn_count_lifetime, a.txn_count_90d, a.txn_count_prev_90d,
    -- speeding up or slowing down. I prefer this to raw counts, for reasons
    -- that become clear further down this page.
    ROUND(1.0*a.txn_count_90d / NULLIF(a.txn_count_prev_90d,0),3)     AS freq_trend_ratio,
    a.monetary_lifetime, a.points_balance, a.ever_redeemed_flag,
    -- join_date is missing for 998 members and impossible for 30 more. Left empty
    -- rather than guessed: a made-up join date invents a relationship with the
    -- customer that never existed.
    CASE WHEN m.join_date IS NOT NULL
         THEN CAST(julianday(a.last_txn_date)-julianday(m.join_date) AS INT) END AS tenure_days,
    m.tier_ambiguous_flag, a.has_imputed_points, a.has_sentinel_amount, a.has_refund
FROM agg a JOIN clean_members m ON m.member_id = a.member_id;
```

And the label, which is the bit `status` couldn't give us:

```sql
CREATE TABLE churn_training AS
WITH outcome AS (                            -- who bought in the 90 days AFTER the cut-off
    SELECT DISTINCT member_id FROM clean_transactions
    WHERE txn_date > '2026-04-01' AND txn_date <= '2026-06-30'
      AND is_orphan_member = 0
)
SELECT f.*,
       CASE WHEN o.member_id IS NULL THEN 1 ELSE 0 END AS churned_90d  -- not in that list = churned
FROM features_train f
LEFT JOIN outcome o ON o.member_id = f.member_id
WHERE f.recency_days <= 365;                 -- only members active in the last year
```

## What's in the table

34 features in 12 groups.

| Feature | What it measures | Note |
|---|---|---|
| `recency_days` | Days since their last purchase | Strongest honest signal in the set |
| `tenure_days` plus two flags | How long they've been a member | Left blank when unknown, never guessed |
| `txn_count_lifetime` / `_90d` / `_prev_90d` / `_365d` | How often they buy | See the warning below |
| `freq_trend_ratio` | Last 90 days against the 90 before | Speeding up or slowing down |
| `monetary_lifetime`, `avg_basket`, `spend_90d`, `spend_prev_90d` | How much they spend | Junk amounts drop out automatically |
| `spend_trend_ratio` | Recent spend against earlier | |
| `avg_gap_days`, `recency_vs_own_cadence` | Their personal rhythm | Is this silence unusual *for them* |
| `points_balance`, `redemption_rate`, `ever_redeemed_flag` | Whether they use points | |
| `tier`, `tier_ambiguous_flag` | Bronze through Platinum | Spelling cleaned up |
| `distinct_brands`, `is_cross_brand` | Do they shop more than one brand | |
| `distinct_channels`, `pct_app` | App, online or in store | |
| Five data-quality flags | Which members had data repaired | So a modeller can test without them |

## Tier behaviour, which the brief asks for and I couldn't build

The brief lists "recency, frequency, monetary value, tier behavior, engagement trend, redemption
behavior". I have the tier, but a tier is a label, not a behaviour. Two reasons, both worth saying
rather than quietly skipping.

There's no tier history in the file. The member data is a single snapshot with no record of when
anyone moved between tiers. The one exception is faintly ironic: those 150 duplicated member rows
*are* tier changes — `M00073` appears as both Bronze and Silver — and collapsing them to one row per
member, which I had to do, destroys the only evidence of movement in the whole file. With proper
history I'd build "changed tier in the last 180 days", "days since the change" and whether it went up
or down. I'd expect a downgrade to be one of the strongest churn warnings available.

The second reason is that tier doesn't actually get you anything here. Bronze, Silver, Gold and
Platinum all earn identical points per dollar in every brand, which Part 6 goes into. So tier can't
*cause* churn in this programme, it can only correlate with it, and I wouldn't let anyone read a tier
effect as "upgrading members keeps them".

## A flaw in my own labels

Those 20 people with two accounts: 34 of their accounts sit in the training set and 19 are labelled
churned. If someone abandons their PulseEats account but keeps shopping on their PulseHome one, my
label calls them lost when the business hasn't lost them at all.

It's a small slice of 31,712 so I haven't adjusted for it. But it's a real flaw rather than a
theoretical one, and it's the kind that gets worse with scale — across 20 brands, more people hold
more accounts.

## Five Part 1 problems, how I handled them, and what I turned down

**Duplicate transactions.** Keep one row per ID using a fixed rule. I rejected the simpler "remove
identical rows" because it only catches the 1,936 exact copies and silently keeps both versions of
the 59 that disagree. I also rejected "keep the most recent", since there's no timestamp saying which
was written last. My rule picks the same row every time, so re-running gives the same answer.

**Junk amounts.** Blank the amount, keep the transaction. The purchase happened; the price is what's
broken. Deleting the whole row would make those members look like they shop less than they do.
Capping the value at something plausible means inventing a price I've no basis for. With the amount
blank, spending totals skip it while the transaction still counts towards frequency.

**Refunds that gave out points.** Keep the refund, remove the points. I rejected flipping the
negative to positive, which disguises a refund as a purchase and repeats the original bug. I rejected
deleting the row, because someone returning goods is exactly the behaviour a churn model should be
able to see. This strips 265,569 wrongly awarded points.

**Missing points.** Work them out from the amount and mark them as estimated. Filling in missing
values is usually a bad idea; it's defensible here for one specific reason, which is that the earning
rate is completely fixed. PulseEats gives 1.75 points per dollar, PulseHome 2.00, PulseMart 2.30,
identical to three decimal places across every tier and basket size. The rate is measured from the
data, not typed in by me. I rejected deleting the rows, which loses 1,514 real purchases, and
rejected filling in zero, which understates what the company owes. Adds 200,724 points, all flagged.

**Duplicate members.** Keep the higher tier and more active status, and flag them. I rejected
deleting both rows, which loses 150 real customers, and rejected taking whichever came first, because
then the answer changes between runs. Being honest about it: with no timestamp there's no way to know
which row is current. The flag exists so anyone can test the model with those 150 removed.

Nothing disappears quietly. Every point the cleaning removes is accounted for, and the validation
script proves the totals close:

```
started with 25,586,688  −  removed 915,482  +  estimated 200,724  =  24,871,930  ✓
```

## Does it predict anything

I sorted members by days since last purchase and cut them into ten equal groups:

| group (1 = most recent) | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| % churned | 44.0 | 46.5 | 50.4 | 56.6 | 57.4 | 62.2 | 65.3 | 68.1 | 69.3 | 68.5 |

24.5 percentage points between best and worst, climbing steadily at 8 of the 9 steps. I then held
back 20% of members, split by member so nobody lands in both halves, and the pattern held at 28.8
points. So it's real signal, not the model memorising noise.

## Six features I'd block, and why

I checked something simple: does each feature point the way common sense says it should? Six out of
ten don't.

| feature | relationship with churn | expected | |
|---|---|---|---|
| `recency_days` | +0.162 | positive | ok |
| `txn_count_90d` | −0.206 | negative | ok |
| `avg_gap_days` | +0.209 | positive | ok |
| `freq_trend_ratio` | −0.148 | negative | ok |
| `txn_count_lifetime` | +0.202 | negative | **backwards** |
| `monetary_lifetime` | +0.181 | negative | **backwards** |
| `points_balance` | +0.175 | negative | **backwards** |
| `ever_redeemed_flag` | +0.044 | negative | **backwards** |
| `is_cross_brand` | +0.053 | negative | **backwards** |
| `recency_vs_own_cadence` | −0.055 | positive | **backwards** |

One cause explains all six. I compared how much each member bought before the cut-off against how
much they bought after. In the real world those move together — people who shop a lot carry on
shopping a lot. Here the relationship is negative, at −0.217. Which means each member appears to have
a fixed lifetime allowance of purchases (most have 4, the maximum is 16), so a purchase seen before
the cut-off is one used up. Every feature that counts things up inherits the problem.

| purchases before the cut-off | members | % churned |
|---|---|---|
| 1–2 | 3,171 | 33.9 |
| 3 | 3,171 | 56.4 |
| 6 or more | 3,173 | **70.3** |

Train a model on this and it learns that the more someone buys, the more likely they are to leave. It
would look excellent in testing, then aim the entire retention budget at your best customers while
ignoring the people actually walking out.

So what I'd ship is the recency and trend features only: `recency_days`, `avg_gap_days`,
`txn_count_90d`, `freq_trend_ratio`, `spend_trend_ratio`. I'd hold the counting features back until
whoever produces this data can explain the pattern. Shipping a model that's confidently backwards is
worse than shipping nothing.

Three others I'm uneasy about for unrelated reasons. `redemption_rate` is built on a column that
never exceeds exactly 200 and is half round numbers, so I'd use the simpler "have they ever redeemed"
instead. `tenure_days` is 2% missing, 30 impossible, and 205 members bought before they joined. And
`freq_trend_ratio` is undefined for anyone with no purchases in the earlier window, so how you handle
that blank will drive most of the feature's behaviour.

## 90 days might be the wrong definition

The typical gap between one purchase and the next here is 104 days, and 54% of perfectly ordinary
gaps run longer than 90. So going quiet for 90 days is average behaviour in this data, not a warning
sign, which is why 59% of members end up counted as churned.

| window | members | % churned |
|---|---|---|
| **90 days (as the brief specifies)** | 31,712 | **58.8** |
| 180 days | 29,458 | 42.4 |
| 270 days | 27,284 | 31.2 |
| 365 days | 24,902 | 23.1 |

I built the 90-day version as asked. My recommendation is that the business revisits it, or defines
churn against each member's own rhythm, which is what `recency_vs_own_cadence` is sitting there for.

---

Previous: [Part 1 — Data quality](part1-data-quality.md) · Next: [Part 3 — Pipeline design](part3-pipeline.md)
