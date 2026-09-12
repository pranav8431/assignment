-- =====================================================================================
-- 03_clean.sql  --  RAW -> CLEANED
--
-- Every transformation here corresponds to a finding in answers/part1-data-quality.md.
-- Nothing is dropped silently: each exclusion sets a flag or is counted in
-- clean_exclusions, so the cleaning can be reconciled against the raw totals.
-- =====================================================================================

DROP VIEW IF EXISTS v_txn_typed;
DROP VIEW IF EXISTS v_txn_ranked;
DROP VIEW IF EXISTS v_txn_dedup;
DROP VIEW IF EXISTS v_brand_earn_rate;
DROP VIEW IF EXISTS clean_transactions;
DROP VIEW IF EXISTS clean_members;
DROP VIEW IF EXISTS clean_exclusions;

-- -------------------------------------------------------------------------------------
-- STEP 1  Type coercion + date normalisation.
--
-- T5/T6: transaction_date arrives in THREE formats from two different exporters:
--   191,311  'YYYY-MM-DD HH:MM:SS'
--     1,500  'YYYY-MM-DD'            (date only)
--     1,500  'MM/DD/YYYY'            (US locale -- inferred: first component never > 12,
--                                      second reaches 31. Documented as an assumption.)
-- A naive CAST/substr would silently lose the 3,000 rows in the latter two formats.
-- -------------------------------------------------------------------------------------
CREATE VIEW v_txn_typed AS
SELECT
    transaction_id,
    member_id,
    brand,
    channel,
    transaction_type,
    transaction_date AS transaction_date_raw,
    CASE
        WHEN transaction_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'
            THEN substr(transaction_date, 1, 10)
        WHEN transaction_date GLOB '[0-9][0-9]/[0-9][0-9]/[0-9][0-9][0-9][0-9]'
            THEN substr(transaction_date, 7, 4) || '-' ||
                 substr(transaction_date, 1, 2) || '-' ||
                 substr(transaction_date, 4, 2)
    END AS txn_date,
    CAST(amount          AS REAL) AS amount_raw,
    CAST(points_redeemed AS REAL) AS points_redeemed,
    CASE WHEN trim(points_earned) = '' THEN NULL
         ELSE CAST(points_earned AS REAL) END AS points_earned_raw
FROM raw_transactions;

-- -------------------------------------------------------------------------------------
-- STEP 2  Deduplicate on the natural key.
--
-- T1: 1,995 transaction_ids are duplicated. 1,936 groups are byte-identical
-- (at-least-once delivery replay); 59 groups CONFLICT on their payload.
-- We use ROW_NUMBER, not SELECT DISTINCT: DISTINCT would keep all 59 conflicting
-- rows and silently double-count them. Ordering is deterministic so re-runs are stable.
-- -------------------------------------------------------------------------------------
CREATE VIEW v_txn_ranked AS
SELECT t.*,
       ROW_NUMBER() OVER (
           PARTITION BY transaction_id
           ORDER BY txn_date, amount_raw, points_earned_raw
       ) AS rn,
       COUNT(*) OVER (PARTITION BY transaction_id) AS dup_group_size
FROM v_txn_typed t;

CREATE VIEW v_txn_dedup AS
SELECT * FROM v_txn_ranked WHERE rn = 1;

-- -------------------------------------------------------------------------------------
-- STEP 3  Derive the per-brand earn rate FROM THE DATA (never hard-coded).
--
-- Computed only over rows we trust: positive, non-sentinel amount and a present
-- points value. The rate turns out to be deterministic per brand
-- (PulseEats 1.75 / PulseHome 2.00 / PulseMart 2.30) which is what makes the
-- T4 imputation below defensible. 06_validate.py asserts this.
-- -------------------------------------------------------------------------------------
CREATE VIEW v_brand_earn_rate AS
SELECT brand,
       ROUND(SUM(points_earned_raw) / SUM(amount_raw), 4) AS earn_rate,
       COUNT(*) AS n_rows
FROM v_txn_dedup
WHERE points_earned_raw IS NOT NULL
  AND amount_raw > 0
  AND amount_raw < 9999
GROUP BY brand;

-- -------------------------------------------------------------------------------------
-- STEP 4  The cleaned transaction fact.
--
-- T2  sentinel amounts (999999.99 / 99999 / 88888.5 / 75000 / 64000, 15 rows):
--     NULL the amount but KEEP the row. The purchase happened -- the price is what is
--     corrupt. Deleting the row would bias frequency/recency features downward;
--     winsorising would invent a price we have no basis for.
-- T3  negative amounts (2,012 rows): these are refunds posted as negative purchases,
--     and points were awarded on ABS(amount) (median ratio 2.001 = the earn rate).
--     We KEEP the refund so it nets spend down, but ZERO the wrongly granted points.
--     ABS() would launder a refund into a purchase; dropping would overstate value.
-- T4  null points_earned (1,514 rows): impute amount * derived brand earn rate and
--     FLAG it. Dropping loses real transactions; zero-filling corrupts points_balance.
-- T7  orphan member_ids (2,988 rows): flagged, not deleted, so Part 8 can quantify them.
-- -------------------------------------------------------------------------------------
CREATE VIEW clean_transactions AS
SELECT
    d.transaction_id,
    d.member_id,
    d.brand,
    d.channel,
    d.txn_date,
    -- amount
    CASE WHEN d.amount_raw >= 9999 THEN NULL ELSE d.amount_raw END       AS amount,
    CASE WHEN d.amount_raw >= 9999 THEN 1 ELSE 0 END                     AS is_sentinel_amount,
    CASE WHEN d.amount_raw <  0    THEN 1 ELSE 0 END                     AS is_refund,
    -- points earned
    CASE
        WHEN d.amount_raw < 0                THEN 0.0                       -- T3
        WHEN d.points_earned_raw IS NOT NULL THEN d.points_earned_raw
        WHEN d.amount_raw >= 9999            THEN NULL                      -- no basis to impute
        ELSE ROUND(d.amount_raw * r.earn_rate, 0)                           -- T4
    END                                                                  AS points_earned,
    CASE WHEN d.points_earned_raw IS NULL AND d.amount_raw < 9999
              AND d.amount_raw >= 0 THEN 1 ELSE 0 END                    AS is_points_imputed,
    CASE WHEN d.amount_raw < 0 THEN d.points_earned_raw ELSE 0 END       AS points_reversed_on_refund,
    d.points_redeemed,
    CASE WHEN m.member_id IS NULL THEN 1 ELSE 0 END                      AS is_orphan_member,
    d.dup_group_size
FROM v_txn_dedup d
LEFT JOIN v_brand_earn_rate r ON r.brand = d.brand
LEFT JOIN (SELECT DISTINCT member_id FROM raw_members) m ON m.member_id = d.member_id
WHERE d.txn_date IS NOT NULL;

-- -------------------------------------------------------------------------------------
-- STEP 5  The cleaned member dimension.
--
-- M1  150 member_ids appear twice, differing ONLY in tier and status -- an SCD-2
--     history flattened without an is_current pick. There is no updated_at, so we
--     cannot know which row is current. We collapse to the HIGHER tier and the more
--     engaged status (the conservative choice for a churn/marketing use case) and
--     raise tier_ambiguous_flag so a modeller can ablate them.
--     Rejected: dropping both rows (loses 150 real members); arbitrary first-row
--     (non-deterministic across runs -- a reproducibility bug).
-- M3/M4  tier and country conformed by trim + case normalisation, plus an explicit
--     country synonym map. 800 tier rows and 502 country rows are affected.
-- M6  30 join_dates are 2027-03-15, after the last observed transaction -> NULLed.
-- -------------------------------------------------------------------------------------
CREATE VIEW clean_members AS
WITH conformed AS (
    SELECT
        member_id,
        lower(trim(email))                                          AS email,
        CASE lower(trim(tier))
            WHEN 'bronze' THEN 'Bronze' WHEN 'silver'   THEN 'Silver'
            WHEN 'gold'   THEN 'Gold'   WHEN 'platinum' THEN 'Platinum'
        END                                                         AS tier,
        CASE lower(trim(country))
            WHEN 'in' THEN 'IN' WHEN 'india'     THEN 'IN'
            WHEN 'us' THEN 'US' WHEN 'usa'       THEN 'US' WHEN 'u.s.' THEN 'US'
            WHEN 'sg' THEN 'SG' WHEN 'singapore' THEN 'SG'
            WHEN 'ae' THEN 'AE' WHEN 'gb'        THEN 'GB'
            ELSE upper(trim(country))
        END                                                         AS country,
        lower(trim(status))                                         AS status_raw,
        trim(brand)                                                 AS brand,
        CASE WHEN trim(join_date) GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
                  AND trim(join_date) <= (SELECT MAX(txn_date) FROM clean_transactions)
             THEN trim(join_date) END                               AS join_date,
        CASE WHEN trim(join_date) = '' THEN 1 ELSE 0 END            AS is_join_date_missing,
        CASE WHEN trim(join_date) > (SELECT MAX(txn_date) FROM clean_transactions)
             THEN 1 ELSE 0 END                                      AS is_join_date_future,
        substr(trim(birth_date), 1, 4)                              AS birth_year,
        CASE lower(trim(tier)) WHEN 'bronze' THEN 1 WHEN 'silver' THEN 2
                               WHEN 'gold' THEN 3 WHEN 'platinum' THEN 4 END AS tier_rank,
        CASE lower(trim(status)) WHEN 'active' THEN 3 WHEN 'inactive' THEN 2
                                 WHEN 'churned' THEN 1 END          AS status_rank
    FROM raw_members
),
ranked AS (
    SELECT c.*,
           COUNT(*)  OVER (PARTITION BY member_id) AS n_source_rows,
           MAX(tier_rank)   OVER (PARTITION BY member_id) AS max_tier_rank,
           MAX(status_rank) OVER (PARTITION BY member_id) AS max_status_rank,
           ROW_NUMBER() OVER (PARTITION BY member_id
                              ORDER BY tier_rank DESC, status_rank DESC) AS rn
    FROM conformed c
)
SELECT
    member_id,
    email,
    CASE max_tier_rank WHEN 1 THEN 'Bronze' WHEN 2 THEN 'Silver'
                       WHEN 3 THEN 'Gold'   WHEN 4 THEN 'Platinum' END AS tier,
    CASE max_status_rank WHEN 3 THEN 'active' WHEN 2 THEN 'inactive'
                         WHEN 1 THEN 'churned' END                     AS status,
    brand, country, join_date, birth_year,
    is_join_date_missing, is_join_date_future,
    CASE WHEN n_source_rows > 1 THEN 1 ELSE 0 END                      AS tier_ambiguous_flag
FROM ranked
WHERE rn = 1;

-- -------------------------------------------------------------------------------------
-- STEP 6  Reconciliation ledger -- every point the cleaning removes must be accounted
--         for. 06_validate.py asserts raw_total == clean_total + SUM(these).
-- -------------------------------------------------------------------------------------
CREATE VIEW clean_exclusions AS
SELECT 'duplicate_txn_rows' AS reason,
       COUNT(*) AS n_rows,
       COALESCE(SUM(points_earned_raw), 0) AS points_removed
FROM v_txn_ranked WHERE rn > 1
UNION ALL
SELECT 'points_reversed_on_refund', COUNT(*), COALESCE(SUM(points_reversed_on_refund),0)
FROM clean_transactions WHERE is_refund = 1
UNION ALL
SELECT 'orphan_member_rows', COUNT(*), COALESCE(SUM(points_earned),0)
FROM clean_transactions WHERE is_orphan_member = 1
UNION ALL
SELECT 'sentinel_amount_rows', COUNT(*), 0
FROM clean_transactions WHERE is_sentinel_amount = 1
UNION ALL
SELECT 'unparseable_date_rows', COUNT(*), 0
FROM v_txn_dedup WHERE txn_date IS NULL;
