-- =====================================================================================
-- 04_features.sql  --  member-level churn feature table   (answers/part2-features.md)
--
-- POINT-IN-TIME CORRECTNESS IS THE WHOLE DESIGN.
-- Every aggregate below is bounded by  txn_date <= (SELECT as_of_date FROM params).
-- The same file produces BOTH the training rows (as_of = 2026-04-01) and the
-- scoring rows (as_of = 2026-06-30); only the parameter changes. That is what
-- prevents train/serve skew.
--
-- Measured evidence for why this matters (06_validate.py re-derives it):
--   corr(recency, label) computed over ALL data  = 0.760   <- leaks the outcome window
--   corr(recency, label) computed over <= as_of  = 0.162   <- legitimate signal
-- =====================================================================================

DROP TABLE IF EXISTS member_features;

CREATE TABLE member_features AS
WITH p AS (
    SELECT as_of_date,
           date(as_of_date, '-90 day')  AS w90,
           date(as_of_date, '-180 day') AS w180,
           date(as_of_date, '-365 day') AS w365
    FROM params
),
-- Observation window only. Orphan members (T7) are excluded here: they are not in
-- the member master, cannot be contacted, and are not a modellable population.
tx AS (
    SELECT ct.*
    FROM clean_transactions ct, p
    WHERE ct.txn_date <= p.as_of_date
      AND ct.is_orphan_member = 0
),
agg AS (
    SELECT
        tx.member_id,

        -- ---------- RECENCY ----------
        MAX(tx.txn_date)                                                     AS last_txn_date,
        MIN(tx.txn_date)                                                     AS first_txn_date,
        CAST(julianday((SELECT as_of_date FROM p)) - julianday(MAX(tx.txn_date)) AS INT)
                                                                             AS recency_days,

        -- ---------- FREQUENCY ----------
        COUNT(*)                                                             AS txn_count_lifetime,
        SUM(CASE WHEN tx.txn_date >  (SELECT w90  FROM p) THEN 1 ELSE 0 END) AS txn_count_90d,
        SUM(CASE WHEN tx.txn_date <= (SELECT w90  FROM p)
                  AND tx.txn_date >  (SELECT w180 FROM p) THEN 1 ELSE 0 END) AS txn_count_prev_90d,
        SUM(CASE WHEN tx.txn_date >  (SELECT w365 FROM p) THEN 1 ELSE 0 END) AS txn_count_365d,

        -- ---------- MONETARY ----------
        -- amount is NULL on the 15 sentinel rows (T2), so SUM/AVG skip them
        -- automatically while the row still counts toward frequency. That is the
        -- entire reason we NULLed rather than deleted.
        ROUND(SUM(tx.amount), 2)                                             AS monetary_lifetime,
        ROUND(AVG(tx.amount), 2)                                             AS avg_basket,
        ROUND(SUM(CASE WHEN tx.txn_date >  (SELECT w90 FROM p)
                       THEN tx.amount ELSE 0 END), 2)                        AS spend_90d,
        ROUND(SUM(CASE WHEN tx.txn_date <= (SELECT w90  FROM p)
                        AND tx.txn_date >  (SELECT w180 FROM p)
                       THEN tx.amount ELSE 0 END), 2)                        AS spend_prev_90d,

        -- ---------- POINTS / REDEMPTION ----------
        ROUND(SUM(tx.points_earned), 0)                                      AS points_earned_total,
        ROUND(SUM(tx.points_redeemed), 0)                                    AS points_redeemed_total,
        ROUND(SUM(tx.points_earned) - SUM(tx.points_redeemed), 0)            AS points_balance,
        MAX(CASE WHEN tx.points_redeemed > 0 THEN 1 ELSE 0 END)              AS ever_redeemed_flag,

        -- ---------- BREADTH / CHANNEL ----------
        COUNT(DISTINCT tx.brand)                                             AS distinct_brands,
        COUNT(DISTINCT tx.channel)                                           AS distinct_channels,
        ROUND(1.0 * SUM(CASE WHEN tx.channel = 'app' THEN 1 ELSE 0 END) / COUNT(*), 3)
                                                                             AS pct_app,

        -- ---------- DATA-QUALITY META ----------
        -- lets a modeller ablate every member touched by a repaired row
        MAX(tx.is_points_imputed)                                            AS has_imputed_points,
        MAX(tx.is_sentinel_amount)                                           AS has_sentinel_amount,
        MAX(tx.is_refund)                                                    AS has_refund,
        SUM(CASE WHEN tx.dup_group_size > 1 THEN 1 ELSE 0 END)               AS n_deduped_txns
    FROM tx
    GROUP BY tx.member_id
)
SELECT
    (SELECT as_of_date FROM p)                                               AS as_of_date,
    m.member_id,
    m.brand                                                                  AS member_brand,
    m.tier,
    m.country,
    a.recency_days,
    -- M5/M6: join_date is NULL for 998 members (missing) + 30 (impossible future date).
    -- We do NOT impute a fake join date; we expose NULL plus the flag and let the
    -- model learn from missingness. Imputing the median would manufacture tenure.
    CASE WHEN m.join_date IS NOT NULL
         THEN CAST(julianday(a.last_txn_date) - julianday(m.join_date) AS INT) END
                                                                             AS tenure_days,
    m.is_join_date_missing,
    m.is_join_date_future,
    a.txn_count_lifetime,
    a.txn_count_90d,
    a.txn_count_prev_90d,
    a.txn_count_365d,
    -- engagement TREND. Preferred over raw counts: see the anti-predictive
    -- frequency finding in answers/part2-features.md.
    ROUND(1.0 * a.txn_count_90d / NULLIF(a.txn_count_prev_90d, 0), 3)        AS freq_trend_ratio,
    ROUND(a.spend_90d / NULLIF(a.spend_prev_90d, 0), 3)                      AS spend_trend_ratio,
    a.monetary_lifetime,
    a.avg_basket,
    a.spend_90d,
    a.spend_prev_90d,
    -- average days between purchases: the member's own cadence, which is what
    -- recency should really be judged against (median across the base is 104 days)
    CASE WHEN a.txn_count_lifetime > 1
         THEN CAST((julianday(a.last_txn_date) - julianday(a.first_txn_date))
                   / (a.txn_count_lifetime - 1) AS INT) END                  AS avg_gap_days,
    ROUND(1.0 * a.recency_days /
          NULLIF(CAST((julianday(a.last_txn_date) - julianday(a.first_txn_date))
                 / NULLIF(a.txn_count_lifetime - 1, 0) AS INT), 0), 3)       AS recency_vs_own_cadence,
    a.points_earned_total,
    a.points_redeemed_total,
    a.points_balance,
    ROUND(a.points_redeemed_total / NULLIF(a.points_earned_total, 0), 4)     AS redemption_rate,
    a.ever_redeemed_flag,
    a.distinct_brands,
    CASE WHEN a.distinct_brands > 1 THEN 1 ELSE 0 END                        AS is_cross_brand,
    a.distinct_channels,
    a.pct_app,
    m.tier_ambiguous_flag,
    a.has_imputed_points,
    a.has_sentinel_amount,
    a.has_refund,
    a.n_deduped_txns,
    CASE WHEN a.has_imputed_points = 1 OR a.has_sentinel_amount = 1
              OR a.has_refund = 1 OR a.n_deduped_txns > 0
              OR m.tier_ambiguous_flag = 1 OR m.is_join_date_missing = 1
         THEN 1 ELSE 0 END                                                   AS dq_suspect_flag,
    a.last_txn_date
FROM agg a
JOIN clean_members m ON m.member_id = a.member_id;

CREATE INDEX ix_mf_member ON member_features(member_id);
