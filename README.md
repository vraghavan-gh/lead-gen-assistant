# 🎯 Lead Gen Assistant — Enterprise Multi-Agent Pipeline

> **A production-ready AI cookbook for converting raw leads into Sales Qualified Leads using Claude + Databricks**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org)
[![Anthropic Claude](https://img.shields.io/badge/AI-Claude%20Sonnet-orange.svg)](https://anthropic.com)
[![Databricks](https://img.shields.io/badge/Data-Databricks-red.svg)](https://databricks.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📋 Overview

The Lead Gen Assistant is an enterprise-grade **multi-agent AI pipeline** that automates the lead qualification lifecycle from raw inbound lead to a Sales-owned opportunity. Built as a **sellable cookbook** that enterprises can purchase, customize, and deploy on their own infrastructure.

**Pipeline Flow:**
```
Web Form / Social
      │
      ▼
┌─────────────────┐
│  Triage Agent   │──► Rejected (spam, invalid)
│                 │
│  • Validates    │
│  • Detects spam │
│  • Routes leads │
└────────┬────────┘
         │ Accepted
         ▼
┌─────────────────┐
│   MQL Agent     │──► Nurture Track (score < threshold)
│                 │
│  • Enriches     │
│  • Scores 0-100 │
│  • Persona fit  │
└────────┬────────┘
         │ MQL Qualified
         ▼
┌─────────────────┐
│   SQL Agent     │──► Returned to Nurture (BANT < threshold)
│                 │
│  • BANT scoring │
│  • Deal sizing  │
│  • Rep routing  │
└────────┬────────┘
         │ SQL Qualified
         ▼
┌─────────────────┐
│  Sales Handoff  │
│  + Analytics    │
│    Agent        │
└─────────────────┘
```

---

## 🏗️ Architecture

### Agents

| Agent | Responsibility | Input | Output |
|-------|---------------|-------|--------|
| **Triage Agent** | Validate, accept, or reject raw leads | `RawLeadInput` | `TriageResult` |
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
    └── vw_full_funnel      ← Genie-optimized view
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Databricks workspace with Unity Catalog
- Anthropic API key
- Databricks Personal Access Token (PAT)

### Installation

```bash
# Clone the repo
git clone https://github.com/YOUR_ORG/lead-gen-assistant.git
cd lead-gen-assistant

# Create virtual environment
python -m venv venv
source venv/bin/activate  # zsh/bash

# Install dependencies
pip install -r requirements.txt
```

### Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your credentials
nano .env
```

Required environment variables:

```env
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=your_pat_token
DATABRICKS_WORKSPACE_ID=your_workspace_id
DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/your_warehouse_id
ANTHROPIC_API_KEY=your_anthropic_api_key
```

### Initialize Databricks Schema

**Option A — Databricks Notebook (Recommended):**
1. Upload `notebooks/01_setup_databricks_schema.py` to your workspace
2. Run all cells

**Option B — CLI:**
```bash
python main.py
lead-gen> setup
```

### Run the Assistant

```bash
python main.py
```

```
╔══════════════════════════════════════════════════════════╗
║         🎯  LEAD GEN ASSISTANT  v1.0.0                  ║
║         Multi-Agent Sales Pipeline                       ║
║         Powered by Claude + Databricks                   ║
╚══════════════════════════════════════════════════════════╝

lead-gen> demo        # Run sample leads through pipeline
lead-gen> submit      # Submit a new lead interactively
lead-gen> report      # Funnel analytics report
lead-gen> status      # Check a specific lead's journey
lead-gen> help        # Show all commands
```

---

## 📊 Genie Integration

All tables are tagged with `'lead_gen.genie_enabled' = 'true'` and include rich column-level metadata.

**Starter Genie Prompts:**
- *"What is my MQL conversion rate this month?"*
- *"Show me leads by source channel in the last 30 days"*
- *"Which sales rep has the most SQLs?"*
- *"What is the average time from lead capture to MQL?"*
- *"Show me the full funnel breakdown by industry"*
- *"What is the estimated pipeline value this quarter?"*

See `notebooks/02_genie_analytics.py` for pre-built analytics queries.

---

## ⚙️ Configuration

All scoring thresholds are in `config/scoring_config.yaml` — no code changes needed:

```yaml
mql:
  threshold: 50          # Points needed to qualify as MQL

  scoring_rules:
    job_title:
      qualifying_titles:
        - CTO
        - VP Engineering
        # Add your titles...

sql:
  threshold: 70          # Points needed for SQL (BANT)
```

---

## 🔌 Enterprise Customization

| Customization | How |
|--------------|-----|
| Scoring thresholds | Edit `config/scoring_config.yaml` |
| CRM integration | Add webhook in `agents/sql_agent.py → _notify_sales_rep()` |
| Slack notifications | Add Slack SDK call in handoff method |
| Email enrichment | Replace enrichment stub in `mql_agent.py` |
| Custom personas | Add to scoring config `persona_rules` |
| Industry verticals | Add to `high_value_industries` list |

---

## 🧪 Testing

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=agents --cov=utils
```

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
│   ├── base_agent.py               # Base class (Claude API + DB client)
│   ├── triage_agent.py             # Stage 1: Accept/Reject
│   ├── mql_agent.py                # Stage 2: MQL Scoring
│   ├── sql_agent.py                # Stage 3: BANT + Sales Assignment
│   └── analytics_agent.py          # Reporting + AI Insights
│
├── utils/
│   ├── models.py                   # Pydantic data models
│   └── databricks_client.py        # Databricks SQL wrapper
│
├── schema/
│   └── databricks_schema.sql       # Full DDL with metadata
│
├── config/
│   └── scoring_config.yaml         # Tunable scoring rules
│
├── notebooks/
│   ├── 01_setup_databricks_schema.py
│   └── 02_genie_analytics.py
│
├── tests/
│   └── test_pipeline.py
│
└── docs/
    └── architecture.md
```

---

## 📖 Cookbook Usage

This repository is designed as an **enterprise cookbook**. To customize for your organization:

1. **Fork** this repository
2. Update `config/scoring_config.yaml` with your qualification criteria
3. Add your CRM integration in `agents/sql_agent.py`
4. Configure your Databricks workspace in `.env`
5. Run `setup` to initialize Unity Catalog tables
6. Test with `demo` mode before going live

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 📄 License

MIT License — see [LICENSE](LICENSE)

---

## 🏢 Built With

- [Anthropic Claude](https://anthropic.com) — AI agent intelligence
- [Databricks](https://databricks.com) — Data platform + Unity Catalog + Genie
- [Pydantic](https://pydantic.dev) — Data validation
- [Rich](https://rich.readthedocs.io) — Terminal UI
- [Python 3.11+](https://python.org)
