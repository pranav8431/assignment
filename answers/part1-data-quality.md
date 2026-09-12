# Part 1 — Data Quality & Governance Audit

Ordered by how much damage each one does, not by how easy it was to find. For the last column I've
tried to name a check that actually runs. "Improve data governance" isn't a control; a unique
constraint either exists or it doesn't.

| Issue | Evidence (how I found it) | Likely root cause | Fix | Prevention control |
|---|---|---|---|---|
| **1,995 transactions appear twice** | Grouped the file by transaction ID and looked for IDs showing up more than once. Then compared the full rows inside each group: 1,936 pairs are exact copies, but **59 pairs disagree with each other** | The sending system re-sends a batch when it isn't sure the first attempt landed, and our loader adds rows rather than replacing them. Those 59 disagreeing pairs mean a corrected version got sent too | Keep one row per transaction ID, picked by a fixed rule. Not a plain "remove exact duplicates", which leaves both rows of all 59 disagreeing pairs | Make transaction ID unique in the database and load with "replace if present". A load that breaks the rule should fail loudly, not quietly append |
| **15 transactions have junk amounts** — `999999.99` six times, `99999.00` six times, then `88888.50`, `75000.00`, `64000.00` | Sorted the amount column downwards. 99% of transactions sit under $285.69, so these are about 3,500 times a normal purchase. **12 of the 15 are PulseMart's** | The till writes a placeholder when it can't look up a price, instead of leaving the field empty | Blank the amount, keep the transaction. The purchase happened; only the price is wrong | Reject any amount outside a sensible range at load time, and alert if the top of the range shifts. **These 15 rows reverse the answer to Part 6** |
| **2,012 refunds handed out points anyway** | Filtered for negative amounts, which run from −$484.85 to −$7.67. Every one has points attached, and points divided by refund size comes to **2.001** — exactly the normal earning rate | Refunds go into the same table as purchases, as negatives, and the points rule ignored the minus sign | Keep the refund so it reduces the customer's spend properly, but strip the points it wrongly awarded | Give refunds their own transaction type with a points rule that can go negative. Add a test: a negative amount must never carry positive points |
| **Three date formats in one column** | Pattern-matched all 194,311 dates. 191,311 look like `2026-03-13 00:43:55`, 1,500 like `2026-03-13`, and 1,500 like `03/13/2026`. The two odd groups never overlap | Two systems export this with different regional settings and the files were merged without anyone agreeing a format | Read all three explicitly. The slash format is US month-first: the first number never exceeds 12, the second reaches 31 | Agree one format in writing per source and reject the rest. A standard date conversion would have **silently dropped 3,000 rows** |
| **The `status` column doesn't reflect whether anyone actually shops** | Compared the most recent purchase date per group. Members marked `active` last bought on 2026-04-05, `churned` on **2026-04-04**, `inactive` on 2026-04-05 | Set by a rule nobody maintains, or filled in once and never updated since | Don't use `status` to decide who churned. Work it out from purchases | Anything used to train a model needs a named owner and a written definition. A monthly test checking that status separates active from inactive customers would have caught this years ago |
| **150 members appear twice** | Grouped by member ID and compared the pairs. In all 150 cases only the tier and status differ; everything else matches | This table normally keeps a history of changes and has been squashed into one snapshot, without marking which row is current | One row per member, taking the higher tier and more active status, with the member flagged as uncertain | Make member ID unique, and ask the source for "valid from" and "valid to" dates so the history survives |
| **20 email addresses belong to two different member IDs** — one person, two accounts | There are 170 repeated emails. 150 are the same account listed twice (the row above). The other **20 map to two genuinely different member IDs, so 40 accounts**. `member38687@…` is both `M02784` (Gold, PulseHome, joined 2023) and `M38687` (Platinum, PulseEats, joined 2021) | Nothing joins customers up across brands. Each brand creates its own record for the same person | Link both accounts to one person ID via the email, and total their activity at person level | Match on email as data arrives and expose a person ID everyone uses. **34 of these accounts are in the churn training set and 19 are labelled churned — someone shopping on their other account looks like a lost customer** |
| **2,988 transactions belong to members who don't exist** | Checked every transaction's member ID against the member file. These all look like `M9######`, have exactly one transaction each, and their transaction IDs start `TX` rather than `T` | A second system, or a test environment, has leaked into the export. Two ID schemes with nothing keeping them apart | Flag them, leave them out of the model, count them separately for the finance question | An automatic check that every transaction points at a real member, failing the load past a threshold |
| **1,514 transactions have no points recorded** (0.78%) | Counted blanks. They're spread evenly across brands and channels, so no single feed is broken. The amount is present on every one, which means the points are recoverable | The points service timed out mid-write and nothing retried | Work the points out from the amount and the brand's rate, and mark the row as estimated | Make the column mandatory and send failures to a retry queue rather than writing a blank |
| **Personal data sitting in plain text** — email, first name, last name, date of birth, filled in for all 50,160 people | Reading the column headers was enough | No policy classifying or protecting personal data on this export route | Scramble or drop it the moment it arrives (Part 3) | Tag the columns that hold personal data, and a scanner that blocks any export still carrying readable identifiers |

## Also found, less serious

I've kept these to a paragraph because the brief asks for a short report, not an exhaustive checklist.

The `points_redeemed` column never exceeds exactly 200 and half its values are round numbers like 50
or 100, which makes it look truncated or generated. Still usable, but I don't fully trust it, and
Part 8 leans on that. Every transaction in the file is typed as a `purchase`, so there are no
redemption records at all — structurally important enough that I deal with it properly in Part 8
rather than here. The `join_date` column is broken three separate ways: 999 blank, 30 dated in the
future (2027-03-15), and 205 members whose first purchase predates the day they supposedly joined.
Tier and country are spelled inconsistently, 10 spellings for 4 tiers and 10 for 5 countries,
affecting 800 and 502 rows; trimming spaces and mapping variants fixes it. And the brand recorded
against a transaction disagrees with the member's home brand on 9.3% of rows, which forces a
deliberate choice in Part 6.

## The governance finding, which is bigger than any of these

This arrived as a plain spreadsheet holding the full name, email address and date of birth of 50,160
people. No description of what the file should contain, no version number, no checksum to confirm it
arrived intact.

Every problem in the table above is fixable. The thing an audit would actually escalate is that a
file like this could be produced and sent at all.

---

Evidence for every number here is in `output/dq_findings.txt`, generated by `scripts/01_profile.py`.
`notebooks/00_discovery.ipynb` shows how the larger ones were found, including the checks that turned
up nothing.

Next: [Part 2 — Feature engineering](part2-features.md)
