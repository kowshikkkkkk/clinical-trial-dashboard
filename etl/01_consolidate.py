"""
01_consolidate.py
Reads all 207 Excel files across 23 study folders and builds
9 master DataFrames, then saves them to a SQLite database.

Usage (from project root with venv active):
    python etl/01_consolidate.py
"""

import os
import re
import pandas as pd
from sqlalchemy import create_engine

# ── CONFIG ────────────────────────────────────────────────────────────────────
DATA_DIR = "data"           # folder containing all 23 study subfolders
DB_PATH  = "outputs/clinical.db"

# EDC Metrics: the real column names live across rows 0 and 1
# Row 0 has the main header, row 1 has sub-headers for merged cells.
# We resolve them manually using the column-index map we verified.
EDC_COLUMNS = {
     0: "project_name",
     1: "region",
     2: "country",
     3: "site_id",
     4: "subject_id",
     5: "latest_visit",
     6: "subject_status",
     7: "missing_visits",
     8: "missing_pages",
     9: "coded_terms",
    10: "uncoded_terms",
    11: "open_issues_lnr",
    12: "open_issues_edrr",
    13: "inactivated_forms",
    14: "esae_review_dm",
    15: "esae_review_safety",
    16: "expected_visits",
    17: "pages_entered",
    18: "pages_nonconformant",
    19: "crfs_with_queries_nc",
    20: "crfs_without_queries_nc",
    21: "pct_clean_crf",
    22: "dm_queries",
    23: "clinical_queries",
    24: "medical_queries",
    25: "site_queries",
    26: "field_monitor_queries",
    27: "coding_queries",
    28: "safety_queries",
    29: "total_queries",
    30: "crfs_require_sdv",
    31: "forms_verified",
    32: "crfs_frozen",
    33: "crfs_not_frozen",
    34: "crfs_locked",
    35: "crfs_unlocked",
    36: "pds_confirmed",
    37: "pds_proposed",
    38: "crfs_signed",
    39: "crfs_overdue_sign_0_45",
    40: "crfs_overdue_sign_45_90",
    41: "crfs_overdue_sign_90plus",
    42: "broken_signatures",
    43: "crfs_never_signed",
}

# ── HELPERS ───────────────────────────────────────────────────────────────────

def get_study_name(folder_name):
    """Extract a clean study name like 'Study 1' from the folder name."""
    match = re.match(r"(study\s*\d+)", folder_name, re.IGNORECASE)
    return match.group(1).title().replace(" ", " ") if match else folder_name[:20]


def find_file(folder_path, keyword):
    """Return the first file in folder whose name contains keyword (case-insensitive)."""
    for f in os.listdir(folder_path):
        if keyword.lower() in f.lower() and f.endswith(".xlsx"):
            return os.path.join(folder_path, f)
    return None


def safe_read(path, sheet, skiprows=None, header=0):
    """Read an Excel sheet safely; return empty DataFrame on failure."""
    try:
        return pd.read_excel(path, sheet_name=sheet, skiprows=skiprows, header=header)
    except Exception as e:
        print(f"    WARNING: could not read {os.path.basename(path)} / {sheet}: {e}")
        return pd.DataFrame()


# ── LOADERS ───────────────────────────────────────────────────────────────────

def load_edc_metrics(folder_path, study_name):
    path = find_file(folder_path, "CPID_EDC") or find_file(folder_path, "EDC_Metrics")
    if not path:
        return pd.DataFrame()

    # Skip rows 0-3 (merged header rows); row 4 onward is data
    df = pd.read_excel(path, sheet_name="Subject Level Metrics",
                       header=None, skiprows=4)

    # Keep only the columns we've mapped
    cols_to_keep = [c for c in EDC_COLUMNS if c < len(df.columns)]
    df = df[cols_to_keep].copy()
    df.rename(columns=EDC_COLUMNS, inplace=True)

    # Drop completely empty rows
    df.dropna(subset=["subject_id"], inplace=True)
    df.insert(0, "study", study_name)
    return df


def load_missing_pages(folder_path, study_name):
    path = find_file(folder_path, "Missing_Pages") or find_file(folder_path, "Missing_Page")
    if not path:
        return pd.DataFrame()
    df = safe_read(path, 0)  # sheet=0 handles any sheet name
    if df.empty:
        return df
    df.columns = [c.strip().lower().replace(" ", "_").replace("#", "num") for c in df.columns]
    df.dropna(how="all", inplace=True)
    for col in df.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns:
        df[col] = df[col].astype(str)
    if "study" not in df.columns:
        df.insert(0, "study", study_name)
    return df


def load_missing_visits(folder_path, study_name):
    path = find_file(folder_path, "Visit_Projection") or find_file(folder_path, "Visit Projection")
    if not path:
        return pd.DataFrame()
    df = safe_read(path, 0)  # use sheet=0 instead of sheet name
    if df.empty:
        return df
    df.columns = [c.strip().lower().replace(" ", "_").replace("#", "num") for c in df.columns]
    df.dropna(how="all", inplace=True)
    # Keep only the 6 core columns we care about
    core = ["country", "site", "subject", "visit", "projected_date", "num_days_outstanding"]
    df = df[[c for c in core if c in df.columns]]
    # Convert dates to string to avoid SQLite Timestamp errors
    for col in df.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns:
        df[col] = df[col].astype(str)
    if "study" not in df.columns:
        df.insert(0, "study", study_name)
    return df


def load_sae(folder_path, study_name):
    path = find_file(folder_path, "SAE") or find_file(folder_path, "eSAE")
    if not path:
        return pd.DataFrame()
    frames = []
    for sheet, role in [("SAE Dashboard_DM", "DM"), ("SAE Dashboard_Safety", "Safety")]:
        df = safe_read(path, sheet)
        if not df.empty:
            df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
            df.dropna(how="all", inplace=True)
            df["role"] = role
            df.insert(0, "study", study_name)
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_coding(folder_path, study_name, dict_type):
    keyword = "MedDRA" if dict_type == "meddra" else "WHODD"
    path = find_file(folder_path, keyword)
    if not path:
        # also try generic "Coding" filename
        path = find_file(folder_path, "Coding")
    if not path:
        return pd.DataFrame()

    # Don't hardcode sheet name — just read the first sheet
    df = safe_read(path, sheet=0)
    if df.empty:
        return df
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    df.dropna(how="all", inplace=True)
    if "study" not in df.columns:
        df.insert(0, "study", study_name)
    return df


def load_edrr(folder_path, study_name):
    path = find_file(folder_path, "EDRR")
    if not path:
        return pd.DataFrame()
    df = safe_read(path, "OpenIssuesSummary")
    if df.empty:
        return df
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    df.dropna(how="all", inplace=True)
    # 'study' column already exists in this file
    if "study" not in df.columns:
        df.insert(0, "study", study_name)
    return df

def load_lab(folder_path, study_name):
    path = find_file(folder_path, "Missing_Lab") or find_file(folder_path, "Lab_Name")
    if not path:
        return pd.DataFrame()
    df = safe_read(path, 0)
    if df.empty:
        return df
    df.columns = [c.strip().lower().replace(" ", "_").replace("/", "_") for c in df.columns]
    df.dropna(how="all", inplace=True)
    if "study" not in df.columns:
        df.insert(0, "study", study_name)
    return df


def load_inactivated(folder_path, study_name):
    path = find_file(folder_path, "Inactivated")
    if not path:
        return pd.DataFrame()
    df = safe_read(path, 0)
    if df.empty:
        return df
    df.columns = [c.strip().lower().replace(" ", "_").replace("\n", "_") for c in df.columns]
    df.dropna(how="all", inplace=True)
    df.insert(0, "study", study_name)
    return df


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    os.makedirs("outputs", exist_ok=True)

    # Collect all frames per table
    tables = {
        "edc_metrics":    [],
        "missing_pages":  [],
        "missing_visits": [],
        "sae":            [],
        "coding_meddra":  [],
        "coding_whodd":   [],
        "edrr":           [],
        "lab_issues":     [],
        "inactivated":    [],
    }

    study_folders = sorted(os.listdir(DATA_DIR))
    print(f"Found {len(study_folders)} study folders.\n")

    for folder in study_folders:
        folder_path = os.path.join(DATA_DIR, folder)
        if not os.path.isdir(folder_path):
            continue

        study_name = get_study_name(folder)
        print(f"Processing {study_name}...")

        tables["edc_metrics"].append(load_edc_metrics(folder_path, study_name))
        tables["missing_pages"].append(load_missing_pages(folder_path, study_name))
        tables["missing_visits"].append(load_missing_visits(folder_path, study_name))
        tables["sae"].append(load_sae(folder_path, study_name))
        tables["coding_meddra"].append(load_coding(folder_path, study_name, "meddra"))
        tables["coding_whodd"].append(load_coding(folder_path, study_name, "whodd"))
        tables["edrr"].append(load_edrr(folder_path, study_name))
        tables["lab_issues"].append(load_lab(folder_path, study_name))
        tables["inactivated"].append(load_inactivated(folder_path, study_name))

    # Concatenate and save to SQLite
    engine = create_engine(f"sqlite:///{DB_PATH}")
    print(f"\nSaving to {DB_PATH}...\n")

    for table_name, frames in tables.items():
        non_empty = [f for f in frames if not f.empty]
        if non_empty:
            master = pd.concat(non_empty, ignore_index=True)
            # Convert any remaining datetime columns to string for SQLite
            for col in master.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns:
                master[col] = master[col].astype(str)
            master.to_sql(table_name, engine, if_exists="replace", index=False)
            print(f"  {table_name:20s} → {len(master):>5} rows, {len(master.columns):>3} cols")
        else:
            print(f"  {table_name:20s} → no data found")

    print("\nDone. Database ready at:", DB_PATH)


if __name__ == "__main__":
    main()