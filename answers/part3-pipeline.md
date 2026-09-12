# Part 3 — Pipeline Design

The job: run this every day, for 20 brands, at roughly 50 times the current volume — call it 10
million transactions a day — feeding a store that a model reads every morning.

```
  20 brand sources
        │  (one file per brand per day, with a description of what it should contain)
        ▼
   ┌─────────┐   ┌─────────┐   ┌───────────┐   ┌──────────┐   ┌──────────────┐
   │ LANDING │──▶│   RAW   │──▶│  CLEANED  │──▶│ FEATURES │──▶│ FEATURE STORE│
   │ as sent │   │ typed,  │   │ tidied,   │   │ per      │   │ what the     │
   │ personal│   │ no      │   │ problems  │   │ member   │   │ model reads  │
   │ scrambled│  │ dupes   │   │ flagged   │   │          │   │              │
   └─────────┘   └─────────┘   └─────┬─────┘   └──────────┘   └──────┬───────┘
                                     │                               │
                            ┌────────▼────────┐                      ▼
                            │  QUALITY GATE   │  fails ⇒ keep     model scores
                            │ "safe to serve?"│  yesterday's      at 06:00
                            └─────────────────┘  good data
```

## Getting data in without processing it twice

Each brand drops one file per day into storage, filed by brand and date, and nothing edits it
afterwards. Every file comes with a short description of what it should contain — row count,
checksum, format version. A missing description stops the load rather than raising a warning that
someone ignores.

Idempotency just means running the same job twice leaves you in the same state, rather than with
everything doubled. Two things get you there.

The first is the key. It's the brand *plus* the transaction ID, not the transaction ID alone. Across
20 brands you can't assume IDs are globally unique, and this file already proves the point: those
orphan `M9######` records come from a different ID scheme entirely, sitting in the same export. The
second is that loading replaces a row when that key already exists, instead of adding another one. So
a re-sent or retried batch ends up exactly where the first attempt did.

We already know this matters. Today's one-off export carries 1,995 duplicate transactions, 59 of
which disagree with each other. At 50x volume that's roughly 100,000 duplicates a day, quietly
inflating both the points the company owes and every "how often do they shop" number in the feature
table.

## Noticing when the incoming data changes shape

Schema drift is the structure of an incoming file changing without anyone telling you. The defence is
writing down what each brand's file should look like — columns, types, date format — and versioning
it.

A column disappearing or changing type stops the load. Don't try to convert it and carry on.

A new column appearing gets that day set aside with an alert raised, and yesterday's data keeps
serving. New columns are usually harmless, but "usually" isn't good enough for something feeding a
model that makes decisions about customers.

A format changing inside a column is the one that already happened here and nobody noticed: three
date formats in a single column, two of them from a different source system. Writing the expected
format down and rejecting anything else turns that into a failed load rather than 3,000 rows quietly
disappearing.

## What gets checked, and what "safe to serve" means

Two levels, and the difference is whether the data reaches the model at all.

Blocking — all of these pass before anything is published:

- transaction IDs unique within each brand
- every transaction belongs to a member who exists *(fails today)*
- row count within 20% of the last seven days' typical count for that brand
- blank amounts and blank points below a threshold
- every amount within a believable range *(fails today)*
- no negative amount carrying positive points *(fails today)*
- tier, country and channel containing only approved values *(fails today)*
- no missing days — no date inside the loaded range with zero transactions for a brand. This data has
  19 such days, all in 2021, up to five consecutive. Harmless here, but nothing in the current process
  would have spotted a five-day hole, and a row-count check on its own doesn't catch it
- points balances never going negative at any point in time. Replay each member's points in date
  order and check they never spend more than they hold. Checking only the final balance misses anyone
  who went negative and recovered; this data has 5 such cases that only the stricter check finds

Warning level, where you alert but keep going: a brand's earning rate shifting, the tier mix changing,
or the features starting to look different from what the model was trained on.

The commitment is features ready and passing by 06:00 local, on 99% of days, with the gate's result
published as a table anyone can query. If the gate fails, the store keeps serving the last good day
and the model runs on slightly old features, with the age exposed as a column so nobody is misled by
it. Stale scores can be corrected later. Confidently wrong ones get acted on.

Alerts name the brand and the specific check that failed. Never just "the pipeline broke" — that
tells the person on call nothing and wastes the first twenty minutes.

## Personal data

All of this happens the moment data arrives, so no later stage ever holds anything readable.

| Field | What happens | Why |
|---|---|---|
| `email` | Replaced with a scrambled code that can't be reversed, produced by a keyed one-way function | The same email always produces the same code, so we can still tell two records are the same person without anyone being able to read the address |
| `first_name`, `last_name` | Deleted outright from the analysis data | They add nothing to any model here. The cheapest way to protect a piece of personal data is not to keep it |
| `birth_date` | Reduced to a birth year, then an age band | A full date of birth identifies someone on its own. An age band gives the business everything it actually uses |

Linking people up belongs at this stage too. That scrambled email code isn't only a privacy measure,
it's what fixes the two-accounts problem from Part 1. Right now 20 people hold 40 accounts because
each brand creates its own record. Matching on the code as data arrives is what stops the model
calling someone a lost customer while they're happily shopping under their other account. With 20
brands this gets worse, so it needs solving once in the pipeline rather than repeatedly in every
analysis someone writes.

Real email addresses live in one locked-down store with separate access, because campaigns genuinely
need to reach real inboxes — the Part 7 list is useless otherwise. Access is logged. If someone asks
to be deleted we delete that one record, which permanently breaks the link everywhere downstream.
That honours the request without rewriting years of history.

## Which tool runs it

Airflow, managed rather than self-hosted so we're not maintaining the scheduler itself.

This workload is 20 brands running in parallel, each waiting on its own file, with a quality gate that
has to sit between cleaning and publishing, re-runs when a brand sends a corrected day, and deadlines
that need to wake someone up when they're missed. That's what Airflow is for, and fanning the same
steps across 20 brands is a standard pattern in it rather than something you fight.

What I turned down:

dbt on its own. It's excellent at the transformation steps and should absolutely be used inside this.
But it has no scheduler, can't wait for a file to arrive, and has no concept of re-running one
specific past day. Making it the orchestrator means rebuilding all of that by hand in CI.

Databricks Workflows. Genuinely good, and if the company already ran everything on Databricks I'd
take it for the reduced number of moving parts. I turned it down here because it ties scheduling to
one vendor's compute, and this pipeline has to reach 20 outside systems, a feature store and a
serving layer that won't all live in the same place.

---

Previous: [Part 2 — Feature engineering](part2-features.md) · Next: [Part 4 — Production incident](part4-incident.md)
