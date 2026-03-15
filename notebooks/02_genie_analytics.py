# Databricks notebook source
# MAGIC %md
# MAGIC # Lead Gen Assistant — Genie Analytics Notebook
# MAGIC
# MAGIC This notebook demonstrates the Genie-ready analytics queries for the Lead Gen pipeline.
# MAGIC Use these as starter queries in your Genie space, or run them directly.

# COMMAND ----------
# MAGIC %md
# MAGIC ## Starter Genie Prompts
# MAGIC 
# MAGIC Copy these into your Genie space to get instant AI-powered analytics:
# MAGIC 
# MAGIC - *"What is my MQL conversion rate this month?"*
# MAGIC - *"Show me leads by source channel in the last 30 days"*
# MAGIC - *"Which sales rep has the most SQLs assigned?"*
# MAGIC - *"What is the average time from lead capture to MQL?"*
# MAGIC - *"Show me the full funnel breakdown by industry"*
# MAGIC - *"Which leads are stuck in the pipeline for more than 7 days?"*
# MAGIC - *"What is the estimated pipeline value by sales team?"*

# COMMAND ----------
# MAGIC %md
# MAGIC ## 1. Funnel Overview

# COMMAND ----------

# DBTITLE 1,Full Funnel Summary
# %sql
spark.sql("""
SELECT
  COUNT(*)                                          AS total_leads,
  COUNT(CASE WHEN status = 'accepted'      THEN 1 END) AS accepted,
  COUNT(CASE WHEN status = 'rejected'      THEN 1 END) AS rejected,
  COUNT(CASE WHEN status = 'mql'           THEN 1 END) AS mql,
  COUNT(CASE WHEN status = 'sql'           THEN 1 END) AS sql_leads,
  COUNT(CASE WHEN status = 'sales_owned'   THEN 1 END) AS sales_owned,
  ROUND(COUNT(CASE WHEN status IN ('mql','sql','sales_owned') THEN 1 END) * 100.0 / NULLIF(COUNT(CASE WHEN status = 'accepted' THEN 1 END),0), 1) AS mql_rate_pct,
  ROUND(COUNT(CASE WHEN status IN ('sql','sales_owned') THEN 1 END) * 100.0 / NULLIF(COUNT(CASE WHEN status = 'mql' THEN 1 END),0), 1) AS sql_rate_pct
FROM lead_gen.sales_pipeline.raw_leads
WHERE created_at >= DATEADD(DAY, -30, CURRENT_TIMESTAMP())
""").show()

# COMMAND ----------
# MAGIC %md
# MAGIC ## 2. Leads by Source Channel

# COMMAND ----------

# DBTITLE 1,Lead Volume by Channel
spark.sql("""
SELECT
  source_channel,
  COUNT(*)                                                AS total,
  COUNT(CASE WHEN status NOT IN ('rejected','new') THEN 1 END) AS accepted,
  COUNT(CASE WHEN status IN ('mql','sql','sales_owned')  THEN 1 END) AS qualified,
  ROUND(COUNT(CASE WHEN status IN ('mql','sql','sales_owned') THEN 1 END) * 100.0 / COUNT(*), 1) AS qual_rate_pct
FROM lead_gen.sales_pipeline.raw_leads
WHERE created_at >= DATEADD(DAY, -30, CURRENT_TIMESTAMP())
GROUP BY source_channel
ORDER BY total DESC
""").show()

# COMMAND ----------
# MAGIC %md
# MAGIC ## 3. MQL Analysis

# COMMAND ----------

# DBTITLE 1,MQL by Persona and Buying Stage
spark.sql("""
SELECT
  persona,
  buying_stage,
  COUNT(*)             AS total_mqls,
  AVG(mql_score)       AS avg_score,
  AVG(confidence_score) AS avg_confidence
FROM lead_gen.sales_pipeline.mql_leads
WHERE created_at >= DATEADD(DAY, -30, CURRENT_TIMESTAMP())
GROUP BY persona, buying_stage
ORDER BY total_mqls DESC
""").show()

# COMMAND ----------
# MAGIC %md
# MAGIC ## 4. SQL / BANT Analysis

# COMMAND ----------

# DBTITLE 1,BANT Score Breakdown
spark.sql("""
SELECT
  assigned_team,
  COUNT(*)                      AS total_sqls,
  AVG(sql_score)                AS avg_bant_score,
  AVG(bant_score_budget)        AS avg_budget,
  AVG(bant_score_authority)     AS avg_authority,
  AVG(bant_score_need)          AS avg_need,
  AVG(bant_score_timeline)      AS avg_timeline,
  COUNT(CASE WHEN estimated_deal_size = '$200K+' THEN 1 END) AS enterprise_deals
FROM lead_gen.sales_pipeline.sql_leads
WHERE created_at >= DATEADD(DAY, -30, CURRENT_TIMESTAMP())
GROUP BY assigned_team
ORDER BY avg_bant_score DESC
""").show()

# COMMAND ----------
# MAGIC %md
# MAGIC ## 5. Pipeline Velocity

# COMMAND ----------

# DBTITLE 1,Time to Qualify (Hours)
spark.sql("""
SELECT
  r.source_channel,
  COUNT(*)                                AS leads,
  ROUND(AVG(DATEDIFF(HOUR, r.created_at, m.qualified_at)), 1)  AS avg_hrs_to_mql,
  ROUND(AVG(DATEDIFF(HOUR, m.qualified_at, s.qualified_at)), 1) AS avg_hrs_to_sql,
  ROUND(AVG(DATEDIFF(HOUR, r.created_at, s.qualified_at)), 1)  AS avg_total_hrs
FROM lead_gen.sales_pipeline.raw_leads r
JOIN lead_gen.sales_pipeline.mql_leads m ON r.lead_id = m.lead_id
JOIN lead_gen.sales_pipeline.sql_leads s ON m.mql_id  = s.mql_id
WHERE r.created_at >= DATEADD(DAY, -30, CURRENT_TIMESTAMP())
GROUP BY r.source_channel
ORDER BY avg_total_hrs ASC
""").show()

# COMMAND ----------
# MAGIC %md
# MAGIC ## 6. Sales Rep Performance

# COMMAND ----------

# DBTITLE 1,Rep Workload and Pipeline
spark.sql("""
SELECT
  s.assigned_rep_name,
  s.assigned_team,
  COUNT(*)                       AS total_sqls,
  SUM(CASE WHEN s.status = 'closed_won' THEN 1 ELSE 0 END) AS closed_won,
  AVG(s.sql_score)               AS avg_bant_score,
  COUNT(CASE WHEN s.estimated_deal_size = '$200K+' THEN 1 END) AS enterprise_deals,
  COUNT(CASE WHEN s.handoff_confirmed = true THEN 1 END) AS confirmed_handoffs
FROM lead_gen.sales_pipeline.sql_leads s
WHERE s.created_at >= DATEADD(DAY, -30, CURRENT_TIMESTAMP())
GROUP BY s.assigned_rep_name, s.assigned_team
ORDER BY total_sqls DESC
""").show()

# COMMAND ----------
# MAGIC %md
# MAGIC ## 7. Full Funnel View (for Genie)

# COMMAND ----------

# DBTITLE 1,Full Funnel Denormalized View
spark.sql("""
SELECT *
FROM lead_gen.sales_pipeline.vw_full_funnel
WHERE captured_at >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
ORDER BY captured_at DESC
LIMIT 20
""").show(truncate=False)

# COMMAND ----------
# MAGIC %md
# MAGIC ## 8. Audit Trail for a Specific Lead

# COMMAND ----------

# DBTITLE 1,Lead Journey (replace lead_id)
LEAD_ID = "LD-20250314-XXXXXXXX"  # Replace with actual lead ID

spark.sql(f"""
SELECT
  event_timestamp,
  event_type,
  agent_name,
  from_status,
  to_status,
  score_at_event,
  duration_seconds
FROM lead_gen.sales_pipeline.lead_events
WHERE lead_id = '{LEAD_ID}'
ORDER BY event_timestamp ASC
""").show(truncate=False)
