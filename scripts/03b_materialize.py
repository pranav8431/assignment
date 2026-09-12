#!/usr/bin/env python3
"""
Materialise the cleaned layer.

clean_transactions/clean_members are defined as VIEWS in 03_clean.sql so the logic
stays readable and reviewable. But the view chain contains a window function over
194k rows, so every downstream query re-computes the whole dedup. We snapshot them
into physical tables here -- the same thing a warehouse does when it materialises a
dbt model rather than leaving it ephemeral.
"""
import os, sqlite3
BASE = os.path.join(os.path.dirname(__file__), "..")
con = sqlite3.connect(os.path.join(BASE, "output", "loyalty.db"))
cur = con.cursor()

# rebuild views from source, then snapshot
cur.executescript(open(os.path.join(BASE, "scripts", "03_clean.sql")).read())

for view, table in (("clean_transactions", "ct"), ("clean_members", "cm"),
                    ("clean_exclusions", "cx"), ("v_brand_earn_rate", "ber")):
    cur.execute(f"DROP TABLE IF EXISTS {table}")
    cur.execute(f"CREATE TABLE {table} AS SELECT * FROM {view}")
    n = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  materialised {view:20s} -> {table:4s} {n:>8,} rows")

# swap: views become tables under the original names.
# ALL views must be dropped BEFORE any rename -- clean_members references
# clean_transactions, so renaming one at a time breaks the other's definition.
for view in ("clean_exclusions", "clean_members", "clean_transactions", "v_brand_earn_rate",
             "v_txn_dedup", "v_txn_ranked", "v_txn_typed"):
    cur.execute(f"DROP VIEW IF EXISTS {view}")
for view, table in (("clean_transactions", "ct"), ("clean_members", "cm"),
                    ("clean_exclusions", "cx"), ("v_brand_earn_rate", "ber")):
    cur.execute(f"ALTER TABLE {table} RENAME TO {view}")

cur.execute("CREATE INDEX ix_ct_member ON clean_transactions(member_id)")
cur.execute("CREATE INDEX ix_ct_date   ON clean_transactions(txn_date)")
cur.execute("CREATE INDEX ix_ct_brand  ON clean_transactions(brand)")
cur.execute("CREATE UNIQUE INDEX ix_cm_member ON clean_members(member_id)")
con.commit()
print("\n  clean_members.member_id now carries a UNIQUE index -- the constraint the")
print("  raw layer could not satisfy. That is the Part 1 fix, enforced.")
con.close()
