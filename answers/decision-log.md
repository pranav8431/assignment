# Decision Log

The brief asks for a few bullets per part: what I decided, what I turned down, and anywhere an AI
tool's first answer was wrong and how I caught it. Organised by part.

I used AI throughout, mostly for first drafts of SQL and for sanity-checking my reasoning. Four of
the entries below are places it confidently handed me something wrong. Those are the interesting ones.

## Part 1 — Data quality

Kept the table to 10 rows rather than 14. The brief asks for a short report and says outright it isn't
after an exhaustive checklist, so five lower-impact findings went into a paragraph underneath. A long
table looks thorough and buries the six issues that actually matter.

Every prevention measure is something that runs. "Improve data governance" isn't checkable. "Make
transaction ID unique" either exists or it doesn't.

I split the duplicate-email finding apart late on. My first pass reported "170 duplicate emails" as a
single problem, lumped in with the duplicate members. That conflated two different things: 150 are the
same account listed twice, but 20 are two different accounts belonging to one person. I caught it by
asking whether the repeated emails and the repeated member IDs were the *same rows*. They weren't, and
those 20 have consequences in Parts 2, 7 and 8.

## Part 2 — Feature engineering

**Worked churn out from purchases rather than the `status` column.** Using `status` is the obvious
move and produces tidy code, and it was the first thing suggested to me. I nearly took it. What
caught it was asking a question no code review would have asked: do these labels match what people
actually did? The most recent purchase date is within a day across all three statuses. The column is
inert.

**Checked the direction of every feature, which changed what I'd recommend shipping.** Purchase
counts are the textbook answer and showed the strongest separation of anything in the set — a
36-point spread, better than recency. But it runs backwards. I caught it by checking the sign before
the strength, which isn't the usual order. Six features turned out to be affected. A strong signal
pointing the wrong way is worse than no signal at all, because it survives validation.

Used a fixed rule to pick one row per transaction rather than "remove identical rows". The simpler
version was the first suggestion; it handles the 1,936 exact copies and silently keeps both versions
of the 59 that disagree. Caught by checking whether the duplicates actually *were* identical before
deciding how to handle them.

**Rejected flipping negative amounts to positive.** It looks sensible and it's wrong — it disguises a
refund as a purchase and repeats the original bug. Caught by asking what the negatives actually were:
all 2,012 had points attached at exactly the standard earning rate, which identified them as refunds.

Left missing join dates blank rather than filling in a typical value. Guessing invents a relationship
with a customer that never existed.

## Part 3 — Pipeline design

Chose Airflow, named one tool, said why not the others. dbt has no scheduler and can't wait for files,
so it belongs inside the orchestrator rather than being one. Databricks Workflows is good but ties
scheduling to a single vendor's compute.

Made the key brand plus transaction ID, not transaction ID alone. Across 20 brands you can't assume
IDs are globally unique, and this file already contains two colliding ID schemes.

Chose to serve slightly old data when checks fail rather than stopping. A stale score gets corrected
later. A confidently wrong one gets acted on.

Added the missing-days and running-balance checks late, because writing Part 8 made me realise I'd
only ever checked final balances and had never looked for gaps in the calendar at all.

## Part 4 — Incident

Built the answer around one question first — is the data missing, or is the number really zero.
Everything downstream depends on which, and they have completely different fixes.

Ranked "it's a real drop" last, and said what would change my mind. A ranking with no falsification
condition is just an opinion with numbers next to it.

Included what I'd say in Slack in the first five minutes. The scenario is someone asking whether to
escalate; an answer that investigates thoroughly and never replies to them misses half the question.

## Part 5 — Slack message

Explained the delay using the Part 3 quality gate, because the brief specifies the delay follows those
fixes. My first draft explained it using the Part 1 findings and never mentioned the check that
actually costs the two days.

Cut the line admitting earlier scores were wrong. It was true and I removed it deliberately: the brief
says the manager forwards it to a client unchanged, and that line raises a question they can't answer
in a document they can't edit. I flagged the trade-off in the write-up rather than hiding the choice.

## Part 6 — Brand generosity

**This is where an AI answer was most consequentially wrong.** Adding up all points and dividing by
all spend is the natural approach, and it returns PulseHome as the winner with PulseMart worst at
0.906. I caught it because 0.906 was implausible — every individual PulseMart transaction pays about
2.30, so the total can't be 0.906 unless the bottom of the fraction is contaminated. Sorting by
amount found the 15 junk rows immediately, 12 of them PulseMart's. The rule I took from it: when a
total disagrees with the rows underneath it, the total is wrong.

Excluded my own estimated rows from that specific calculation to avoid circular reasoning, since the
estimate uses the brand's earning rate.

Tried to work out what a point is worth rather than just declaring it impossible, then threw most of
the result away because the pattern turned out to be arithmetic rather than behavioural. Reporting a
weak finding honestly beats both overstating it and pretending I never looked.

## Part 7 — Win-back list

Used 120 days rather than 90 as the threshold for going quiet. The typical gap between purchases is
104 days, so 90 days of silence is shorter than normal and would flag half the customer base.

Didn't filter out members marked `churned` — the obvious filter, and it would drop winnable customers
while letting dead ones through, because that column doesn't track behaviour.

Ranked on spend per year rather than lifetime total, so someone who spent $1,800 in 14 months
outranks someone who spent the same over five years. Flagged that this works against long-standing
steady customers.

Recommended holding back a control group of 20. At this size the result is indistinguishable from
chance, and without a control the campaign spends money and teaches nobody anything.

## Part 8 — Points liability

Led with the structural problem: every transaction is a purchase, so there's no redemption ledger,
and this is a figure I calculated rather than one I could verify.

Gave a range rather than one number. The value of a point swings the answer by two and a half times,
so a single figure would imply precision I don't have.

**Caught myself using my own cleaning as evidence.** I claimed 21 negative balances proved the source
records were broken. Only 5 come from the source; 16 were created by my own refund fix. I caught it by
recalculating with that fix switched off — a check I only ran because the number felt too high for a
dataset this otherwise-tidy. Corrected in the write-up and now tested automatically. Of everything
here, this is the mistake I'd most want a reviewer to see me catch.

## Across the whole thing

Used Python's standard library plus SQLite and nothing else. Neither pandas nor duckdb was installed,
and I decided against installing them for the main pipeline: the SQL stays readable and would move to
Snowflake or BigQuery with small edits. The notebooks are the exception and do use pandas.

Saved the cleaned data as real tables instead of recalculating it every time. As views, one step was
being redone on every query and Section 2 took over two minutes. Saving it took that to 1.8 seconds.

Measured the brands' earning rates from the data instead of typing in 1.75 / 2.00 / 2.30. I measured
them, so the code should too, and the validation script confirms them on every run.

Didn't train a model. It wasn't asked for, and given that six features point the wrong way, a headline
accuracy score would have been actively misleading.

Every number in the write-up is checked automatically. If a figure and the data ever disagree, the
run fails.

## What I'd do with more time

**Part 2:** several cut-off dates rather than one, for roughly three times the training data and a
check on seasonal effects, grouped by member so the same person never lands in both halves.

**Part 6:** nothing more is possible without the rewards catalogue. That's the blocker, not hours.

**Part 7:** target people a campaign would actually change, rather than people with the highest past
value. Needs results from previous campaigns, which aren't in this data.

**Part 8:** an age breakdown of every member's points balance to support a real expiry estimate, and a
root cause for those five negative balances.

**Everywhere:** turn each prevention measure in Part 1 into an automated test, so the audit becomes
something that runs continuously rather than a document that goes stale.

---

Previous: [Part 8 — Points liability](part8-points-liability.md) · [Back to the README](../README.md)
