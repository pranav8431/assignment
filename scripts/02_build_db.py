#!/usr/bin/env python3
"""
Loads both CSVs into SQLite as a RAW layer -- every column TEXT, zero cleaning,
zero coercion. This is deliberate: the raw layer must be a faithful reproduction
of what landed, so that every later transformation is auditable against it.

Cleaning happens in 03_clean.sql, in SQL, where it can be reviewed.
"""
import csv, os, sqlite3

BASE = os.path.join(os.path.dirname(__file__), "..")
DB   = os.path.join(BASE, "output", "loyalty.db")

if os.path.exists(DB):
    os.remove(DB)
con = sqlite3.connect(DB)
cur = con.cursor()

def load(fn, table):
    path = os.path.join(BASE, fn)
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        r = csv.reader(f)
        cols = next(r)
        ddl = ", ".join(f'"{c}" TEXT' for c in cols)
        cur.execute(f"CREATE TABLE {table} ({ddl})")
        ins = f"INSERT INTO {table} VALUES ({','.join('?' * len(cols))})"
        n = 0
        batch = []
        for row in r:
            batch.append(row)
            n += 1
            if len(batch) >= 20000:
                cur.executemany(ins, batch); batch = []
        if batch:
            cur.executemany(ins, batch)
    con.commit()
    print(f"  {table:20s} {n:>8,} rows  ({len(cols)} cols)")
    return n

print("Loading RAW layer (no cleaning):")
load("members.csv",      "raw_members")
load("transactions.csv", "raw_transactions")

# Indexes only -- no constraints, because the raw data violates them all.
# (That violation is itself the Part 1 finding; enforcing here would hide it.)
cur.execute("CREATE INDEX ix_rt_member ON raw_transactions(member_id)")
cur.execute("CREATE INDEX ix_rt_txn    ON raw_transactions(transaction_id)")
cur.execute("CREATE INDEX ix_rm_member ON raw_members(member_id)")
con.commit()

# Demonstrate that a PK on the natural key would fail today -- evidence for Part 3.
for tbl, key in (("raw_members", "member_id"), ("raw_transactions", "transaction_id")):
    d = cur.execute(f"SELECT COUNT(*) FROM (SELECT {key} FROM {tbl} GROUP BY {key} HAVING COUNT(*)>1)").fetchone()[0]
    print(f"  ! {tbl}.{key} is NOT unique: {d:,} duplicated values "
          f"(a PRIMARY KEY would reject this load today)")

con.close()
print(f"\nRaw layer written to {DB}")
