// src/Agent.jsx
// Agentic AI page — proactive risk scanning, CRA report generation,
// and submission readiness assessment.

import { useState, useEffect } from "react"
import axios from "axios"

const API = "http://localhost:5000/api"

function Loading({ text }) {
  return (
    <div className="loading">
      <div className="spinner" />
      {text || "Agent thinking..."}
    </div>
  )
}

// ── RISK SCANNER ──────────────────────────────────────────────────────────────

function RiskScanner() {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [ran, setRan] = useState(false)

  const runScan = async () => {
    setLoading(true)
    setRan(true)
    try {
      // fetch context from our API
      const [sitesRes, studyRes] = await Promise.all([
        fetch(`${API}/sites`).then(r => r.json()),
        fetch(`${API}/studies`).then(r => r.json()),
      ])

      const prompt = `You are a clinical trial risk management agent. Analyze the site data below and generate a prioritized action plan.

For each at-risk site specify:
1. PRIORITY (Critical/High/Medium)
2. SITE (study + site_id + country)
3. RISK REASON (specific metric that triggered the flag)
4. RECOMMENDED ACTION (exactly what the CRA or DM should do)
5. DEADLINE (immediate/this week/this month)

Focus on the worst 10 sites. Be specific with numbers.

SITE DATA:
${JSON.stringify(sitesRes.slice(0, 30), null, 2)}

STUDY DATA:
${JSON.stringify(studyRes, null, 2)}`

      const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${import.meta.env.VITE_GROQ_API_KEY}`,
        },
        body: JSON.stringify({
          model: "llama-3.3-70b-versatile",
          messages: [
            { role: "system", content: "You are a clinical data quality agent. Be concise, specific, and action-oriented." },
            { role: "user", content: prompt }
          ],
          max_tokens: 1500,
          temperature: 0.2,
        })
      })
      const data = await res.json()
      const answer = data.choices?.[0]?.message?.content || JSON.stringify(data)
      setResult({ action_plan: answer, sites_scanned: sitesRes.length })
    } catch (e) {
      setResult({ action_plan: `⚠️ Error: ${e.message}` })
    } finally {
      setLoading(false)
    }
  }
  return (
    <div className="card">
      <div className="card-header">
        <span>🔍</span>
        <span className="card-title">Risk Scanner Agent</span>
        <span className="card-sub">scans all sites → prioritized action plan</span>
      </div>
      <div className="card-body">
        <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16, lineHeight: 1.6 }}>
          The agent scans all site metrics, identifies risk signals, and generates
          a prioritized action plan with specific recommendations for each CRA and DM.
        </p>
        <button
          className="btn"
          onClick={runScan}
          disabled={loading}
          style={{ marginBottom: 20 }}
        >
          {loading ? "Scanning..." : ran ? "🔄 Re-scan All Sites" : "🚀 Run Risk Scan"}
        </button>

        {loading && <Loading text="Agent scanning all sites and generating action plan..." />}

        {result && !loading && (
          <div>
            <div style={{
              fontSize: 11, fontFamily: "var(--mono)", color: "var(--text-muted)",
              marginBottom: 12
            }}>
              {result.sites_scanned} sites scanned · action plan generated
            </div>
            <div style={{
              background: "var(--bg3)",
              border: "1px solid var(--border)",
              borderRadius: 10,
              padding: "20px 24px",
              fontSize: 13,
              lineHeight: 1.8,
              whiteSpace: "pre-wrap",
              fontFamily: "var(--font)",
              color: "var(--text)",
            }}>
              {result.action_plan}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── CRA REPORT GENERATOR ──────────────────────────────────────────────────────

function CraReportGenerator({ studies }) {
  const [selectedStudy, setSelectedStudy] = useState("")
  const [siteId, setSiteId] = useState("")
  const [sites, setSites] = useState([])
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)

  // Load sites when study changes
  useEffect(() => {
    if (!selectedStudy) { setSites([]); setSiteId(""); return }
    axios.get(`${API}/sites?study=${encodeURIComponent(selectedStudy)}`)
      .then(r => setSites(r.data))
  }, [selectedStudy])

  const generateReport = async () => {
    if (!selectedStudy || !siteId) return
    setLoading(true)
    setReport(null)
    try {
      const [siteRes, subjectRes] = await Promise.all([
        fetch(`${API}/sites?study=${encodeURIComponent(selectedStudy)}`).then(r => r.json()),
        fetch(`${API}/subjects?study=${encodeURIComponent(selectedStudy)}&site=${encodeURIComponent(siteId)}&limit=20`).then(r => r.json()),
      ])

      const prompt = `Generate a professional CRA site visit report for:
Study: ${selectedStudy}
Site: ${siteId}

SITE METRICS: ${JSON.stringify(siteRes.find(s => s.site_id === siteId), null, 2)}
SUBJECT DETAILS: ${JSON.stringify(subjectRes, null, 2)}

Include:
1. SITE OVERVIEW - key metrics summary
2. CRITICAL FINDINGS - specific issues with subject IDs and numbers
3. DATA QUALITY STATUS - DQI score interpretation
4. REQUIRED ACTIONS - numbered list assigned to CRA/DM/Site
5. FOLLOW-UP TIMELINE - specific deadlines`

      const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${import.meta.env.VITE_GROQ_API_KEY}`,
        },
        body: JSON.stringify({
          model: "llama-3.3-70b-versatile",
          messages: [
            { role: "system", content: "You are an expert CRA writing formal site visit reports." },
            { role: "user", content: prompt }
          ],
          max_tokens: 1500,
          temperature: 0.2,
        })
      })
      const data = await res.json()
      setReport(data.choices?.[0]?.message?.content || JSON.stringify(data))
    } catch (e) {
      setReport(`⚠️ Error: ${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  const copyReport = () => {
    navigator.clipboard.writeText(report)
  }

  return (
    <div className="card">
      <div className="card-header">
        <span>📝</span>
        <span className="card-title">CRA Report Generator</span>
        <span className="card-sub">auto-drafts site visit reports</span>
      </div>
      <div className="card-body">
        <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16, lineHeight: 1.6 }}>
          Select a study and site — the agent will analyze all subject-level data
          and draft a professional CRA site visit report with findings and action items.
        </p>

        <div className="filter-bar" style={{ marginBottom: 16 }}>
          <select
            className="filter-select"
            value={selectedStudy}
            onChange={e => { setSelectedStudy(e.target.value); setReport(null) }}
          >
            <option value="">Select study...</option>
            {studies?.map(s => (
              <option key={s.study} value={s.study}>{s.study}</option>
            ))}
          </select>

          <select
            className="filter-select"
            value={siteId}
            onChange={e => { setSiteId(e.target.value); setReport(null) }}
            disabled={!selectedStudy}
          >
            <option value="">Select site...</option>
            {sites.map(s => (
              <option key={s.site_id} value={s.site_id}>
                {s.site_id} — {s.country} (DQI: {s.avg_dqi?.toFixed(1)})
              </option>
            ))}
          </select>

          <button
            className="btn"
            onClick={generateReport}
            disabled={!selectedStudy || !siteId || loading}
          >
            {loading ? "Generating..." : "📄 Generate Report"}
          </button>
        </div>

        {loading && <Loading text="Agent analyzing site data and drafting report..." />}

        {report && !loading && (
          <div>
            <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 10 }}>
              <button
                onClick={copyReport}
                style={{
                  background: "var(--bg3)",
                  border: "1px solid var(--border)",
                  borderRadius: 6,
                  padding: "6px 14px",
                  color: "var(--text-muted)",
                  fontSize: 12,
                  cursor: "pointer",
                  fontFamily: "var(--font)",
                }}
              >
                📋 Copy Report
              </button>
            </div>
            <div style={{
              background: "var(--bg3)",
              border: "1px solid var(--border)",
              borderRadius: 10,
              padding: "20px 24px",
              fontSize: 13,
              lineHeight: 1.8,
              whiteSpace: "pre-wrap",
              fontFamily: "var(--font)",
              color: "var(--text)",
              maxHeight: 500,
              overflowY: "auto",
            }}>
              {report}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── SUBMISSION READINESS ──────────────────────────────────────────────────────

function SubmissionReadiness() {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [ran, setRan] = useState(false)

  const runCheck = async () => {
    setLoading(true)
    setRan(true)
    try {
      const [studyRes, alertsRes] = await Promise.all([
        fetch(`${API}/studies`).then(r => r.json()),
        fetch(`${API}/alerts`).then(r => r.json()),
      ])

      const prompt = `You are a submission readiness agent. For each study give GO / NO-GO / CONDITIONAL decision.

For each study:
1. STUDY NAME
2. DECISION: GO or NO-GO or CONDITIONAL
3. DQI STATUS
4. BLOCKING ISSUES
5. REQUIRED ACTIONS
6. ESTIMATED EFFORT

A study needs DQI >= 80 AND >= 70% clean subjects to be GO.

STUDY METRICS: ${JSON.stringify(studyRes, null, 2)}
AT-RISK SITES: ${JSON.stringify(alertsRes.slice(0, 15), null, 2)}`

      const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${import.meta.env.VITE_GROQ_API_KEY}`,
        },
        body: JSON.stringify({
          model: "llama-3.3-70b-versatile",
          messages: [
            { role: "system", content: "You are a clinical data submission readiness expert. Be decisive and specific." },
            { role: "user", content: prompt }
          ],
          max_tokens: 2000,
          temperature: 0.2,
        })
      })
      const data = await res.json()
      setResult({ readiness_report: data.choices?.[0]?.message?.content || JSON.stringify(data), total_studies: studyRes.length })
    } catch (e) {
      setResult({ readiness_report: `⚠️ Error: ${e.message}` })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <span>✅</span>
        <span className="card-title">Submission Readiness Agent</span>
        <span className="card-sub">GO / NO-GO for every study</span>
      </div>
      <div className="card-body">
        <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16, lineHeight: 1.6 }}>
          The agent evaluates every study against submission criteria — DQI threshold,
          clean subject rate, open queries, and protocol deviations — and returns a
          GO / NO-GO / CONDITIONAL decision with specific blocking issues.
        </p>
        <button
          className="btn"
          onClick={runCheck}
          disabled={loading}
          style={{ marginBottom: 20 }}
        >
          {loading ? "Checking..." : ran ? "🔄 Re-check Readiness" : "🎯 Check Submission Readiness"}
        </button>

        {loading && <Loading text="Agent evaluating all 23 studies for submission readiness..." />}

        {result && !loading && (
          <div>
            <div style={{
              fontSize: 11, fontFamily: "var(--mono)", color: "var(--text-muted)",
              marginBottom: 12
            }}>
              {result.total_studies} studies evaluated
            </div>
            <div style={{
              background: "var(--bg3)",
              border: "1px solid var(--border)",
              borderRadius: 10,
              padding: "20px 24px",
              fontSize: 13,
              lineHeight: 1.8,
              whiteSpace: "pre-wrap",
              fontFamily: "var(--font)",
              color: "var(--text)",
              maxHeight: 600,
              overflowY: "auto",
            }}>
              {result.readiness_report}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── AGENT PAGE ROOT ───────────────────────────────────────────────────────────

export default function AgentPage({ studies }) {
  return (
    <>
      {/* Explainer banner */}
      <div style={{
        background: "linear-gradient(135deg, #1a2235, #0f1a2e)",
        border: "1px solid #1e3a5f",
        borderRadius: 12,
        padding: "20px 24px",
        display: "flex",
        gap: 16,
        alignItems: "flex-start",
      }}>
        <span style={{ fontSize: 28 }}>🤖</span>
        <div>
          <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 6, color: "#93c5fd" }}>
            Agentic AI — Proactive Clinical Data Management
          </div>
          <div style={{ fontSize: 13, color: "var(--text-muted)", lineHeight: 1.7 }}>
            Unlike the AI Chat which answers questions on demand, these agents <strong style={{ color: "var(--text)" }}>act autonomously</strong> —
            they scan all data, identify risks, make decisions, and generate ready-to-use outputs
            for Data Quality Teams, CRAs, and site managers. No manual analysis required.
          </div>
        </div>
      </div>

      <RiskScanner />
      <CraReportGenerator studies={studies} />
      <SubmissionReadiness />
    </>
  )
}
