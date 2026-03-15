# Databricks notebook source
# MAGIC %md
# MAGIC # Lead Gen Assistant — Clean Setup (v2)
# MAGIC Run cells top to bottom. Every cell is self-contained and tested.

# COMMAND ----------
# MAGIC %md
# MAGIC ## Cell 1 — Drop Everything and Start Clean

# COMMAND ----------

spark.sql("DROP VIEW  IF EXISTS lead_gen.sales_pipeline.vw_full_funnel")
spark.sql("DROP TABLE IF EXISTS lead_gen.sales_pipeline.sql_leads")
spark.sql("DROP TABLE IF EXISTS lead_gen.sales_pipeline.mql_leads")
spark.sql("DROP TABLE IF EXISTS lead_gen.sales_pipeline.lead_events")
spark.sql("DROP TABLE IF EXISTS lead_gen.sales_pipeline.analytics_summary")
spark.sql("DROP TABLE IF EXISTS lead_gen.sales_pipeline.sales_reps")
spark.sql("DROP TABLE IF EXISTS lead_gen.sales_pipeline.raw_leads")
spark.sql("DROP SCHEMA IF EXISTS lead_gen.sales_pipeline")
spark.sql("DROP CATALOG IF EXISTS lead_gen CASCADE")
print("✅ Clean slate")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Cell 2 — Create Catalog and Schema

# COMMAND ----------

spark.sql("""
    CREATE CATALOG IF NOT EXISTS lead_gen
    COMMENT 'Lead Generation Assistant - Enterprise Sales Pipeline'
""")

spark.sql("""
    CREATE SCHEMA IF NOT EXISTS lead_gen.sales_pipeline
    COMMENT 'Core sales pipeline. Tracks leads from raw capture through MQL, SQL and Sales Owned.'
""")

print("✅ Catalog: lead_gen")
print("✅ Schema:  lead_gen.sales_pipeline")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Cell 3 — Create raw_leads

# COMMAND ----------

spark.sql("""
CREATE TABLE lead_gen.sales_pipeline.raw_leads (
  lead_id          STRING    NOT NULL COMMENT 'Unique lead ID. Format: LD-YYYYMMDD-UUID8.',
  created_at       TIMESTAMP NOT NULL COMMENT 'UTC timestamp when lead was captured.',
  updated_at       TIMESTAMP          COMMENT 'UTC timestamp of last update.',
  source_channel   STRING    NOT NULL COMMENT 'Acquisition channel: web_form | linkedin | twitter | facebook | email_campaign | paid_search | organic_search | referral | event.',
  source_campaign  STRING             COMMENT 'Marketing campaign identifier.',
  source_url       STRING             COMMENT 'URL where lead was captured.',
  form_type        STRING             COMMENT 'Form type: demo_request | contact_us | whitepaper_download | newsletter_signup | webinar_registration | free_trial.',
  utm_source       STRING             COMMENT 'UTM source parameter.',
  utm_medium       STRING             COMMENT 'UTM medium parameter.',
  utm_campaign     STRING             COMMENT 'UTM campaign name.',
  first_name       STRING             COMMENT 'Lead first name.',
  last_name        STRING             COMMENT 'Lead last name.',
  email            STRING    NOT NULL COMMENT 'Lead email address. Primary contact identifier.',
  phone            STRING             COMMENT 'Lead phone number.',
  linkedin_url     STRING             COMMENT 'LinkedIn profile URL.',
  company          STRING             COMMENT 'Company name.',
  job_title        STRING             COMMENT 'Job title. Used for authority scoring.',
  department       STRING             COMMENT 'Business department.',
  company_size     STRING             COMMENT 'Employee range: 1-10 | 11-50 | 51-200 | 201-1000 | 1001-5000 | 5000+.',
  industry         STRING             COMMENT 'Industry vertical.',
  country          STRING             COMMENT 'Country code ISO 3166-1 alpha-2.',
  state_region     STRING             COMMENT 'State or region.',
  message          STRING             COMMENT 'Free-text message from lead.',
  interests        ARRAY<STRING>      COMMENT 'Product areas of interest.',
  opt_in_marketing BOOLEAN            COMMENT 'Marketing opt-in flag.',
  status           STRING    NOT NULL COMMENT 'Pipeline status: new | processing | accepted | rejected | mql | sql | sales_owned.',
  rejection_reason STRING             COMMENT 'Rejection reason: invalid_email | spam | duplicate | incomplete_data.',
  raw_payload      STRING             COMMENT 'Original JSON payload from source.'
)
USING DELTA
COMMENT 'Master table of all inbound leads. Every pipeline journey starts here. Genie: query for lead volume, source mix, geographic distribution.'
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'lead_gen.owner'             = 'marketing_ops',
  'lead_gen.genie_enabled'     = 'true'
)
""")
print("✅ Table created: raw_leads")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Cell 4 — Create mql_leads

# COMMAND ----------

spark.sql("""
CREATE TABLE lead_gen.sales_pipeline.mql_leads (
  mql_id             STRING    NOT NULL COMMENT 'Unique MQL ID. Format: MQL-YYYYMMDD-UUID8.',
  lead_id            STRING    NOT NULL COMMENT 'FK to raw_leads.lead_id.',
  created_at         TIMESTAMP NOT NULL COMMENT 'UTC timestamp when lead was promoted to MQL.',
  updated_at         TIMESTAMP          COMMENT 'UTC timestamp of last update.',
  qualified_at       TIMESTAMP          COMMENT 'UTC timestamp MQL qualification was confirmed.',
  mql_score          INTEGER            COMMENT 'Total MQL score 0-100. Threshold set in scoring_config.yaml.',
  score_breakdown    STRING             COMMENT 'JSON: score per dimension: job_title, company_size, industry, form_type, email_domain, message_intent, completeness.',
  enriched_company   STRING             COMMENT 'Verified company name after enrichment.',
  enriched_industry  STRING             COMMENT 'Verified industry after enrichment.',
  enriched_employees INTEGER            COMMENT 'Verified employee headcount.',
  enriched_revenue   STRING             COMMENT 'Estimated annual revenue range.',
  enriched_website   STRING             COMMENT 'Company website URL.',
  company_linkedin   STRING             COMMENT 'Company LinkedIn URL.',
  technologies_used  ARRAY<STRING>      COMMENT 'Tech stack identified for company.',
  persona            STRING             COMMENT 'Buyer persona: Technical_Buyer | Economic_Buyer | End_User | Champion.',
  buying_stage       STRING             COMMENT 'Stage: awareness | consideration | decision.',
  product_interest   ARRAY<STRING>      COMMENT 'Products lead expressed interest in.',
  pain_points        ARRAY<STRING>      COMMENT 'Pain points extracted from lead data.',
  agent_version      STRING             COMMENT 'MQL agent version that processed this record.',
  agent_reasoning    STRING             COMMENT 'Claude MQL agent reasoning for this decision.',
  confidence_score   FLOAT              COMMENT 'Agent confidence 0.0-1.0.',
  human_reviewed     BOOLEAN            COMMENT 'Whether a human analyst reviewed this MQL.',
  reviewer_id        STRING             COMMENT 'Employee ID of human reviewer.',
  status             STRING    NOT NULL COMMENT 'MQL status: mql_new | mql_nurturing | mql_accepted | mql_rejected | promoted_to_sql.',
  nurture_track      STRING             COMMENT 'Nurture track: enterprise_track | smb_track | technical_track | general_track.'
)
USING DELTA
COMMENT 'Marketing Qualified Leads. Leads that passed MQL scoring threshold. Genie: analyze MQL conversion by persona, industry, buying stage.'
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'lead_gen.owner'             = 'marketing_ops',
  'lead_gen.genie_enabled'     = 'true'
)
""")
print("✅ Table created: mql_leads")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Cell 5 — Create sql_leads

# COMMAND ----------

spark.sql("""
CREATE TABLE lead_gen.sales_pipeline.sql_leads (
  sql_id               STRING    NOT NULL COMMENT 'Unique SQL ID. Format: SQL-YYYYMMDD-UUID8.',
  mql_id               STRING    NOT NULL COMMENT 'FK to mql_leads.mql_id.',
  lead_id              STRING    NOT NULL COMMENT 'FK to raw_leads.lead_id.',
  created_at           TIMESTAMP NOT NULL COMMENT 'UTC timestamp when lead was promoted to SQL.',
  updated_at           TIMESTAMP          COMMENT 'UTC timestamp of last update.',
  qualified_at         TIMESTAMP          COMMENT 'UTC timestamp SQL qualification was confirmed.',
  sql_score            INTEGER            COMMENT 'Total BANT score 0-100. Threshold in scoring_config.yaml.',
  bant_score_budget    INTEGER            COMMENT 'BANT Budget score 0-25.',
  bant_score_authority INTEGER            COMMENT 'BANT Authority score 0-25.',
  bant_score_need      INTEGER            COMMENT 'BANT Need score 0-25.',
  bant_score_timeline  INTEGER            COMMENT 'BANT Timeline score 0-25.',
  estimated_deal_size  STRING             COMMENT 'Deal range: <$10K | $10K-$50K | $50K-$200K | $200K+.',
  estimated_close_date DATE               COMMENT 'Expected close date from timeline signals.',
  use_case_summary     STRING             COMMENT 'Business problem and solution fit summary.',
  competitive_context  STRING             COMMENT 'Known competitive situation.',
  next_step            STRING             COMMENT 'Next action: discovery_call | product_demo | proposal | executive_briefing | trial.',
  assigned_team        STRING             COMMENT 'Sales team: enterprise_sales | mid_market_sales | smb_sales | channel_sales.',
  assigned_rep_id      STRING             COMMENT 'Employee ID of assigned sales rep.',
  assigned_rep_name    STRING             COMMENT 'Name of assigned sales rep.',
  assigned_rep_email   STRING             COMMENT 'Email of assigned sales rep.',
  assignment_reason    STRING             COMMENT 'Reason for this rep assignment.',
  agent_version        STRING             COMMENT 'SQL agent version.',
  agent_reasoning      STRING             COMMENT 'Claude SQL agent BANT reasoning.',
  confidence_score     FLOAT              COMMENT 'Agent confidence 0.0-1.0.',
  status               STRING    NOT NULL COMMENT 'SQL status: sql_new | sql_contacted | sql_demo_scheduled | sql_proposal | sql_negotiation | closed_won | closed_lost.',
  crm_opportunity_id   STRING             COMMENT 'CRM opportunity ID after rep accepts.',
  handoff_confirmed    BOOLEAN            COMMENT 'Whether sales rep confirmed receipt.',
  handoff_at           TIMESTAMP          COMMENT 'UTC timestamp of confirmed handoff.'
)
USING DELTA
COMMENT 'Sales Qualified Leads. BANT-qualified leads assigned to sales reps. Genie: pipeline value, rep workload, win rates, sales cycle length.'
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'lead_gen.owner'             = 'sales_ops',
  'lead_gen.genie_enabled'     = 'true'
)
""")
print("✅ Table created: sql_leads")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Cell 6 — Create lead_events

# COMMAND ----------

spark.sql("""
CREATE TABLE lead_gen.sales_pipeline.lead_events (
  event_id         STRING    NOT NULL COMMENT 'Unique event ID.',
  lead_id          STRING    NOT NULL COMMENT 'FK to raw_leads.lead_id.',
  event_timestamp  TIMESTAMP NOT NULL COMMENT 'UTC timestamp of this event.',
  event_type       STRING    NOT NULL COMMENT 'Event: lead_captured | triage_started | triage_completed | mql_scoring_started | mql_qualified | mql_rejected | sql_scoring_started | sql_qualified | sql_rejected | sales_assigned | handoff_confirmed.',
  from_status      STRING             COMMENT 'Lead status before this event.',
  to_status        STRING             COMMENT 'Lead status after this event.',
  agent_name       STRING             COMMENT 'Agent that triggered this event.',
  agent_version    STRING             COMMENT 'Agent version.',
  score_at_event   INTEGER            COMMENT 'Lead score at time of event.',
  event_details    STRING             COMMENT 'JSON payload with event-specific details.',
  duration_seconds INTEGER            COMMENT 'Agent processing time in seconds.',
  error_message    STRING             COMMENT 'Error details if applicable.'
)
USING DELTA
COMMENT 'Immutable append-only audit log. Every state transition recorded here. Genie: measure processing time, identify bottlenecks, calculate time-to-MQL and time-to-SQL.'
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'false',
  'delta.appendOnly'           = 'true',
  'lead_gen.owner'             = 'platform_engineering',
  'lead_gen.genie_enabled'     = 'true'
)
""")
print("✅ Table created: lead_events")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Cell 7 — Create analytics_summary

# COMMAND ----------

spark.sql("""
CREATE TABLE lead_gen.sales_pipeline.analytics_summary (
  summary_id             STRING    NOT NULL COMMENT 'Unique summary record ID.',
  report_date            DATE      NOT NULL COMMENT 'Date this summary represents.',
  report_period          STRING    NOT NULL COMMENT 'Period: daily | weekly | monthly.',
  source_channel         STRING             COMMENT 'Lead source filter. NULL means all channels.',
  leads_captured         INTEGER            COMMENT 'Total raw leads captured in period.',
  leads_accepted         INTEGER            COMMENT 'Leads accepted by triage agent.',
  leads_rejected         INTEGER            COMMENT 'Leads rejected by triage agent.',
  leads_mql              INTEGER            COMMENT 'Leads promoted to MQL.',
  leads_sql              INTEGER            COMMENT 'Leads promoted to SQL.',
  leads_sales_owned      INTEGER            COMMENT 'Leads confirmed by sales reps.',
  acceptance_rate        FLOAT              COMMENT 'leads_accepted / leads_captured.',
  mql_conversion_rate    FLOAT              COMMENT 'leads_mql / leads_accepted.',
  sql_conversion_rate    FLOAT              COMMENT 'leads_sql / leads_mql.',
  sales_conversion_rate  FLOAT              COMMENT 'leads_sales_owned / leads_sql.',
  overall_funnel_rate    FLOAT              COMMENT 'End-to-end: raw capture to sales owned.',
  avg_time_to_mql        FLOAT              COMMENT 'Average hours from capture to MQL.',
  avg_time_to_sql        FLOAT              COMMENT 'Average hours from MQL to SQL.',
  avg_time_to_handoff    FLOAT              COMMENT 'Average hours from SQL to handoff.',
  avg_mql_score          FLOAT              COMMENT 'Average MQL score in period.',
  avg_sql_score          FLOAT              COMMENT 'Average BANT score in period.',
  avg_agent_confidence   FLOAT              COMMENT 'Average agent confidence across all decisions.',
  human_review_rate      FLOAT              COMMENT 'Ratio of leads requiring human review.',
  estimated_pipeline_value STRING           COMMENT 'Sum of estimated deal sizes for SQL leads.',
  computed_at            TIMESTAMP          COMMENT 'When this summary was computed.',
  computed_by            STRING             COMMENT 'Process: analytics_agent | scheduled_job.'
)
USING DELTA
COMMENT 'Pre-aggregated pipeline metrics. Best table for Genie exec reporting and trend analysis.'
TBLPROPERTIES (
  'lead_gen.owner'         = 'marketing_ops',
  'lead_gen.genie_enabled' = 'true'
)
""")
print("✅ Table created: analytics_summary")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Cell 8 — Create sales_reps

# COMMAND ----------

spark.sql("""
CREATE TABLE lead_gen.sales_pipeline.sales_reps (
  rep_id       STRING    NOT NULL COMMENT 'Unique sales rep ID.',
  first_name   STRING    NOT NULL COMMENT 'Rep first name.',
  last_name    STRING    NOT NULL COMMENT 'Rep last name.',
  email        STRING    NOT NULL COMMENT 'Rep work email. Used for lead handoff notifications.',
  team         STRING    NOT NULL COMMENT 'Sales team: enterprise_sales | mid_market_sales | smb_sales | channel_sales.',
  territory    ARRAY<STRING>      COMMENT 'Geographic territories as ISO country codes.',
  industries   ARRAY<STRING>      COMMENT 'Industry specializations.',
  is_active    BOOLEAN            COMMENT 'Whether rep is available for assignment.',
  current_load INTEGER            COMMENT 'Current number of open SQLs assigned.',
  max_load     INTEGER            COMMENT 'Maximum SQL capacity before overflow routing.',
  created_at   TIMESTAMP          COMMENT 'When rep was added to roster.',
  updated_at   TIMESTAMP          COMMENT 'Last update timestamp.'
)
USING DELTA
COMMENT 'Sales rep roster for intelligent lead routing. Genie: join with sql_leads for rep performance and workload analysis.'
TBLPROPERTIES (
  'lead_gen.owner'         = 'sales_ops',
  'lead_gen.genie_enabled' = 'true'
)
""")
print("✅ Table created: sales_reps")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Cell 9 — Seed Sales Reps

# COMMAND ----------

from datetime import datetime
now = datetime.utcnow()

spark.sql(f"""
INSERT INTO lead_gen.sales_pipeline.sales_reps VALUES
  ('REP001', 'Alex',   'Chen',    'alex.chen@company.com',    'enterprise_sales', array('US','CA'), array('Technology','Financial Services'), true,  12, 50, '{now}', '{now}'),
  ('REP002', 'Maria',  'Santos',  'maria.santos@company.com', 'enterprise_sales', array('US','GB'), array('Healthcare','Manufacturing'),       true,  8,  50, '{now}', '{now}'),
  ('REP003', 'James',  'Wright',  'james.wright@company.com', 'mid_market_sales', array('US'),      array('Technology','Retail'),              true,  15, 60, '{now}', '{now}'),
  ('REP004', 'Priya',  'Sharma',  'priya.sharma@company.com', 'mid_market_sales', array('US','IN'), array('Financial Services','Technology'),  true,  10, 60, '{now}', '{now}'),
  ('REP005', 'Marcus', 'Johnson', 'marcus.j@company.com',     'smb_sales',        array('US'),      array('All'),                              true,  5,  80, '{now}', '{now}')
""")

spark.table("lead_gen.sales_pipeline.sales_reps").show()
print("✅ Seeded 5 sales reps")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Cell 10 — Create Genie View

# COMMAND ----------

spark.sql("""
CREATE OR REPLACE VIEW lead_gen.sales_pipeline.vw_full_funnel AS
SELECT
  r.lead_id,
  r.created_at         AS captured_at,
  r.source_channel,
  r.source_campaign,
  r.form_type,
  r.first_name,
  r.last_name,
  r.email,
  r.company,
  r.job_title,
  r.industry,
  r.company_size,
  r.country,
  r.status             AS current_status,
  r.rejection_reason,
  m.mql_id,
  m.mql_score,
  m.persona,
  m.buying_stage,
  m.qualified_at       AS mql_qualified_at,
  m.confidence_score   AS mql_confidence,
  s.sql_id,
  s.sql_score,
  s.bant_score_budget,
  s.bant_score_authority,
  s.bant_score_need,
  s.bant_score_timeline,
  s.estimated_deal_size,
  s.estimated_close_date,
  s.assigned_team,
  s.assigned_rep_name,
  s.qualified_at       AS sql_qualified_at,
  s.handoff_confirmed,
  s.status             AS sql_status,
  DATEDIFF(HOUR, r.created_at, m.qualified_at)   AS hours_to_mql,
  DATEDIFF(HOUR, m.qualified_at, s.qualified_at) AS hours_to_sql
FROM lead_gen.sales_pipeline.raw_leads r
LEFT JOIN lead_gen.sales_pipeline.mql_leads m ON r.lead_id = m.lead_id
LEFT JOIN lead_gen.sales_pipeline.sql_leads s ON m.mql_id  = s.mql_id
""")
print("✅ View created: vw_full_funnel")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Cell 11 — Verify Everything

# COMMAND ----------

tables = spark.sql("SHOW TABLES IN lead_gen.sales_pipeline").collect()
print(f"\n{'Object':<30} {'Temporary'}")
print("-" * 45)
for t in tables:
    print(f"{t.tableName:<30} {t.isTemporary}")

print(f"\n✅ Total objects: {len(tables)}")
print("\n🎯 Schema setup complete — ready for Genie and python main.py")
