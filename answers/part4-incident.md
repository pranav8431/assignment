# Part 4 — Production Incident

The engagement score dropped to zero for about 40% of PulseEats members, across the same six days,
and only for PulseEats. Someone's asking on Slack whether to escalate to the brand team.

## What I'd say in the first five minutes

Before knowing anything:

> Looking into it now. One brand, one unbroken run of days, and a clean zero rather than a low number
> — that pattern usually means a data problem rather than a real drop, so I don't want to call it
> yet. I'll update within the hour.

That reply is worth sending immediately. Escalating a data bug to a brand team costs them a week of
chasing something that never happened, and the apology afterwards doesn't buy the week back.

## What I'd check, in order

It all hangs on one question first: is the data missing, or is the number genuinely zero? Those have
completely different fixes and everything downstream depends on which one it is.

1. **Is the data even there.** Count transactions and active members per day for PulseEats over the
   last fortnight, next to the other brands. If PulseEats transactions dropped too, this is about data
   arriving. If transactions look normal and only the score is zero, it's the calculation.
2. **Is it the same 40% of people, or a random 40%.** Group the affected members by join date, tier,
   country and channel. A clean pattern — everyone whose activity comes through one particular feed,
   say — points at part of the data being missing. A random-looking 40% points somewhere else entirely.
3. **Zero, blank, or missing row.** Three different bugs. A real zero means the calculation ran and
   produced zero, which points at its inputs rather than at ingestion.
4. **Did we change something.** Deployment history and code changes across those six days. A six-day
   window ending Sunday, spotted Monday, is the classic shape of a Friday release.
5. **Did the source change.** File descriptions from PulseEats for those days — row counts, sizes,
   format version — against the other 19 brands on the same days.
6. **Rebuild it by hand.** Recalculate the score straight from raw data for a handful of affected
   members. A sensible number means the bug is in our processing. Also empty means the data never
   arrived.
7. **Only now, real-world explanations.** Shop closures, an app release, a promotion ending.

## What I'd actually run

- Transactions and distinct members per day per brand, last 14 days. One query answers step 1.
- Counts of scores that are exactly zero, blank, or missing entirely, for PulseEats across those dates.
- The affected members grouped by tier, country, channel and join month, against the unaffected 60%.
  I'm looking for one characteristic that splits them cleanly.
- Proportion of blanks in each column feeding the score, by day and brand. In my experience this is
  usually where the answer turns out to be.
- Airflow's run history for those six days: retries, jobs that hung, or jobs that "succeeded"
  suspiciously fast having processed nothing.
- What changed in the transformation code, and the row counts stored against each day's output.
- Source file row counts and checksums per brand per day. If PulseEats sent 40% fewer rows for six
  days, this whole investigation takes about thirty seconds.

## Three explanations, ranked

**Part of the PulseEats feed failed.** Most likely. Three details point here together: it's one
brand, so something brand-specific; it's an unbroken six-day run, so something that started and
stopped rather than drifted in; and the share affected is large and roughly round. If PulseEats sends
engagement events through a separate feed — app activity, for instance — and that feed stopped, then
precisely the members whose activity arrives that way go to zero while everyone else is unaffected.
Step 2 confirms or kills this quickly.

**A bug in our own processing hitting one brand.** A brand-specific setting, a join that quietly
started dropping unmatched rows, or — very plausibly given what's already in this data — a date that
couldn't be read, making six days of PulseEats transactions invisible to the calculation. We know
that failure mode is live: 3,000 rows in this file use date formats that a standard conversion
silently discards. Second rather than first only because it would more often hit every brand at once.

**A real drop in engagement.** Least likely, on the shape of the evidence rather than optimism. Real
customer behaviour doesn't produce exactly zero for 40% of a customer base, in one brand only,
starting and stopping cleanly on a six-day boundary. Genuine declines are gradual, partial, and show
up across brands that share customers.

What would change my mind: scores that are low but not exactly zero, a gradual slide rather than a
cliff, a matching fall in raw PulseEats transaction counts, or a real event that explains it. Any of
those and I escalate straight away.

And if steps 1 to 6 clear the pipeline — data present, nothing deployed, no feed gap, rebuilding from
raw still gives zero — then it's real, and the brand team should have been told an hour ago. I'd
rather be an hour late to a real problem than send twenty people chasing a bug in our own code.

---

Previous: [Part 3 — Pipeline design](part3-pipeline.md) · Next: [Part 5 — Slack message](part5-slack-message.md)
