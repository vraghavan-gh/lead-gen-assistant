# 🎯 Lead Gen Assistant — Enterprise Multi-Agent Pipeline

> **A production-ready AI cookbook for converting raw leads into Sales Qualified Leads using Python + Databricks**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org)
[![Anthropic Claude](https://img.shields.io/badge/AI-Claude%20Sonnet-orange.svg)](https://anthropic.com)
[![OpenAI](https://img.shields.io/badge/AI-OpenAI%20GPT4o-green.svg)](https://openai.com)
[![Gemini](https://img.shields.io/badge/AI-Google%20Gemini-blue.svg)](https://deepmind.google)
[![Databricks](https://img.shields.io/badge/Data-Databricks-red.svg)](https://databricks.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📋 Overview

The Lead Gen Assistant is an enterprise-grade **multi-agent AI pipeline** that automates the lead qualification lifecycle — from a raw web form submission all the way to a Sales-owned opportunity.

Built as a **sellable cookbook** that enterprises can purchase, customize, and deploy on their own infrastructure. Works with **Anthropic Claude, OpenAI GPT-4o, or Google Gemini** — bring your own LLM key.

---

## 🤖 Multi-Agent Pipeline

```
Web Form Submission
        │
        ▼
┌──────────────────┐
│ Web Form Agent   │──► Auto-rejected (bot/spam score > 90)
│                  │
│ • Enriches data  │
│ • Detects bots   │
│ • Human review   │◄── YOU approve or reject here (60s timeout)
│ • Auto-accepts   │
└────────┬─────────┘
         │ Accepted
         ▼
┌──────────────────┐
│  Triage Agent    │──► Rejected (invalid, spam, incomplete)
│                  │
│ • Validates lead │
│ • Routes to MQL  │
└────────┬─────────┘
         │ Accepted
         ▼
┌──────────────────┐
│   MQL Agent      │──► Nurture Track (score < threshold)
│                  │
│ • Scores 0-100   │
│ • Enriches data  │
│ • Classifies     │
│   persona        │
└────────┬─────────┘
         │ MQL Qualified
         ▼
┌──────────────────┐
│   SQL Agent      │──► Returns to Nurture (BANT < threshold)
│                  │
│ • BANT scoring   │
│ • Deal sizing    │
│ • Assigns rep    │
└────────┬─────────┘
         │ SQL Qualified
         ▼
┌──────────────────┐
│ Sales Handoff    │
│ + Analytics      │
│   Agent          │
└──────────────────┘
```

---

## 🏗️ Architecture

### Agents

| Agent | Responsibility | Input | Output |
|-------|---------------|-------|--------|
| **Web Form Agent** | Enrich, detect bots, human-in-the-loop review | Raw form POST | `RawLeadInput` or rejected |
| **Triage Agent** | Validate and route accepted leads | `RawLeadInput` | `TriageResult` |
| **MQL Agent** | Score and enrich accepted leads (0-100) | `lead_id` | `MQLResult` |
| **SQL Agent** | BANT qualify and assign to sales rep | `mql_id` | `SQLResult` |
| **Analytics Agent** | Funnel reporting and AI insights | `days` or `lead_id` | Metrics + Insights |

### Databricks Data Model (Unity Catalog)

```
lead_gen (catalog)
└── sales_pipeline (schema)
    ├── raw_leads           ← All inbound leads
    ├── mql_leads           ← Marketing Qualified Leads
    ├── sql_leads           ← Sales Qualified Leads
    ├── lead_events         ← Immutable audit trail
    ├── analytics_summary   ← Pre-aggregated metrics
    ├── sales_reps          ← Rep roster for routing
    └── vw_full_funnel      ← Denormalized analytics view
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Databricks workspace with Unity Catalog
- API key for one of: Anthropic, OpenAI, or Google Gemini
- Databricks Personal Access Token (PAT)

### Installation

```bash
# Clone the repo
git clone https://github.com/vraghavan-gh/lead-gen-assistant.git
cd lead-gen-assistant

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# Databricks
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=your_pat_token
DATABRICKS_WORKSPACE_ID=your_workspace_id
DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/your_warehouse_id

# LLM Provider — choose one: anthropic | openai | gemini
LLM_PROVIDER=anthropic
LLM_API_KEY=your_api_key_here
```

### Initialize Databricks Schema

1. Upload `notebooks/01_setup_databricks_schema.py` to your Databricks workspace
2. Run all 11 cells top to bottom
3. Verify: Cell 11 should show `✅ Total objects: 7`

### Run the CLI

```bash
python main.py
lead-gen> demo    # Process sample leads
lead-gen> submit  # Submit a lead interactively
lead-gen> report  # Funnel analytics
lead-gen> status  # Check a specific lead
```

### Run the Web Form

```bash
python web/app.py
```

- **Form:** `http://127.0.0.1:8080`
- **Dashboard:** `http://127.0.0.1:8080/dashboard`

Submit a lead from the form. The Web Form Agent will display it in your terminal for review before the pipeline runs.

---

## 🔑 LLM Provider Configuration

The pipeline is **LLM-agnostic**. Set two variables in `.env` to switch providers:

### Anthropic Claude (default)

```env
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-...
```

Get your key: [console.anthropic.com](https://console.anthropic.com) → API Keys

Default model: `claude-sonnet-4-20250514`

---

### OpenAI GPT-4o

```env
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
```

Get your key: [platform.openai.com](https://platform.openai.com) → API Keys

Default model: `gpt-4o`

---

### Google Gemini

```env
LLM_PROVIDER=gemini
LLM_API_KEY=AIza...
```

Get your key: [aistudio.google.com](https://aistudio.google.com) → Get API Key

Default model: `gemini-1.5-pro`

---

### Override the Default Model

```env
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-...
LLM_MODEL=claude-haiku-4-5-20251001   # Use a faster/cheaper model
```

---

## ⚙️ Configuration Files

All rules and thresholds are in config files — no code changes needed.

### `config/scoring_config.yaml` — MQL and SQL scoring

```yaml
mql:
  threshold: 50          # Points needed to qualify as MQL

sql:
  threshold: 70          # Points needed for SQL (BANT)
```

### `config/web_form_rules.yaml` — Bot detection and form validation

```yaml
sensitivity: medium      # low | medium | high

bot_risk_thresholds:
  low:      { max: 30,  action: auto_accept }
  medium:   { max: 55,  action: prompt }
  high:     { max: 75,  action: prompt }
  critical: { max: 100, action: auto_reject }

auto_rules:
  auto_reject_above_bot_risk: 90
  auto_accept_above_quality: 80
  human_review_timeout_seconds: 60
```

---

## 🔌 Enterprise Customization

| Customization | Where |
|--------------|-------|
| Switch LLM provider | `.env` — change `LLM_PROVIDER` and `LLM_API_KEY` |
| MQL/SQL thresholds | `config/scoring_config.yaml` |
| Bot detection rules | `config/web_form_rules.yaml` |
| CRM integration | `agents/sql_agent.py → _notify_sales_rep()` |
| Slack notifications | Add Slack SDK call in handoff method |
| Sales rep roster | Update `sales_reps` table in Databricks |
| Web form fields | `web/templates/index.html` |

---

## 📁 Project Structure

```
lead_gen_assistant/
├── main.py                          # Interactive CLI entry point
├── pipeline.py                      # Pipeline orchestrator
├── requirements.txt
├── .env.example
│
├── agents/
│   ├── base_agent.py               # Base class — pluggable LLM client
│   ├── web_form_agent.py           # Stage 0: Bot detection + human review
│   ├── triage_agent.py             # Stage 1: Accept/Reject
│   ├── mql_agent.py                # Stage 2: MQL Scoring
│   ├── sql_agent.py                # Stage 3: BANT + Sales Assignment
│   └── analytics_agent.py          # Reporting + AI Insights
│
├── utils/
│   ├── llm_client.py               # Pluggable LLM — Anthropic/OpenAI/Gemini
│   ├── models.py                   # Pydantic data models
│   └── databricks_client.py        # Databricks SQL wrapper
│
├── web/
│   ├── app.py                      # Flask server + webhook
│   └── templates/
│       ├── index.html              # Lead capture web form
│       └── dashboard.html          # Live pipeline dashboard
│
├── schema/
│   └── databricks_schema.sql       # Full DDL with metadata
│
├── config/
│   ├── scoring_config.yaml         # MQL/SQL scoring rules
│   └── web_form_rules.yaml         # Bot detection rules
│
├── notebooks/
│   └── 01_setup_databricks_schema.py  # Databricks setup (run this first)
│
├── tests/
│   └── test_pipeline.py
│
└── docs/
    └── architecture.md
```

---

## 🧪 Testing

```bash
# Run all tests (no API calls — zero cost)
pytest tests/

# Run with coverage
pytest tests/ --cov=agents --cov=utils
```

---

## 📖 How to Use This Cookbook

1. **Fork** this repository
2. Set your LLM provider in `.env`
3. Run the Databricks setup notebook
4. Start the web server: `python web/app.py`
5. Submit leads via the form — review them in your terminal
6. Customize scoring thresholds in `config/` files
7. Add your CRM/Slack integration in `agents/sql_agent.py`

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 📄 License

MIT License — see [LICENSE](LICENSE)

---

## 🏢 Built With

- [Anthropic Claude](https://anthropic.com) — AI agent intelligence
- [OpenAI](https://openai.com) — GPT-4o support
- [Google Gemini](https://deepmind.google) — Gemini support
- [Databricks](https://databricks.com) — Data platform + Unity Catalog
- [Flask](https://flask.palletsprojects.com) — Web server
- [Pydantic](https://pydantic.dev) — Data validation
- [Rich](https://rich.readthedocs.io) — Terminal UI
- [Python 3.11+](https://python.org)
