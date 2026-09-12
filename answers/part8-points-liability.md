# Part 8 — Outstanding points liability

About **$225,000**, on 22,493,011 unspent points at a cent each. Around **$180,000** if you assume
20% never get redeemed.

What I'd actually hand Finance is the range — $157,000 to $281,000 — plus the assumptions below,
rather than a single figure. The spread isn't uncertainty in the data. It's one assumption I can't
verify doing most of the work.

## The thing to know before the number

Every one of the 194,311 transactions is a purchase. There are no redemption records anywhere in this
data. Points being spent shows up only as a column sitting on purchase rows.

That's the caveat that matters most. There's no points ledger, no opening balance, no record of
anything expiring. What follows is a figure I calculated, not one I could check against anything
independent. Nobody should treat it as audited.

## Getting there

| | points |
|---|---|
| Earned minus redeemed, straight from the raw file | 25,586,688 − 2,403,160 = 23,183,528 |
| − duplicate transactions (1,995) | −261,232 |
| − points wrongly given on refunds (1,995 rows) | −265,569 |
| − members who don't exist in the member file (2,988 rows) | −388,681 |
| + points I estimated where they were missing (1,496 rows) | +200,724 |
| **Cleaned total outstanding** | **22,493,011** |

The uncleaned figure overstates what's owed by 690,517 points, or 3.1% — about $6,900 at a cent a
point. Small as a percentage. It's also the difference between a number that survives an audit and
one that doesn't.

## Every assumption, and why

**A point is worth one cent.** This is not in the data anywhere. It's a common value in loyalty
programmes and a reasonable starting point, and it affects the answer more than everything else
combined. Hence the range:

| value per point | all points used | 20% never used | 30% never used |
|---|---|---|---|
| half a cent | $112,465 | $89,972 | $78,726 |
| **one cent** | **$224,930** | **$179,944** | $157,451 |
| 1.25 cents | $281,163 | $224,930 | $196,814 |

**Points never expire.** No expiry date in the data, no copy of the programme's terms. That makes my
figure the maximum possible rather than what's likely to actually be claimed.

**The 20% never-redeemed allowance** can't be worked out from this data. It needs years of history on
points expiring. 20% is a typical industry figure and I've labelled it as an adjustment rather than
something I measured. If Finance needs a number they can defend today, use the full amount and drop
this line entirely.

**I excluded the members who don't exist.** 388,681 points sit on 2,988 `M9######` accounts absent
from the member file. You owe a liability to a person, and the company has no record of these people.
If they turn out to be real customers from another system, the total goes to $228,817, up 1.7%.

**I removed the points given on refunds.** Finance shouldn't record a debt that a software bug
created.

**I removed duplicate transactions.** Keeping them would have inflated the figure by about $2,600.

## Why I don't fully trust my own number

**Five members have a negative points balance in the source data.** Replaying every member's history
in date order also turns up five occasions where someone spent more points than they had, totalling
225 points. Small, but impossible if the records were complete — so some earning records are
genuinely missing.

A correction I want to be explicit about. An earlier version of this answer said *21* members had
negative balances and used that as proof the source records were broken. That was wrong. Only 5 come
from the source data. The other 16 were created by my own refund fix: stripping points from refunds
pushes anyone who'd already spent those points below zero.

I was using my own cleaning as evidence against someone else's system, in the section headed "why I
don't trust my own number", which is about as neatly ironic as it gets. I only caught it because 21
felt high for a dataset this otherwise-tidy, so I recalculated with the fix switched off. The 16 are
still interesting — those members spent points my correction says they never properly earned — but
the honest figure for "the source records are incomplete" is **5, not 21**. The validation script now
tests both numbers so the claim can't quietly drift back.

**The redemption column looks cut off.** It never exceeds exactly 200 and half its values are round
numbers. If real redemptions are being under-recorded, the amount actually owed is lower than my
figure, possibly by a lot.

**There's nothing to reconcile against.** See the top of this page. This is the caveat I'd put in bold
in a note to an auditor.

**0.9% of the total is estimated rather than observed** — 200,724 points across 1,496 rows.

**The value of a point is assumed, not measured**, and it moves the answer by two and a half times
across a plausible range.

## What I'd recommend

Record the middle figure, publish the range next to it, and mark it as an estimate pending three
things: the redemption records so it can be checked, the programme's terms for expiry rules and point
value, and an explanation for those five negative balances.

A number this size with this many open questions deserves a note attached, not a decimal point.

## Confidence

Reasonable about the points count, low about the dollar figure. I'd defend 22.5 million points
outstanding — it reconciles line by line against the raw totals. Turning that into dollars rests
entirely on an assumption I couldn't verify.

---

Workings in `output/section2_findings.txt`.

Previous: [Part 7 — Win-back list](part7-winback.md) · Next: [Decision log](decision-log.md)
