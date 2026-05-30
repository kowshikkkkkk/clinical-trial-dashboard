"""
backend/app.py
Flask REST API that serves clinical trial metrics from clinical.db.
The React frontend calls these endpoints to power the dashboard.

Usage (from project root with venv active):
    python backend/app.py

Endpoints:
    GET /api/studies                     - all study-level metrics
    GET /api/sites?study=Study+1         - site metrics (optionally filtered by study)
    GET /api/subjects?study=X&site=Y     - subject metrics (filtered by study and/or site)
    GET /api/summary                     - high-level KPI snapshot
    GET /api/alerts                      - sites/subjects flagged as at-risk
    GET /api/sae                         - SAE review status counts
    GET /api/coding                      - uncoded term counts by study
    GET /api/lab_issues                  - lab issues by study
    GET /api/missing_visits              - overdue visits by study
    POST /api/ask                        - AI natural language query (Claude API)
"""

import os
import pandas as pd
from flask import Flask, jsonify, request
from flask_cors import CORS
from sqlalchemy import create_engine, text

app = Flask(__name__)
CORS(app)  # allow React frontend (different port) to call this API

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "outputs", "clinical.db")
engine  = create_engine(f"sqlite:///{DB_PATH}")

# ── HELPERS ───────────────────────────────────────────────────────────────────

def query_db(sql, params=None):
    """Run a SQL query and return a list of dicts (JSON-serialisable)."""
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        rows   = result.fetchall()
        cols   = result.keys()
    df = pd.DataFrame(rows, columns=cols)
    # Convert booleans and NaN for JSON
    df = df.where(pd.notnull(df), None)
    for col in df.select_dtypes(include="bool").columns:
        df[col] = df[col].astype(str)
    return df.to_dict(orient="records")


def error(msg, code=400):
    return jsonify({"error": msg}), code


# ── ROUTES ────────────────────────────────────────────────────────────────────

@app.route("/api/studies")
def get_studies():
    """All study-level metrics, sorted by DQI ascending (worst first)."""
    rows = query_db("""
        SELECT study, total_subjects, clean_subjects, avg_dqi,
               pct_clean, total_queries, total_missing_pages,
               total_uncoded, submission_ready
        FROM   study_metrics
        ORDER  BY avg_dqi ASC
    """)
    return jsonify(rows)


@app.route("/api/sites")
def get_sites():
    """Site metrics, optionally filtered by study."""
    study = request.args.get("study")
    if study:
        rows = query_db("""
            SELECT study, region, country, site_id, total_subjects,
                   clean_subjects, avg_dqi, pct_clean_subjects,
                   total_queries, total_missing_pages, total_uncoded,
                   total_pds, open_edrr_issues, risk_flag
            FROM   site_metrics
            WHERE  study = :study
            ORDER  BY avg_dqi ASC
        """, {"study": study})
    else:
        rows = query_db("""
            SELECT study, region, country, site_id, total_subjects,
                   clean_subjects, avg_dqi, pct_clean_subjects,
                   total_queries, total_missing_pages, total_uncoded,
                   total_pds, open_edrr_issues, risk_flag
            FROM   site_metrics
            ORDER  BY avg_dqi ASC
            LIMIT  200
        """)
    return jsonify(rows)


@app.route("/api/subjects")
def get_subjects():
    """Subject metrics filtered by study and/or site. Always paginated."""
    study  = request.args.get("study")
    site   = request.args.get("site")
    limit  = min(int(request.args.get("limit", 100)), 500)
    offset = int(request.args.get("offset", 0))

    conditions = []
    params     = {"limit": limit, "offset": offset}

    if study:
        conditions.append("study = :study")
        params["study"] = study
    if site:
        conditions.append("site_id = :site")
        params["site"] = site

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    rows = query_db(f"""
        SELECT study, region, country, site_id, subject,
               subject_status, dqi_score, is_clean,
               total_queries, missing_page_count, total_uncoded,
               open_edrr_issues, crfs_never_signed, pds_confirmed,
               query_rate_pct, sdv_completion_pct, sig_compliance_pct
        FROM   subject_metrics
        {where}
        ORDER  BY dqi_score ASC
        LIMIT  :limit OFFSET :offset
    """, params)
    return jsonify(rows)


@app.route("/api/summary")
def get_summary():
    """Top-level KPI snapshot for the dashboard header cards."""
    rows = query_db("""
        SELECT
            COUNT(DISTINCT study)                                AS total_studies,
            SUM(total_subjects)                                  AS total_subjects,
            ROUND(AVG(avg_dqi), 1)                               AS overall_dqi,
            SUM(clean_subjects)                                  AS total_clean_subjects,
            ROUND(SUM(clean_subjects) * 100.0
                  / NULLIF(SUM(total_subjects), 0), 1)           AS pct_clean,
            SUM(CASE WHEN submission_ready = 'True' THEN 1
                     ELSE 0 END)                                 AS studies_ready,
            SUM(total_queries)                                   AS total_open_queries,
            SUM(total_uncoded)                                   AS total_uncoded_terms,
            SUM(total_missing_pages)                             AS total_missing_pages
        FROM study_metrics
    """)
    return jsonify(rows[0] if rows else {})


@app.route("/api/alerts")
def get_alerts():
    """Sites flagged as high-risk (risk_flag = True), worst first."""
    rows = query_db("""
        SELECT study, country, site_id, total_subjects,
               avg_dqi, pct_clean_subjects, total_queries,
               total_pds, open_edrr_issues, risk_flag
        FROM   site_metrics
        WHERE  risk_flag = 'True'
        ORDER  BY avg_dqi ASC
        LIMIT  50
    """)
    return jsonify(rows)


@app.route("/api/sae")
def get_sae():
    """SAE review status counts by study and role."""
    rows = query_db("""
        SELECT study,
               role,
               review_status,
               COUNT(*) AS count
        FROM   sae
        GROUP  BY study, role, review_status
        ORDER  BY study, role
    """)
    return jsonify(rows)


@app.route("/api/coding")
def get_coding():
    """Uncoded term counts by study for MedDRA and WHO Drug."""
    meddra = query_db("""
        SELECT study,
               SUM(CASE WHEN coding_status LIKE '%UnCoded%' THEN 1 ELSE 0 END) AS uncoded,
               COUNT(*)                                                          AS total
        FROM   coding_meddra
        GROUP  BY study
        ORDER  BY uncoded DESC
    """)
    whodd = query_db("""
        SELECT study,
               SUM(CASE WHEN coding_status LIKE '%UnCoded%' THEN 1 ELSE 0 END) AS uncoded,
               COUNT(*)                                                          AS total
        FROM   coding_whodd
        GROUP  BY study
        ORDER  BY uncoded DESC
    """)
    return jsonify({"meddra": meddra, "whodd": whodd})


@app.route("/api/lab_issues")
def get_lab_issues():
    """Lab issue counts by study and issue type."""
    rows = query_db("""
        SELECT study,
               issue,
               COUNT(*) AS count
        FROM   lab_issues
        GROUP  BY study, issue
        ORDER  BY count DESC
    """)
    return jsonify(rows)


@app.route("/api/missing_visits")
def get_missing_visits():
    """Overdue visits grouped by study, showing avg days outstanding."""
    rows = query_db("""
        SELECT study,
               COUNT(*)                        AS total_overdue,
               ROUND(AVG(num_days_outstanding), 1) AS avg_days_overdue,
               MAX(num_days_outstanding)           AS max_days_overdue
        FROM   missing_visits
        GROUP  BY study
        ORDER  BY total_overdue DESC
    """)
    return jsonify(rows)


@app.route("/api/ask", methods=["POST"])
def ask_ai():
    """
    Natural language query endpoint.
    Accepts: { "question": "Which sites have DQI below 70?" }
    Returns: { "answer": "..." }

    Pulls summary context from the DB and sends it to Claude API.
    """
    import json, urllib.request, urllib.error

    body = request.get_json()
    if not body or "question" not in body:
        return error("Request body must include a 'question' field.")

    question = body["question"].strip()
    if not question:
        return error("Question cannot be empty.")

    # Build a compact data context to send to Claude
    try:
        studies  = query_db("SELECT * FROM study_metrics ORDER BY avg_dqi ASC")
        alerts   = query_db("SELECT * FROM site_metrics WHERE risk_flag = 'True' ORDER BY avg_dqi ASC LIMIT 20")
        summary  = query_db("""
            SELECT SUM(total_subjects) as subjects,
                   ROUND(AVG(avg_dqi),1) as avg_dqi,
                   SUM(total_queries) as queries,
                   SUM(total_uncoded) as uncoded
            FROM study_metrics
        """)

        context = f"""
You are a clinical data quality analyst assistant. Answer questions based only on the data below.
Be concise and specific. Use numbers. Highlight risks clearly.

STUDY METRICS:
{json.dumps(studies, indent=2)}

AT-RISK SITES (risk_flag=True, lowest DQI first):
{json.dumps(alerts[:10], indent=2)}

OVERALL SUMMARY:
{json.dumps(summary[0] if summary else {}, indent=2)}
"""
    except Exception as e:
        return error(f"Failed to load data context: {str(e)}")

    # Call Groq API instead of Claude
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return error("GROQ_API_KEY environment variable not set.")

    payload = json.dumps({
        "model": "llama3-70b-8192",
        "messages": [
            {"role": "system", "content": context},
            {"role": "user",   "content": question}
        ],
        "max_tokens": 1000,
        "temperature": 0.3,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data    = payload,
        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method = "POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            data   = json.loads(resp.read().decode("utf-8"))
            answer = data["choices"][0]["message"]["content"]
        return jsonify({"answer": answer})
    except urllib.error.HTTPError as e:
        return error(f"Groq API error: {e.read().decode()}", 502)
    except Exception as e:
        return error(f"Unexpected error: {str(e)}", 500)

# ── HEALTH CHECK ──────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "db": DB_PATH})


# ── RUN ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Starting Clinical Trial Dashboard API...")
    print(f"Database: {os.path.abspath(DB_PATH)}")
    print("Endpoints available at http://localhost:5000/api/")
    app.run(debug=True, port=5000)