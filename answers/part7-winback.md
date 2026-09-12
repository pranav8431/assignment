# Part 7 — Win-back campaign list

The list is `output/winback_list.csv` — 20 members, each with the score that put them there.

## Defining the two terms

**Worth winning back** means lifetime spend in the top 25%, above $349.19, and at least 3 purchases.
The thresholds come from the actual distribution rather than a guess: a quarter of members spent under
$88.58, half under $223.07, three quarters under $349.19. The 3-purchase minimum stops one big
shopping trip from making someone look loyal. A single purchase isn't a relationship.

**Slipping away** means their last purchase was between 120 and 365 days ago.

The lower bound is the judgement call I care most about here. The obvious choice is 90 days, but the
typical gap between purchases in this data is 104 days — so 90 days of silence is *shorter than
normal* and would flag roughly half the customer base. 120 days is the first point where going quiet
actually carries information.

## Who I left out

| Left out | How many | Why |
|---|---|---|
| Quiet under 120 days | 6,940 | Not slipping. Most would come back anyway, and discounting them is giving away margin |
| Quiet over 365 days | 1,333 | Gone, not slipping. A voucher doesn't reach someone silent for two years. This is the "could a campaign realistically work" test |
| The `M9######` members | 2,988 | Not in the member file at all, so no email, no way to contact them |
| Anyone whose spend came from a junk amount | 1 | Their value would be an artifact of a broken row |
| Members marked `churned` | **0 — kept in deliberately** | The obvious filter, and it would be a mistake. That column doesn't track behaviour, as Part 1 shows, so using it would drop winnable customers and let dead ones through |

The funnel: 49,996 members, down to 12,497 on the spend threshold, 12,465 after requiring 3
purchases, 4,192 after the time window, leaving 4,191 eligible.

## Ranking them

By spend per year — total spend over how long they've been active — with ties broken on how overdue
they are against their own usual gap.

Spend rate rather than lifetime total, deliberately. Someone who spent $1,800 in 14 months is a
better recovery target than someone who spent $1,800 across five years, even though a lifetime-value
ranking treats them identically.

The chosen 20 against everyone else: average lifetime spend $1,895 versus $244, so 7.8 times higher,
and on average 243 days since their last purchase against 184. Between them they're sitting on 76,621
unspent points.

## The judgement calls, stated plainly

The 120-to-365-day window is a business decision, not something the data proves. I got 120 from the
typical purchase gap, but the upper limit is my own judgement about who's still reachable. If the CRM
team has real numbers on how dormancy affects win-back rates, those should replace my guess.

Ranking by spend per year favours people with short, intense histories. That's intentional — recent
heavy spenders are easier to win back — but it works against long-standing steady customers, and
somebody should actively agree with that trade-off rather than inherit it from me without noticing.

The unspent points are a reason to make contact, not a reason to pick someone. Each of these members
holds between 2,800 and 5,000 points, which is a cheaper hook than a discount. But whether to remind
customers about a balance the business would quietly rather they forgot is a commercial decision, not
an analytical one.

Twenty people is too few to learn anything from. At any realistic response rate the result will be
indistinguishable from chance. I'd run it as asked, but I'd also hold back a matched group of 20 who
get nothing, so the next campaign has actual evidence behind it. Without that you spend the budget
and learn nothing.

And every one of these members is affected by the counting problem from Part 2. They qualified on
observed purchase volume, and in this dataset that volume is partly an artifact of how the data was
generated. On real data I'd trust this list considerably more than I do.

## Confidence

Reasonable about the method, low about these specific 20 names. I'd defend the criteria in a meeting.
The names themselves depend on thresholds a stakeholder should really set with me rather than inherit.

---

Previous: [Part 6 — Brand generosity](part6-brand-generosity.md) · Next: [Part 8 — Points liability](part8-points-liability.md)
