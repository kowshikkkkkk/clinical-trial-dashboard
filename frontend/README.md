# TrialPulse 🧬
### Real-Time Clinical Data Quality Platform

> Built for the **NEST 2.0 Hackathon** — integrating 207 Excel files across 23 clinical studies into a single AI-powered quality dashboard.

---

## The Problem

Clinical trials generate massive amounts of data across dozens of disconnected systems — Electronic Data Capture (EDC), laboratory reports, safety dashboards, coding dictionaries, and monitoring logs. In a typical trial:

- Data managers manually open Excel files one by one to check quality
- Issues like missing pages, unsigned CRFs, and uncoded adverse events go undetected for weeks
- There is no single score to tell you if a site or subject is "clean"
- Deciding whether a study is ready for submission requires days of manual review

**The result:** delayed trials, regulatory risk, and poor visibility for decision-makers.

---

## Our Solution

TrialPulse is a full-stack clinical data quality platform that:

1. **Ingests** all 207 Excel files from 23 studies automatically in under 2 minutes
2. **Scores** every subject and site with a Data Quality Index (DQI) from 0–100
3. **Visualizes** quality across studies, sites, and subjects in a real-time dashboard
4. **Flags** at-risk sites and subjects automatically
5. **Answers** natural language questions about the data using an AI assistant

---

## What We Built — Step by Step

### Step 1: ETL Pipeline (`etl/01_consolidate.py`)

The first challenge was the data itself — 207 Excel files spread across 23 study folders, each with inconsistent file names, sheet names, and multi-row merged headers.

We wrote a Python script that:
- Loops through all 23 study folders automatically
- Identifies each file type by fuzzy keyword matching (e.g. anything with `CPID_EDC` in the name = EDC metrics file)
- Handles the EDC metrics file's 4-row merged header by skipping those rows and mapping columns by position
- Standardizes all column names (lowercase, underscores, no special characters)
- Concatenates all studies into 9 master DataFrames
- Saves everything into a single SQLite database (`outputs/clinical.db`)

**Result: ~1 million rows across 9 tables, fully queryable in one place**

| Table | Rows | Description |
|---|---|---|
| edc_metrics | 57,997 | One row per subject — the master quality table |
| coding_meddra | 498,393 | Medical term coding status |
| coding_whodd | 308,017 | Drug coding status |
| inactivated | 66,884 | Deactivated records |
| sae | 26,870 | Serious adverse event reviews |
| lab_issues | 20,416 | Missing lab names and ranges |
| missing_pages | 2,751 | Missing CRF pages by visit |
| edrr | 893 | Third-party reconciliation issues |
| missing_visits | 883 | Overdue patient visits |

---

### Step 2: Data Quality Index (`etl/02_derive_metrics.py`)

Raw counts don't tell you which sites need attention. A site with 50 open queries might be fine with 5,000 CRFs, but terrible with only 100.

We designed a **Data Quality Index (DQI)** — a single score from 0 to 100 per subject:

| Component | Weight | How It's Calculated |
|---|---|---|
| Query rate | 25% | Open queries ÷ pages entered (lower = better) |
| SDV completion | 20% | Forms verified ÷ forms requiring verification |
| Signature compliance | 20% | CRFs signed ÷ total CRFs |
| Uncoded terms | 20% | Normalised count from MedDRA + WHO Drug tables |
| Missing pages | 15% | Normalised count from missing pages table |

**A subject is "clean" only when ALL six conditions are zero:**
- No open queries
- No unsigned CRFs
- No uncoded terms (MedDRA or WHO Drug)
- No missing pages
- No open EDRR issues
- No confirmed protocol deviations

**A study is "submission-ready" when:**
- Average DQI ≥ 80
- ≥ 70% of subjects are clean

Scores are rolled up from subject → site → study level, and sites are automatically risk-flagged when DQI < 60, less than 20% clean subjects, or high query volume.

---

### Step 3: Flask REST API (`backend/app.py`)

We built a Flask API to serve all derived metrics as JSON, allowing the React frontend to fetch live data on demand.

| Endpoint | Description |
|---|---|
| `GET /api/summary` | 9 top-level KPIs for the dashboard header |
| `GET /api/studies` | All 23 studies with DQI scores, worst first |
| `GET /api/sites?study=Study+1` | Site metrics, filterable by study |
| `GET /api/subjects?study=X&site=Y` | Individual subject scores |
| `GET /api/alerts` | All risk-flagged sites |
| `GET /api/sae` | SAE review status counts |
| `GET /api/coding` | Uncoded MedDRA/WHO terms by study |
| `GET /api/lab_issues` | Lab issues grouped by study |
| `GET /api/missing_visits` | Overdue visits by study |
| `POST /api/ask` | AI natural language query |

---

### Step 4: React Dashboard (`frontend/src/App.jsx`)

A dark-themed, responsive dashboard built with React and Recharts with four pages:

- **Overview** — 8 KPI cards, DQI bar chart by study, % clean subjects chart, full study comparison table
- **Sites** — site-level performance table with risk flags, filterable by study dropdown
- **Alerts** — all automatically flagged at-risk sites sorted by DQI (worst first)
- **AI Chat** — natural language interface powered by LLaMA 3.3

---

### Step 5: AI Chat Assistant

The AI Chat page lets any team member — DQT, CRA, or site manager — ask plain English questions about the data:

- *"Which studies are submission-ready?"*
- *"Which sites have DQI below 70?"*
- *"Where are the most uncoded terms?"*
- *"What are the top risks across all studies?"*

The assistant fetches live data from the API, builds a compact context, and sends it to **Groq's LLaMA 3.3 70B** model for a fast, accurate response.

---

## Key Results

| Metric | Value |
|---|---|
| Studies processed | 23 |
| Excel files ingested | 207 |
| Total subjects scored | 57,997 |
| Overall DQI | 89.0 / 100 |
| Clean subjects | 73.8% |
| Studies submission-ready | 5 / 23 |
| Open queries flagged | 20,899 |
| Uncoded terms flagged | 1,495 |
| Missing pages flagged | 2,532 |
| Worst site DQI | 31.9 (Study 20, Site 47, AUS) |

---

## Scientific Questions Addressed

| Question | How We Answer It |
|---|---|
| Which sites have the most missing visits/pages? | Missing pages table + site rollup |
| Where are the highest rates of non-conformant data? | EDC metrics: pages_nonconformant per site |
| Which sites require immediate attention? | Automatic risk flag on site_metrics table |
| Is the data clean enough for submission? | submission_ready flag on study_metrics |
| Where are the most open issues in coding? | coding_meddra + coding_whodd uncoded counts |
| Which sites have high deviation counts? | pds_confirmed in site rollup |

---

## Tech Stack

| Layer | Technology |
|---|---|
| ETL & Data Processing | Python 3.11, pandas, openpyxl |
| Database | SQLite via SQLAlchemy |
| Backend API | Flask, flask-cors |
| Frontend | React 18, Vite, Recharts, Axios |
| AI | Groq API — LLaMA 3.3 70B Versatile |
| Version Control | Git, GitHub |

---

## Project Structure

```
clinical-trial-dashboard/
├── data/                          ← 23 study folders (not committed)
├── etl/
│   ├── 01_consolidate.py          ← reads all 207 Excel files → SQLite
│   └── 02_derive_metrics.py       ← DQI scores, clean flags, rollups
├── backend/
│   └── app.py                     ← Flask REST API
├── frontend/
│   └── src/
│       ├── App.jsx                ← React dashboard
│       └── index.css              ← dark theme
├── outputs/
│   └── clinical.db                ← generated SQLite database
├── .env                           ← API keys (not committed)
├── .gitignore
└── README.md
```

---

## Setup & Run

### Prerequisites
- Python 3.10+
- Node.js 18+
- Git Bash (Windows)

### 1. Clone the repo
```bash
git clone https://github.com/kowshikkkkkk/clinical-trial-dashboard.git
cd clinical-trial-dashboard
```

### 2. Set up Python environment
```bash
python -m venv venv
source venv/Scripts/activate
pip install pandas openpyxl sqlalchemy flask flask-cors
```

### 3. Add data files
Place the 23 study folders inside `data/`

### 4. Run the ETL pipeline
```bash
python etl/01_consolidate.py
python etl/02_derive_metrics.py
```

### 5. Add your Groq API key
```bash
echo "VITE_GROQ_API_KEY=your_key_here" > frontend/.env
```

### 6. Start both servers (two terminals)

**Terminal 1 — Flask API:**
```bash
source venv/Scripts/activate
python backend/app.py
```

**Terminal 2 — React frontend:**
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

---

## Team

Built at the **NEST 2.0 Hackathon** by Team TrialPulse.