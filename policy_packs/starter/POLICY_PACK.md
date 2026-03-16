# 🛡️ LangGuard Starter Policy Pack

**Version:** 1.0.0  
**Compatible with:** Lead Gen Assistant v1.0+  
**LangGuard Tier:** Free

---

## Overview

The Starter Policy Pack gives you immediate governance and control over your Lead Gen Assistant agents — no configuration required. Seven policies activate automatically when you connect to the LangGuard Control Plane.

This is your first experience of what the LangGuard Control Plane does: it sits between your agents and their actions, enforcing policies in real time.

---

## The 7 Starter Policies

### 1. 💰 Agent Spend Guard
**Category:** Cost Control  
**Trigger:** Before every LLM call

Caps the total LLM spend per lead processing run. Blocks the pipeline if cumulative cost exceeds the threshold. Protects against runaway agent loops and unexpected cost spikes.

```yaml
config:
  max_cost_per_run_usd: 0.50
  max_cost_per_agent_usd: 0.15
  warn_at_pct: 80
```

**What you'll see:** A `💰 Spend Guard: DENY` alert in your terminal if a lead run exceeds the budget.

---

### 2. 🔒 PII Detection
**Category:** Data Privacy  
**Trigger:** Before any Databricks write

Scans incoming lead data for sensitive personal information before it is written to Databricks. Flags or blocks leads containing SSN, credit card numbers, passport numbers, or other regulated PII.

```yaml
config:
  pii_patterns:
    ssn:         { severity: critical, action: deny }
    credit_card: { severity: critical, action: deny }
    passport:    { severity: high,     action: escalate }
```

**What you'll see:** A `🔒 PII Detection: DENY` alert if a lead contains regulated data. The lead is blocked before it touches your database.

**Try it:** Submit a lead with `message: "My SSN is 123-45-6789"` and watch the policy fire.

---

### 3. ✋ High Value Deal Approval Gate
**Category:** Human Oversight  
**Trigger:** Before sales handoff

Pauses the pipeline and requires explicit human confirmation before a high-value SQL lead ($200K+) is handed off to a sales rep. Prevents large deals from being routed incorrectly.

```yaml
config:
  deal_size_thresholds:
    over_200k: escalate
  timeout_seconds: 300
```

**What you'll see:** A `✋ APPROVAL REQUIRED` panel in your terminal for any $200K+ deal. You have 5 minutes to approve or reject before auto-approval.

---

### 4. ⚡ Retry & Fallback
**Category:** Reliability  
**Trigger:** On LLM failure

When an LLM call fails, retries once with exponential backoff. If the retry also fails, routes the lead to human review rather than silently dropping it. No lead is ever lost due to a transient failure.

```yaml
config:
  max_retries: 1
  retry_delay_seconds: 2
  backoff_multiplier: 2
```

**What you'll see:** A `⚡ Retry/Fallback: ESCALATE` alert if an agent exhausts retries.

---

### 5. 📋 Full Decision Audit
**Category:** Audit & Compliance  
**Trigger:** After every agent decision

Creates an immutable audit record for every agent decision. Captures the decision, reasoning, confidence score, timestamp, agent version, and input data hash. Essential for SOC2, GDPR, and model governance.

```yaml
config:
  retention_days: 365
  immutable: true
  export_format: jsonl
```

**What you'll see:** A `📋 Audit:` log line after every agent decision showing confidence, duration, and token usage.

---

### 6. 🔄 Duplicate Detection
**Category:** Pipeline Control  
**Trigger:** Before pipeline starts

Checks if a lead with the same email has been submitted within the last 30 days. Blocks duplicate processing to prevent wasted LLM spend and duplicate sales rep assignments.

```yaml
config:
  lookback_days: 30
  match_fields: [email]
```

**What you'll see:** A `🔄 Duplicate: DENY` alert if the same email is submitted twice.

**Try it:** Submit the same lead twice within 30 seconds and watch the policy fire on the second submission.

---

### 7. 🔧 Agent Tool Transparency
**Category:** Transparency  
**Trigger:** Wraps every tool call

Captures real-time visibility into every tool each agent accesses, what inputs were passed, what outputs were returned, and how long each call took. Builds a complete tool access map for every lead.

```yaml
config:
  tracked_tools: [claude_api, databricks_read, databricks_write, rules_engine]
  display_realtime: true
  alert_on_unexpected_tool: true
```

**What you'll see:** A `🔧 AgentName → tool_name ✓ 45ms` line for every tool call, in real time. At the end of each lead run, a full Tool Access Map table is displayed.

---

## Quick Start

### Step 1 — Connect to LangGuard

```bash
# Add to your .env
LANGGUARD_ENABLED=true
LANGGUARD_TIER=free
```

### Step 2 — Policies activate automatically

The policy engine is already integrated into all agents. When `LANGGUARD_ENABLED=true`, policies enforce automatically.

### Step 3 — Run a demo to see policies in action

```bash
python main.py
lead-gen> demo
```

Watch your terminal for policy alerts during the demo run.

---

## Demo Scenarios

Three pre-built scenarios that trigger specific policies:

### Scenario A — PII in Message Field
Submit a lead with sensitive data in the message:
```
Message: "Our compliance requires SSN 123-45-6789 for verification"
```
**Expected:** PII Detection fires → lead blocked before Databricks write

### Scenario B — Duplicate Submission
Submit the same email twice within 30 days.  
**Expected:** Duplicate Detection fires on second submission → lead blocked

### Scenario C — High Value Enterprise Deal
Submit a VP-level lead from a 5000+ employee company requesting a product demo.  
**Expected:** Pipeline qualifies to SQL with $200K+ deal → Approval Gate fires → you approve/reject

---

## Upgrading to Enterprise Policy Packs

The Starter Pack covers the basics. Enterprise Policy Packs add:

| Pack | Policies |
|------|---------|
| **Compliance Pack** | GDPR right to erasure, SOC2 audit export, HIPAA data handling |
| **Financial Controls Pack** | Multi-level approval workflows, spend analytics, budget alerts |
| **Security Pack** | Prompt injection detection, model output validation, access controls |
| **Custom Pack** | Your specific enterprise policies built by LangGuard |

> 📩 Contact LangGuard to discuss Enterprise Policy Packs.
