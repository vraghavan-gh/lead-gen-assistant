# Lead Gen Assistant — Architecture Guide

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Lead Gen Assistant                           │
│                  Multi-Agent AI Pipeline                         │
└─────────────────────────────────────────────────────────────────┘

  INPUT SOURCES              AGENTS                   DATA LAYER
  ─────────────              ──────                   ──────────
  Web Forms          ──►   Triage Agent    ──►   raw_leads
  Social Media       ──►   (Claude API)    ──►   lead_events
                                │
                          accepted │ rejected
                                │
                           MQL Agent       ──►   mql_leads
                          (Claude API)     ──►   lead_events
                                │
                       qualified │ nurture
                                │
                           SQL Agent       ──►   sql_leads
                          (Claude API)     ──►   lead_events
                                │
                    sales_owned │ mql_nurture
                                │
                        Sales Handoff      ──►   sales_reps
                        + Notification
                                │
                      Analytics Agent     ──►   analytics_summary
                      (Claude API)        ──►   vw_full_funnel
                                │
                            GENIE AI
                         (Databricks)
```

---

## Agent Design Principles

### 1. Tool Use Pattern
Every agent uses Claude's `tool_use` feature to return **structured JSON responses**. This ensures:
- Deterministic output parsing
- Type-safe data models
- No string parsing fragility

```python
# Each agent defines a tool schema:
TRIAGE_TOOL = {
    "name": "triage_decision",
    "input_schema": {
        "type": "object",
        "properties": {
            "decision":   {"type": "string", "enum": ["accepted","rejected","needs_review"]},
            "confidence": {"type": "number"},
            ...
        }
    }
}

# Claude is forced to use the tool — structured output guaranteed
response = self.call_claude(
    system_prompt = TRIAGE_SYSTEM_PROMPT,
    user_message  = lead_data_as_json,
    tools         = [TRIAGE_TOOL],
)
result = response["tool_use"]["input"]  # Always a dict
```

### 2. Immutable Audit Trail
Every state change is logged to `lead_events` — an append-only Delta table:

```
lead_captured → triage_started → triage_completed →
mql_scoring_started → mql_qualified → sql_scoring_started →
sql_qualified → sales_assigned → handoff_confirmed
```

### 3. Configuration-Driven Scoring
All scoring thresholds live in `config/scoring_config.yaml`:
- Enterprises customize without touching agent code
- Different verticals can use different scoring profiles
- A/B testing scoring changes is trivial

### 4. Graceful Degradation
- If Claude doesn't return `tool_use`, agents fall back to `needs_review`
- If Databricks is unavailable, agents log locally
- Pipeline stages are independent — a failure in SQL doesn't lose MQL data

---

## Databricks Unity Catalog Design

### Why Unity Catalog?
- Required for Genie AI analytics
- Column-level access controls for PII
- Full lineage tracking across pipeline stages
- Delta Change Data Feed for streaming consumers

### Star Schema for Genie
```
         ┌──────────────┐
         │  raw_leads   │  ← Fact table (all events start here)
         │  (fact)      │
         └──────┬───────┘
                │
    ┌───────────┼───────────┐
    │           │           │
┌───▼───┐  ┌───▼───┐  ┌────▼────┐
│  mql  │  │  sql  │  │ events  │
│ leads │  │ leads │  │ (audit) │
└───────┘  └───────┘  └─────────┘
                │
         ┌──────▼──────┐
         │  sales_reps │
         │   (dim)     │
         └─────────────┘
```

### Genie Optimization Checklist
- ✅ `COMMENT ON TABLE` — rich natural language descriptions
- ✅ `COMMENT ON COLUMN` — every column described for AI context
- ✅ Delta format — required for Genie
- ✅ `TBLPROPERTIES 'lead_gen.genie_enabled' = 'true'`
- ✅ Denormalized view `vw_full_funnel` — single table for most Genie queries
- ✅ `analytics_summary` — pre-aggregated for fast metric queries
- ✅ Proper foreign keys — Genie understands relationships

---

## MQL Scoring Model

| Dimension | Weight | Signals |
|-----------|--------|---------|
| Job Title / Seniority | 20pts | VP+, Director = max |
| Company Size | 15pts | Enterprise 1000+ = max |
| Industry Fit | 10pts | Tech/FinServ/Healthcare = max |
| Form Type Intent | 20pts | Demo Request = max |
| Email Domain | 10pts | Business email = max |
| Message Intent | 15pts | Pricing/urgent/budget keywords |
| Data Completeness | 10pts | All required fields filled |
| **Total** | **100pts** | **Threshold: 50** |

## SQL / BANT Scoring Model

| BANT Dimension | Weight | Signals |
|----------------|--------|---------|
| Budget | 25pts | Explicit mention, procurement signals |
| Authority | 25pts | C-Suite / VP / Director |
| Need | 25pts | Pain points, active evaluation |
| Timeline | 25pts | <30 days = max |
| **Total** | **100pts** | **Threshold: 70** |

---

## Enterprise Customization Guide

### Adding a CRM Integration (Salesforce example)
In `agents/sql_agent.py`, replace the `_notify_sales_rep()` stub:

```python
def _notify_sales_rep(self, sql_result, raw_lead):
    import requests
    
    # Create Salesforce Lead
    sf_payload = {
        "FirstName":  raw_lead["first_name"],
        "LastName":   raw_lead["last_name"],
        "Email":      raw_lead["email"],
        "Company":    raw_lead["company"],
        "OwnerId":    sql_result.assigned_rep_id,
        "Lead_Score__c": sql_result.sql_score,
    }
    requests.post(
        f"{os.getenv('SF_INSTANCE_URL')}/services/data/v58.0/sobjects/Lead/",
        headers={"Authorization": f"Bearer {os.getenv('SF_ACCESS_TOKEN')}"},
        json=sf_payload,
    )
```

### Adding Slack Notifications
```python
def _notify_sales_rep(self, sql_result, raw_lead):
    import requests
    requests.post(os.getenv("SLACK_WEBHOOK_URL"), json={
        "text": f"🎯 New SQL for {sql_result.assigned_rep_name}",
        "blocks": [{
            "type": "section",
            "text": {"type": "mrkdwn", "text": 
                f"*{raw_lead['first_name']} {raw_lead['last_name']}* @ *{raw_lead['company']}*\n"
                f"BANT: {sql_result.sql_score}/100 | Deal: {sql_result.estimated_deal_size}\n"
                f"Next: {sql_result.next_step}"
            }
        }]
    })
```

### Changing Scoring Thresholds
Simply edit `config/scoring_config.yaml`:
```yaml
mql:
  threshold: 60  # Raise the bar (was 50)
sql:
  threshold: 75  # More selective SQL (was 70)
```

---

## Security Notes

- PAT tokens must be in `.env` — never hardcoded
- `.env` and `pat_token` are in `.gitignore`
- PII columns tagged `data_classification: confidential_pii`
- Unity Catalog column masking can be added for GDPR compliance
- Agent reasoning logs may contain PII — review retention policies

---

## Roadmap

- [ ] Real-time lead ingestion via Databricks Structured Streaming
- [ ] Lead deduplication agent
- [ ] A/B testing framework for scoring configs
- [ ] Salesforce / HubSpot native connectors
- [ ] Slack bot interface
- [ ] Email nurture sequence trigger
- [ ] Looker / Tableau dashboard templates
