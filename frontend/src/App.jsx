// src/App.jsx
import { useState, useEffect, useCallback } from "react"
import axios from "axios"
import AgentPage from "./Agent.jsx"
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  RadialBarChart, RadialBar, Cell, ScatterChart, Scatter,
  CartesianGrid, Legend
} from "recharts"

const API = "http://localhost:5000/api"

// ── HELPERS ───────────────────────────────────────────────────────────────────

function dqiColor(score) {
  if (score >= 90) return "#10b981"
  if (score >= 75) return "#f59e0b"
  return "#ef4444"
}

function DqiBadge({ score }) {
  const color = dqiColor(score)
  return (
    <span className="dqi-badge">
      <span style={{ color }}>{score?.toFixed(1)}</span>
      <span className="dqi-bar">
        <span className="dqi-fill" style={{ width: `${score}%`, background: color }} />
      </span>
    </span>
  )
}

function Pill({ value, thresholds }) {
  // thresholds: [goodMin, warnMin] — above goodMin = success, above warnMin = warning, else danger
  const [good, warn] = thresholds || [80, 60]
  const cls = value >= good ? "pill-success" : value >= warn ? "pill-warning" : "pill-danger"
  return <span className={`pill ${cls}`}>{value}</span>
}

function Loading() {
  return <div className="loading"><div className="spinner" />Loading...</div>
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: "#111827", border: "1px solid #1e2d45",
      borderRadius: 8, padding: "10px 14px", fontSize: 12
    }}>
      <div style={{ color: "#94a3b8", marginBottom: 4 }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color || "#e2e8f0" }}>
          {p.name}: <strong>{typeof p.value === "number" ? p.value.toFixed(1) : p.value}</strong>
        </div>
      ))}
    </div>
  )
}

// ── OVERVIEW PAGE ─────────────────────────────────────────────────────────────

function Overview({ summary, studies }) {
  if (!summary || !studies) return <Loading />

  const kpis = [
    { label: "Total Studies", value: summary.total_studies, cls: "kpi-accent", sub: "across all programmes" },
    { label: "Total Subjects", value: summary.total_subjects?.toLocaleString(), cls: "kpi-cyan", sub: "enrolled globally" },
    { label: "Overall DQI", value: summary.overall_dqi, cls: summary.overall_dqi >= 80 ? "kpi-success" : "kpi-warning", sub: "data quality index" },
    { label: "Clean Subjects", value: `${summary.pct_clean}%`, cls: "kpi-success", sub: `${summary.total_clean_subjects?.toLocaleString()} subjects` },
    { label: "Studies Ready", value: summary.studies_ready, cls: "kpi-success", sub: "submission-ready" },
    { label: "Open Queries", value: summary.total_open_queries?.toLocaleString(), cls: "kpi-warning", sub: "need resolution" },
    { label: "Uncoded Terms", value: summary.total_uncoded_terms?.toLocaleString(), cls: "kpi-danger", sub: "MedDRA + WHO Drug" },
    { label: "Missing Pages", value: summary.total_missing_pages?.toLocaleString(), cls: "kpi-danger", sub: "across all sites" },
  ]

  const barData = studies.map(s => ({
    name: s.study.replace("Study ", "S"),
    dqi: s.avg_dqi,
    clean: s.pct_clean,
    queries: s.total_queries,
  }))

  return (
    <>
      <div className="kpi-grid">
        {kpis.map(k => (
          <div className="kpi-card" key={k.label}>
            <div className="kpi-label">{k.label}</div>
            <div className={`kpi-value ${k.cls}`}>{k.value}</div>
            <div className="kpi-sub">{k.sub}</div>
          </div>
        ))}
      </div>

      <div className="chart-grid">
        <div className="card">
          <div className="card-header">
            <span>📊</span>
            <span className="card-title">DQI by Study</span>
            <span className="card-sub">higher = better</span>
          </div>
          <div className="card-body">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={barData} barSize={14}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e2d45" />
                <XAxis dataKey="name" tick={{ fill: "#64748b", fontSize: 10 }} />
                <YAxis domain={[0, 100]} tick={{ fill: "#64748b", fontSize: 10 }} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="dqi" name="DQI Score" radius={[4, 4, 0, 0]}>
                  {barData.map((d, i) => (
                    <Cell key={i} fill={dqiColor(d.dqi)} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <span>🧹</span>
            <span className="card-title">% Clean Subjects by Study</span>
            <span className="card-sub">target ≥ 70%</span>
          </div>
          <div className="card-body">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={barData} barSize={14}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e2d45" />
                <XAxis dataKey="name" tick={{ fill: "#64748b", fontSize: 10 }} />
                <YAxis domain={[0, 100]} tick={{ fill: "#64748b", fontSize: 10 }} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="clean" name="% Clean" radius={[4, 4, 0, 0]}>
                  {barData.map((d, i) => (
                    <Cell key={i} fill={d.clean >= 70 ? "#10b981" : d.clean >= 40 ? "#f59e0b" : "#ef4444"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <span>📋</span>
          <span className="card-title">All Studies — Quality Overview</span>
          <span className="card-sub">{studies.length} studies</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Study</th>
                <th>Subjects</th>
                <th>Avg DQI</th>
                <th>% Clean</th>
                <th>Open Queries</th>
                <th>Missing Pages</th>
                <th>Uncoded</th>
                <th>Submission Ready</th>
              </tr>
            </thead>
            <tbody>
              {studies.map(s => (
                <tr key={s.study}>
                  <td style={{ fontFamily: "var(--mono)", fontWeight: 600 }}>{s.study}</td>
                  <td>{s.total_subjects?.toLocaleString()}</td>
                  <td><DqiBadge score={s.avg_dqi} /></td>
                  <td><Pill value={s.pct_clean?.toFixed(1)} thresholds={[70, 40]} /></td>
                  <td style={{ color: s.total_queries > 500 ? "#ef4444" : "#e2e8f0" }}>
                    {s.total_queries?.toLocaleString()}
                  </td>
                  <td style={{ color: s.total_missing_pages > 100 ? "#f59e0b" : "#e2e8f0" }}>
                    {s.total_missing_pages?.toLocaleString()}
                  </td>
                  <td style={{ color: s.total_uncoded > 50 ? "#ef4444" : "#e2e8f0" }}>
                    {s.total_uncoded?.toLocaleString()}
                  </td>
                  <td>
                    <span className={`pill ${s.submission_ready === "True" ? "pill-success" : "pill-neutral"}`}>
                      {s.submission_ready === "True" ? "✓ Ready" : "Not Ready"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}

// ── SITES PAGE ────────────────────────────────────────────────────────────────

function Sites({ studies }) {
  const [selectedStudy, setSelectedStudy] = useState("")
  const [sites, setSites] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    const url = selectedStudy
      ? `${API}/sites?study=${encodeURIComponent(selectedStudy)}`
      : `${API}/sites`
    axios.get(url)
      .then(r => setSites(r.data))
      .finally(() => setLoading(false))
  }, [selectedStudy])

  return (
    <>
      <div className="card">
        <div className="card-header">
          <span>🏥</span>
          <span className="card-title">Site Performance</span>
          <div className="filter-bar" style={{ marginLeft: "auto" }}>
            <span className="filter-label">Filter by study:</span>
            <select
              className="filter-select"
              value={selectedStudy}
              onChange={e => setSelectedStudy(e.target.value)}
            >
              <option value="">All Studies</option>
              {studies?.map(s => (
                <option key={s.study} value={s.study}>{s.study}</option>
              ))}
            </select>
          </div>
        </div>
        {loading ? <Loading /> : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Study</th>
                  <th>Country</th>
                  <th>Site</th>
                  <th>Subjects</th>
                  <th>Avg DQI</th>
                  <th>% Clean</th>
                  <th>Queries</th>
                  <th>Missing Pages</th>
                  <th>Protocol Dev.</th>
                  <th>Risk</th>
                </tr>
              </thead>
              <tbody>
                {sites?.map((s, i) => (
                  <tr key={i}>
                    <td style={{ fontFamily: "var(--mono)", fontSize: 12 }}>{s.study}</td>
                    <td>{s.country}</td>
                    <td style={{ fontFamily: "var(--mono)" }}>{s.site_id}</td>
                    <td>{s.total_subjects}</td>
                    <td><DqiBadge score={s.avg_dqi} /></td>
                    <td><Pill value={s.pct_clean_subjects?.toFixed(1)} thresholds={[70, 40]} /></td>
                    <td style={{ color: s.total_queries > 50 ? "#f59e0b" : "#e2e8f0" }}>
                      {s.total_queries}
                    </td>
                    <td>{s.total_missing_pages}</td>
                    <td style={{ color: s.total_pds > 0 ? "#ef4444" : "#e2e8f0" }}>{s.total_pds}</td>
                    <td>
                      <span className={`pill ${s.risk_flag === "True" ? "pill-danger" : "pill-success"}`}>
                        {s.risk_flag === "True" ? "⚠ At Risk" : "✓ OK"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}

// ── ALERTS PAGE ───────────────────────────────────────────────────────────────

function Alerts() {
  const [alerts, setAlerts] = useState(null)

  useEffect(() => {
    axios.get(`${API}/alerts`).then(r => setAlerts(r.data))
  }, [])

  if (!alerts) return <Loading />

  return (
    <div className="card">
      <div className="card-header">
        <span>⚠️</span>
        <span className="card-title">Sites Requiring Immediate Attention</span>
        <span className="card-sub">{alerts.length} flagged sites</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Study</th><th>Country</th><th>Site</th>
              <th>Subjects</th><th>Avg DQI</th><th>% Clean</th>
              <th>Queries</th><th>Protocol Dev.</th><th>EDRR Issues</th>
            </tr>
          </thead>
          <tbody>
            {alerts.map((a, i) => (
              <tr key={i} style={{ background: i % 2 === 0 ? "transparent" : "#0d1524" }}>
                <td style={{ fontFamily: "var(--mono)", fontSize: 12 }}>{a.study}</td>
                <td>{a.country}</td>
                <td style={{ fontFamily: "var(--mono)" }}>{a.site_id}</td>
                <td>{a.total_subjects}</td>
                <td><DqiBadge score={a.avg_dqi} /></td>
                <td><Pill value={a.pct_clean_subjects?.toFixed(1)} thresholds={[70, 40]} /></td>
                <td style={{ color: "#f59e0b" }}>{a.total_queries}</td>
                <td style={{ color: a.total_pds > 0 ? "#ef4444" : "#e2e8f0" }}>{a.total_pds}</td>
                <td style={{ color: a.open_edrr_issues > 0 ? "#ef4444" : "#e2e8f0" }}>{a.open_edrr_issues}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── AI CHAT PAGE ──────────────────────────────────────────────────────────────

const SUGGESTED = [
  "Which studies are submission-ready?",
  "Which sites have DQI below 70?",
  "Where are the most uncoded terms?",
  "Which study has the most open queries?",
  "What are the top risks across all studies?",
]

function AiChat({ summary, studies }) {
  const [messages, setMessages] = useState([
    { role: "ai", text: "Hi! I can answer questions about your clinical trial data. Try one of the suggestions below or ask anything." }
  ])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)

  const ask = useCallback(async (question) => {
    if (!question.trim() || loading) return
    setMessages(m => [...m, { role: "user", text: question }])
    setInput("")
    setLoading(true)

    // Fetch compact context fresh from API
    let context = "You are a clinical data quality analyst assistant. Answer concisely using numbers."
    try {
      const [sumRes, studyRes] = await Promise.all([
        fetch(`${API}/summary`).then(r => r.json()),
        fetch(`${API}/studies`).then(r => r.json()),
      ])
      context += `\n\nOVERALL SUMMARY: ${JSON.stringify(sumRes)}`
      context += `\n\nSTUDY METRICS: ${JSON.stringify(studyRes)}`
    } catch (e) {
      context += "\n\n(Could not load live data)"
    }

    try {
      const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${import.meta.env.VITE_GROQ_API_KEY}`,
        },
        body: JSON.stringify({
          model: "llama-3.3-70b-versatile",
          messages: [
            { role: "system", content: context },
            { role: "user", content: question }
          ],
          max_tokens: 500,
          temperature: 0.3,
        })
      })
      const data = await res.json()
      console.log("Groq response:", data)  // check browser console
      const answer = data.choices?.[0]?.message?.content || JSON.stringify(data)
      setMessages(m => [...m, { role: "ai", text: answer }])
    } catch (e) {
      setMessages(m => [...m, { role: "ai", text: `⚠️ Error: ${e.message}` }])
    } finally {
      setLoading(false)
    }
  }, [loading])

  return (
    <div className="card">
      <div className="card-header">
        <span>🤖</span>
        <span className="card-title">AI Data Quality Assistant</span>
        <span className="card-sub">powered by Claude</span>
      </div>
      <div className="card-body">
        <div className="chat-wrap">
          <div className="chat-messages">
            {messages.map((m, i) => (
              <div key={i} className={`chat-msg ${m.role}`}>{m.text}</div>
            ))}
            {loading && (
              <div className="chat-msg ai">
                <div className="spinner" style={{ width: 14, height: 14 }} />
              </div>
            )}
          </div>
          <div className="suggested-questions">
            {SUGGESTED.map(q => (
              <button key={q} className="suggested-q" onClick={() => ask(q)}>{q}</button>
            ))}
          </div>
          <div className="chat-input-row">
            <input
              className="chat-input"
              placeholder="Ask about any study, site, or metric..."
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && ask(input)}
            />
            <button className="btn" onClick={() => ask(input)} disabled={loading || !input.trim()}>
              Ask
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── NAV ───────────────────────────────────────────────────────────────────────

const PAGES = [
  { id: "overview", label: "Overview", icon: "📊" },
  { id: "sites", label: "Sites", icon: "🏥" },
  { id: "alerts", label: "Alerts", icon: "⚠️" },
  { id: "agent", label: "AI Agents", icon: "🤖" },
  { id: "ai", label: "AI Chat", icon: "💬" },
]

// ── APP ROOT ──────────────────────────────────────────────────────────────────

export default function App() {
  const [page, setPage] = useState("overview")
  const [summary, setSummary] = useState(null)
  const [studies, setStudies] = useState(null)

  useEffect(() => {
    axios.get(`${API}/summary`).then(r => setSummary(r.data))
    axios.get(`${API}/studies`).then(r => setStudies(r.data))
  }, [])

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <span className="header-logo">TrialPulse</span>
        <span className="header-sub">Clinical Data Quality Platform</span>
        <div className="header-spacer" />
        <span className="header-badge">
          ● LIVE  {summary ? `${summary.total_studies} studies · ${summary.total_subjects?.toLocaleString()} subjects` : "connecting..."}
        </span>
      </header>

      {/* Sidebar */}
      <nav className="sidebar">
        <div className="sidebar-section">Navigation</div>
        {PAGES.map(p => (
          <div
            key={p.id}
            className={`nav-item ${page === p.id ? "active" : ""}`}
            onClick={() => setPage(p.id)}
          >
            <span className="nav-icon">{p.icon}</span>
            {p.label}
          </div>
        ))}

        <div className="sidebar-section" style={{ marginTop: 16 }}>Quick Stats</div>
        {summary && (
          <>
            <div style={{ padding: "6px 20px", fontSize: 12 }}>
              <div style={{ color: "var(--text-muted)", fontSize: 11, fontFamily: "var(--mono)" }}>Overall DQI</div>
              <div style={{ color: dqiColor(summary.overall_dqi), fontWeight: 700, fontSize: 20 }}>
                {summary.overall_dqi}
              </div>
            </div>
            <div style={{ padding: "6px 20px", fontSize: 12 }}>
              <div style={{ color: "var(--text-muted)", fontSize: 11, fontFamily: "var(--mono)" }}>Open Queries</div>
              <div style={{ color: "#f59e0b", fontWeight: 600 }}>
                {summary.total_open_queries?.toLocaleString()}
              </div>
            </div>
            <div style={{ padding: "6px 20px", fontSize: 12 }}>
              <div style={{ color: "var(--text-muted)", fontSize: 11, fontFamily: "var(--mono)" }}>Ready for Submission</div>
              <div style={{ color: "#10b981", fontWeight: 600 }}>
                {summary.studies_ready} / {summary.total_studies}
              </div>
            </div>
          </>
        )}
      </nav>

      {/* Main */}
      <main className="main">
        {page === "overview" && <Overview summary={summary} studies={studies} />}
        {page === "sites" && <Sites studies={studies} />}
        {page === "alerts" && <Alerts />}
        {page === "ai" && <AiChat summary={summary} studies={studies} />}
        {page === "agent" && <AgentPage studies={studies} />}
      </main>
    </div>
  )
}