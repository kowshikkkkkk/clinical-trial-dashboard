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

    # Call Claude API
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return error("ANTHROPIC_API_KEY environment variable not set.")

    payload = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1000,
        "system": context,
        "messages": [{"role": "user", "content": question}]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data    = payload,
        headers = {
            "Content-Type":      "application/json",
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
        },
        method = "POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            data   = json.loads(resp.read().decode("utf-8"))
            answer = data["content"][0]["text"]
        return jsonify({"answer": answer})
    except urllib.error.HTTPError as e:
        return error(f"Claude API error: {e.read().decode()}", 502)
    except Exception as e:
        return error(f"Unexpected error: {str(e)}", 500)


# ── HEALTH CHECK ──────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "db": DB_PATH})


# ── RUN ───────────────────────────────────────────────────────────────────────

# ── AGENT ROUTES ──────────────────────────────────────────────────────────────

@app.route("/api/agent/scan", methods=["GET"])
def agent_scan():
    import json, urllib.request
    sites = query_db("SELECT * FROM site_metrics ORDER BY avg_dqi ASC")
    study = query_db("SELECT * FROM study_metrics ORDER BY avg_dqi ASC")
    prompt = f"""You are a clinical trial risk management agent. Analyze the site data below and generate a prioritized action plan.

For each at-risk site, specify:
1. PRIORITY (Critical/High/Medium)
2. SITE (study + site_id + country)
3. RISK REASON (specific metric that triggered the flag)
4. RECOMMENDED ACTION (exactly what the CRA or DM should do)
5. DEADLINE (how urgent - immediate/this week/this month)

Focus on the worst 10 sites. Be specific with numbers. Format each as a clear action item.

SITE DATA:
{json.dumps(sites[:30], indent=2)}

STUDY DATA:
{json.dumps(study, indent=2)}"""

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return error("GROQ_API_KEY not set")

    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "You are a clinical data quality agent. Be concise, specific, and action-oriented."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 1500,
        "temperature": 0.2,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data   = json.loads(resp.read().decode("utf-8"))
            answer = data["choices"][0]["message"]["content"]
        return jsonify({"action_plan": answer, "sites_scanned": len(sites)})
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/agent/report", methods=["POST"])
def agent_report():
    import json, urllib.request
    body    = request.get_json()
    study   = body.get("study")
    site_id = body.get("site_id")
    if not study or not site_id:
        return error("Request body must include study and site_id")

    site_data = query_db("SELECT * FROM site_metrics WHERE study = :study AND site_id = :site_id",
                         {"study": study, "site_id": site_id})
    subject_data = query_db("""
        SELECT subject, dqi_score, is_clean, total_queries,
               missing_page_count, total_uncoded, crfs_never_signed,
               pds_confirmed, open_edrr_issues
        FROM subject_metrics
        WHERE study = :study AND site_id = :site_id
        ORDER BY dqi_score ASC LIMIT 20
    """, {"study": study, "site_id": site_id})

    prompt = f"""Generate a professional Clinical Research Associate (CRA) site visit report for:
Study: {study}
Site: {site_id}

Use this data:
SITE METRICS: {json.dumps(site_data, indent=2)}
SUBJECT DETAILS: {json.dumps(subject_data, indent=2)}

The report should include:
1. SITE OVERVIEW - key metrics summary
2. CRITICAL FINDINGS - specific issues with subject IDs and numbers
3. DATA QUALITY STATUS - DQI score interpretation
4. REQUIRED ACTIONS - numbered list, assigned to CRA/DM/Site
5. FOLLOW-UP TIMELINE - specific deadlines

Write in professional clinical trial language. Be specific with numbers."""

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return error("GROQ_API_KEY not set")

    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "You are an expert Clinical Research Associate writing formal site visit reports."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 1500,
        "temperature": 0.2,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.groqcom/openai/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data   = json.loads(resp.read().decode("utf-8"))
            answer = data["choices"][0]["message"]["content"]
        return jsonify({"report": answer})
    except Exception as e:
        return error(str(e), 500)


@app.route("/api/agent/readiness", methods=["GET"])
def agent_readiness():
    import json, urllib.request
    studies = query_db("SELECT * FROM study_metrics ORDER BY avg_dqi DESC")
    alerts  = query_db("SELECT * FROM site_metrics WHERE risk_flag = 'True' ORDER BY avg_dqi ASC")

    prompt = f"""You are a clinical data submission readiness agent. For each study below, give a GO / NO-GO decision for interim analysis or regulatory submission.

For each study provide:
1. STUDY NAME
2. DECISION: GO or NO-GO or CONDITIONAL
3. DQI STATUS: score and what it means
4. BLOCKING ISSUES: specific metrics that prevent submission (if any)
5. REQUIRED ACTIONS: what must be resolved before GO (if NO-GO)
6. ESTIMATED EFFORT: how much work is needed to reach GO

Be decisive. Use the actual numbers. A study needs DQI >= 80 AND >= 70% clean subjects to be GO.

STUDY METRICS:
{json.dumps(studies, indent=2)}

AT-RISK SITES:
{json.dumps(alerts[:15], indent=2)}"""

    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return error("GROQ_API_KEY not set")

    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "You are a clinical data submission readiness expert. Be decisive and specific."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 2000,
        "temperature": 0.2,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data   = json.loads(resp.read().decode("utf-8"))
            answer = data["choices"][0]["message"]["content"]
        return jsonify({"readiness_report": answer, "total_studies": len(studies)})
    except Exception as e:
        return error(str(e), 500)
if __name__ == "__main__":
    print("Starting Clinical Trial Dashboard API...")
    print(f"Database: {os.path.abspath(DB_PATH)}")
    print("Endpoints available at http://localhost:5000/api/")
    app.run(debug=True, port=5000)
