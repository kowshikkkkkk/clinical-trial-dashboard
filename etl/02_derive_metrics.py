"""
02_derive_metrics.py
Calculates derived metrics and Data Quality Index (DQI) for each subject and site.
Reads from clinical.db (built by 01_consolidate.py) and writes back new tables.

DQI Score (0-100, higher = better quality):
  Component            Weight   Source
  ─────────────────────────────────────────────────────
  Query rate             25%    edc_metrics: total_queries / pages_entered
  SDV completion         20%    edc_metrics: forms_verified / crfs_require_sdv
  Signature compliance   20%    edc_metrics: crfs_signed / (crfs_signed + crfs_never_signed)
  Uncoded terms          20%    coding_meddra + coding_whodd: uncoded count per subject
  Missing pages          15%    missing_pages: count per subject

A subject is "clean" only when ALL of the following are true:
  - total_queries == 0
  - crfs_never_signed == 0
  - uncoded_terms == 0
  - no missing pages
  - no open EDRR issues
  - pds_confirmed == 0

Usage (from project root with venv active):
    python etl/02_derive_metrics.py
"""

import pandas as pd
import numpy as np
from sqlalchemy import create_engine

DB_PATH = "outputs/clinical.db"

# ── LOAD ──────────────────────────────────────────────────────────────────────

def load_tables(engine):
    print("Loading tables from database...")
    tables = {}
    for t in ["edc_metrics", "missing_pages", "missing_visits",
              "coding_meddra", "coding_whodd", "edrr", "sae", "lab_issues"]:
        tables[t] = pd.read_sql_table(t, engine)
        print(f"  {t:20s} → {len(tables[t]):>6} rows")
    return tables


# ── SUBJECT-LEVEL HELPERS ─────────────────────────────────────────────────────

def build_uncoded_per_subject(coding_meddra, coding_whodd):
    """Count uncoded terms per subject from both coding tables."""
    frames = []
    for df, label in [(coding_meddra, "meddra"), (coding_whodd, "whodd")]:
        # Normalise column name variations across studies
        status_col = next((c for c in df.columns if "coding_status" in c), None)
        subj_col   = next((c for c in df.columns if c == "subject"), None)
        study_col  = next((c for c in df.columns if c == "study"), None)
        if not all([status_col, subj_col, study_col]):
            continue
        uncoded = df[df[status_col].str.contains("UnCoded", na=False, case=False)]
        grp = uncoded.groupby([study_col, subj_col]).size().reset_index(name=f"uncoded_{label}")
        frames.append(grp)

    if not frames:
        return pd.DataFrame(columns=["study", "subject", "total_uncoded"])

    merged = frames[0]
    for f in frames[1:]:
        merged = merged.merge(f, on=["study", "subject"], how="outer")
    merged.fillna(0, inplace=True)
    uncoded_cols = [c for c in merged.columns if c.startswith("uncoded_")]
    merged["total_uncoded"] = merged[uncoded_cols].sum(axis=1)
    return merged[["study", "subject", "total_uncoded"]]


def build_missing_pages_per_subject(missing_pages):
    """Count missing pages per subject."""
    # Normalise subject column name
    subj_col  = next((c for c in missing_pages.columns if "subject" in c), None)
    study_col = next((c for c in missing_pages.columns if "study" in c), None)
    if not subj_col or not study_col:
        return pd.DataFrame(columns=["study", "subject", "missing_page_count"])

    grp = (missing_pages
           .groupby([study_col, subj_col])
           .size()
           .reset_index(name="missing_page_count"))
    grp.rename(columns={study_col: "study", subj_col: "subject"}, inplace=True)
    return grp


def build_edrr_per_subject(edrr):
    """Sum open EDRR issues per subject."""
    subj_col  = next((c for c in edrr.columns if "subject" in c), None)
    study_col = next((c for c in edrr.columns if "study" in c), None)
    issue_col = next((c for c in edrr.columns if "open_issue" in c or "count" in c), None)
    if not all([subj_col, study_col, issue_col]):
        return pd.DataFrame(columns=["study", "subject", "open_edrr_issues"])

    grp = (edrr
           .groupby([study_col, subj_col])[issue_col]
           .sum()
           .reset_index(name="open_edrr_issues"))
    grp.rename(columns={study_col: "study", subj_col: "subject"}, inplace=True)
    return grp


# ── DQI CALCULATION ───────────────────────────────────────────────────────────

def safe_rate(numerator, denominator, default=0.0):
    """Return numerator/denominator, or default if denominator is 0."""
    with np.errstate(divide="ignore", invalid="ignore"):
        result = np.where(denominator > 0, numerator / denominator, default)
    return result


def calculate_dqi(df):
    # Force all numeric columns to actual numbers - they may come back
    # from SQLite as strings if the column had mixed content
    numeric_cols = [
        "total_queries", "pages_entered", "forms_verified", "crfs_require_sdv",
        "crfs_signed", "crfs_never_signed", "pds_confirmed", "pds_proposed",
        "total_uncoded", "missing_page_count", "open_edrr_issues",
        "pages_nonconformant", "crfs_with_queries_nc", "crfs_without_queries_nc",
        "expected_visits", "crfs_frozen", "crfs_locked", "crfs_unlocked",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    """
    Add DQI score (0-100) and is_clean flag to subject-level DataFrame.

    Component scores are all 0-1 (1 = perfect), then weighted and scaled to 100.
    """
    n = len(df)

    # 1. Query rate score (lower queries per page = better)
    query_rate   = safe_rate(df["total_queries"].fillna(0),
                             df["pages_entered"].fillna(1))
    query_score  = np.clip(1 - query_rate, 0, 1)          # 0 queries → score 1.0

    # 2. SDV completion score
    sdv_score    = safe_rate(df["forms_verified"].fillna(0),
                             df["crfs_require_sdv"].fillna(0),
                             default=1.0)                  # if nothing to verify → perfect
    sdv_score    = np.clip(sdv_score, 0, 1)

    # 3. Signature compliance score
    total_crfs   = df["crfs_signed"].fillna(0) + df["crfs_never_signed"].fillna(0)
    sig_score    = safe_rate(df["crfs_signed"].fillna(0), total_crfs, default=1.0)
    sig_score    = np.clip(sig_score, 0, 1)

    # 4. Uncoded terms score (fewer uncoded = better)
    max_uncoded  = df["total_uncoded"].max() if df["total_uncoded"].max() > 0 else 1
    uncoded_score = 1 - np.clip(df["total_uncoded"] / max_uncoded, 0, 1)

    # 5. Missing pages score (fewer missing = better)
    max_missing  = df["missing_page_count"].max() if df["missing_page_count"].max() > 0 else 1
    page_score   = 1 - np.clip(df["missing_page_count"] / max_missing, 0, 1)

    # Weighted DQI (weights sum to 1.0)
    weights = dict(query=0.25, sdv=0.20, sig=0.20, uncoded=0.20, pages=0.15)
    dqi = (
        weights["query"]   * query_score  +
        weights["sdv"]     * sdv_score    +
        weights["sig"]     * sig_score    +
        weights["uncoded"] * uncoded_score +
        weights["pages"]   * page_score
    ) * 100

    df = df.copy()
    df["query_rate_pct"]       = (query_rate   * 100).round(1)
    df["sdv_completion_pct"]   = (sdv_score    * 100).round(1)
    df["sig_compliance_pct"]   = (sig_score    * 100).round(1)
    df["dqi_score"]            = dqi.round(1)

    # Clean subject: ALL five conditions must be zero
    df["is_clean"] = (
        (df["total_queries"].fillna(0)     == 0) &
        (df["crfs_never_signed"].fillna(0) == 0) &
        (df["total_uncoded"].fillna(0)     == 0) &
        (df["missing_page_count"].fillna(0)== 0) &
        (df["open_edrr_issues"].fillna(0)  == 0) &
        (df["pds_confirmed"].fillna(0)     == 0)
    )

    return df


# ── SITE-LEVEL ROLLUP ─────────────────────────────────────────────────────────

def build_site_metrics(subject_df):
    """Aggregate subject metrics to site level."""
    grp = subject_df.groupby(["study", "region", "country", "site_id"]).agg(
        total_subjects      = ("subject",         "count"),
        clean_subjects      = ("is_clean",            "sum"),
        avg_dqi             = ("dqi_score",           "mean"),
        min_dqi             = ("dqi_score",           "min"),
        total_queries       = ("total_queries",       "sum"),
        total_missing_pages = ("missing_page_count",  "sum"),
        total_uncoded       = ("total_uncoded",       "sum"),
        total_pds           = ("pds_confirmed",       "sum"),
        crfs_never_signed   = ("crfs_never_signed",   "sum"),
        open_edrr_issues    = ("open_edrr_issues",    "sum"),
    ).reset_index()

    grp["pct_clean_subjects"] = (
        safe_rate(grp["clean_subjects"], grp["total_subjects"]) * 100
    ).round(1)
    grp["avg_dqi"] = grp["avg_dqi"].round(1)

    # Risk flag: sites needing immediate attention
    grp["risk_flag"] = (
        (grp["avg_dqi"] < 60) |
        (grp["pct_clean_subjects"] < 20) |
        (grp["total_queries"] > grp["total_queries"].quantile(0.80)) |
        (grp["total_pds"] > 0)
    )

    return grp.sort_values("avg_dqi")


# ── STUDY-LEVEL ROLLUP ────────────────────────────────────────────────────────

def build_study_metrics(subject_df):
    grp = subject_df.groupby("study").agg(
        total_subjects      = ("subject",            "count"),   # changed
        clean_subjects      = ("is_clean",            "sum"),
        avg_dqi             = ("dqi_score",           "mean"),
        total_queries       = ("total_queries",       "sum"),
        total_missing_pages = ("missing_page_count",  "sum"),
        total_uncoded       = ("total_uncoded",       "sum"),
    ).reset_index()

    grp["pct_clean"] = (
        safe_rate(grp["clean_subjects"], grp["total_subjects"]) * 100
    ).round(1)
    grp["avg_dqi"] = grp["avg_dqi"].round(1)

    # Submission readiness: DQI >= 80 and >= 70% clean subjects
    grp["submission_ready"] = (
        (grp["avg_dqi"] >= 80) & (grp["pct_clean"] >= 70)
    )

    return grp.sort_values("avg_dqi")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    engine = create_engine(f"sqlite:///{DB_PATH}")

    tables = load_tables(engine)

    # ── Build supporting per-subject tables
    print("\nCalculating supporting metrics...")
    uncoded_df      = build_uncoded_per_subject(tables["coding_meddra"], tables["coding_whodd"])
    missing_page_df = build_missing_pages_per_subject(tables["missing_pages"])
    edrr_df         = build_edrr_per_subject(tables["edrr"])

    # ── Start from EDC metrics (one row per subject)
    edc = tables["edc_metrics"].copy()

    # Normalise subject column for joins
    edc.rename(columns={"subject_id": "subject"}, inplace=True)

    # ── Join all supporting metrics
    subject_df = (edc
        .merge(uncoded_df,      on=["study", "subject"], how="left")
        .merge(missing_page_df, on=["study", "subject"], how="left")
        .merge(edrr_df,         on=["study", "subject"], how="left")
    )

    # Fill missing join results with 0 (subject had no issues in that table)
    for col in ["total_uncoded", "missing_page_count", "open_edrr_issues"]:
        subject_df[col] = subject_df[col].fillna(0)

    # ── Calculate DQI
    print("Calculating DQI scores...")
    subject_df = calculate_dqi(subject_df)

    # ── Build rollups
    site_df  = build_site_metrics(subject_df)
    study_df = build_study_metrics(subject_df)

    # ── Save to DB
    print(f"\nSaving derived tables to {DB_PATH}...")
    for df, name in [
        (subject_df, "subject_metrics"),
        (site_df,    "site_metrics"),
        (study_df,   "study_metrics"),
    ]:
        # Convert any datetime cols to string
        for col in df.select_dtypes(include=["datetime64[ns]", "datetimetz", "bool"]).columns:
            df[col] = df[col].astype(str)
        df.to_sql(name, engine, if_exists="replace", index=False)
        print(f"  {name:20s} → {len(df):>6} rows, {len(df.columns):>3} cols")

    # ── Print summary
    print("\n── Study Summary ─────────────────────────────────────────────")
    print(study_df[["study","total_subjects","avg_dqi","pct_clean","submission_ready"]].to_string(index=False))

    print("\n── Top 10 Sites Needing Attention (lowest DQI) ───────────────")
    risk_sites = site_df[site_df["risk_flag"] == "True"].head(10) if "True" in site_df["risk_flag"].values else site_df.head(10)
    print(risk_sites[["study","country","site_id","total_subjects","avg_dqi","pct_clean_subjects","total_queries"]].to_string(index=False))

    print("\nDone.")


if __name__ == "__main__":
    main()