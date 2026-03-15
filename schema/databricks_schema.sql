-- ============================================================
-- Lead Gen Assistant - Databricks Unity Catalog Schema
-- Optimized for Genie analytics
-- ============================================================
-- Catalog: lead_gen
-- Schema:  sales_pipeline
-- ============================================================

-- Create catalog and schema
CREATE CATALOG IF NOT EXISTS lead_gen
  COMMENT 'Lead Generation Assistant - Enterprise Sales Pipeline Data Product. 
           Contains all lead lifecycle data from raw capture through SQL handoff. 
           Designed for Genie AI analytics and executive reporting.';

CREATE SCHEMA IF NOT EXISTS lead_gen.sales_pipeline
  COMMENT 'Core sales pipeline schema. Tracks leads from raw web/social ingestion 
           through MQL, SQL and Sales Owned stages. Use Genie to query lead conversion 
           rates, funnel velocity, and rep performance.';

-- ============================================================
-- TABLE 1: raw_leads
-- Source of truth for all incoming leads
-- ============================================================
CREATE TABLE IF NOT EXISTS lead_gen.sales_pipeline.raw_leads (
  lead_id           STRING      NOT NULL  COMMENT 'Unique lead identifier. Format: LD-YYYYMMDD-UUID8. Primary key.',
  created_at        TIMESTAMP   NOT NULL  COMMENT 'UTC timestamp when lead was first captured from source channel.',
  updated_at        TIMESTAMP             COMMENT 'UTC timestamp of last record update.',

  -- Source Information
  source_channel    STRING      NOT NULL  COMMENT 'Lead acquisition channel. Values: web_form, linkedin, twitter, facebook, instagram, email_campaign, paid_search, organic_search, referral, event.',
  source_campaign   STRING                COMMENT 'Marketing campaign identifier that generated this lead. Links to campaign tracking systems.',
  source_url        STRING                COMMENT 'Full URL of the page or post where the lead was captured.',
  form_type         STRING                COMMENT 'Type of web form submitted. Values: demo_request, contact_us, whitepaper_download, newsletter_signup, webinar_registration, free_trial.',
  utm_source        STRING                COMMENT 'UTM source parameter from campaign URL.',
  utm_medium        STRING                COMMENT 'UTM medium parameter. e.g. cpc, email, social.',
  utm_campaign      STRING                COMMENT 'UTM campaign name parameter.',

  -- Contact Information
  first_name        STRING                COMMENT 'Lead first name as submitted in form.',
  last_name         STRING                COMMENT 'Lead last name as submitted in form.',
  email             STRING      NOT NULL  COMMENT 'Lead primary email address. Used as secondary deduplication key.',
  phone             STRING                COMMENT 'Lead phone number including country code.',
  linkedin_url      STRING                COMMENT 'LinkedIn profile URL if captured from social or provided in form.',

  -- Company / Firmographic
  company           STRING                COMMENT 'Company or organization name as provided by lead.',
  job_title         STRING                COMMENT 'Lead job title as provided. Used for authority scoring in MQL/SQL.',
  department        STRING                COMMENT 'Business department. e.g. Engineering, Sales, Marketing, Finance.',
  company_size      STRING                COMMENT 'Employee count range. Values: 1-10, 11-50, 51-200, 201-1000, 1001-5000, 5000+.',
  industry          STRING                COMMENT 'Industry vertical. e.g. Technology, Financial Services, Healthcare, Manufacturing.',
  country           STRING                COMMENT 'Country of the lead organization. ISO 3166-1 alpha-2 code.',
  state_region      STRING                COMMENT 'State or region of the lead organization.',

  -- Lead Content
  message           STRING                COMMENT 'Free-text message or inquiry submitted by the lead.',
  interests         ARRAY<STRING>         COMMENT 'Product areas or topics of interest as tagged from form or enrichment.',
  opt_in_marketing  BOOLEAN               COMMENT 'Whether lead has opted in to marketing communications.',

  -- Status
  status            STRING      NOT NULL  COMMENT 'Current lead status. Values: new, processing, accepted, rejected, mql, sql, sales_owned. Managed by triage agent.',
  rejection_reason  STRING                COMMENT 'Reason for rejection if status=rejected. e.g. invalid_email, spam, duplicate, incomplete_data.',

  -- Raw Payload
  raw_payload       STRING                COMMENT 'Original JSON payload as received from source channel. Preserved for audit and reprocessing.',

  CONSTRAINT raw_leads_pk PRIMARY KEY (lead_id)
)
USING DELTA
COMMENT 'Master table of all incoming raw leads captured from web forms and social media channels. 
         Every lead journey begins here. This table is append-friendly — records are inserted on capture 
         and status is updated as leads progress through the pipeline. 
         Genie tip: Query this table to understand lead volume by source, channel mix, and geographic distribution.'
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'lead_gen.owner' = 'marketing_ops',
  'lead_gen.data_classification' = 'confidential_pii',
  'lead_gen.refresh_cadence' = 'real_time',
  'lead_gen.primary_use_case' = 'lead_capture',
  'lead_gen.genie_enabled' = 'true'
);

-- ============================================================
-- TABLE 2: mql_leads
-- Marketing Qualified Leads
-- ============================================================
CREATE TABLE IF NOT EXISTS lead_gen.sales_pipeline.mql_leads (
  mql_id              STRING      NOT NULL  COMMENT 'Unique MQL identifier. Format: MQL-YYYYMMDD-UUID8. Primary key.',
  lead_id             STRING      NOT NULL  COMMENT 'Foreign key to raw_leads.lead_id. Traceability to original lead.',
  created_at          TIMESTAMP   NOT NULL  COMMENT 'UTC timestamp when lead was promoted to MQL status.',
  updated_at          TIMESTAMP             COMMENT 'UTC timestamp of last MQL record update.',
  qualified_at        TIMESTAMP             COMMENT 'UTC timestamp when MQL qualification was confirmed by agent.',

  -- MQL Scoring
  mql_score           INTEGER               COMMENT 'Total MQL qualification score (0-100). Threshold defined in scoring_config.yaml. Higher = stronger MQL.',
  score_breakdown     STRING                COMMENT 'JSON breakdown of score components: job_title, company_size, industry, form_type, email_domain, message_intent, completeness.',

  -- Enriched Firmographics
  enriched_company    STRING                COMMENT 'Verified/enriched company name from enrichment service.',
  enriched_industry   STRING                COMMENT 'Verified industry vertical after enrichment.',
  enriched_employees  INTEGER               COMMENT 'Verified employee headcount from enrichment.',
  enriched_revenue    STRING                COMMENT 'Estimated annual revenue range from enrichment. e.g. $1M-$10M.',
  enriched_website    STRING                COMMENT 'Company website URL from enrichment.',
  company_linkedin    STRING                COMMENT 'Company LinkedIn page URL from enrichment.',
  technologies_used   ARRAY<STRING>         COMMENT 'Tech stack identified for target company. e.g. Salesforce, AWS, Databricks.',

  -- MQL Classification
  persona             STRING                COMMENT 'Buyer persona classification. e.g. Technical_Buyer, Economic_Buyer, End_User, Champion.',
  buying_stage        STRING                COMMENT 'Estimated buying stage. Values: awareness, consideration, decision.',
  product_interest    ARRAY<STRING>         COMMENT 'Specific products or solutions the lead has expressed interest in.',
  pain_points         ARRAY<STRING>         COMMENT 'Identified pain points extracted from lead message and behavior.',

  -- Agent Metadata
  agent_version       STRING                COMMENT 'Version of MQL agent that processed this record. For audit and model tracking.',
  agent_reasoning     STRING                COMMENT 'Natural language reasoning from Claude MQL agent explaining qualification decision.',
  confidence_score    FLOAT                 COMMENT 'Agent confidence in MQL classification (0.0-1.0). Below 0.7 triggers human review.',
  human_reviewed      BOOLEAN DEFAULT FALSE COMMENT 'Whether a human marketing analyst has reviewed and confirmed this MQL.',
  reviewer_id         STRING                COMMENT 'Employee ID of human reviewer if human_reviewed=true.',

  -- Status
  status              STRING      NOT NULL  COMMENT 'MQL lifecycle status. Values: mql_new, mql_nurturing, mql_accepted, mql_rejected, promoted_to_sql.',
  nurture_track       STRING                COMMENT 'Marketing nurture track assigned. e.g. enterprise_track, smb_track, technical_track.',

  CONSTRAINT mql_leads_pk PRIMARY KEY (mql_id),
  CONSTRAINT mql_leads_fk FOREIGN KEY (lead_id) REFERENCES lead_gen.sales_pipeline.raw_leads(lead_id)
)
USING DELTA
COMMENT 'Marketing Qualified Leads (MQL). Contains leads that have passed marketing qualification scoring threshold. 
         Each record represents a lead enriched with firmographic data and scored by the Claude MQL agent. 
         Genie tip: Use this table to analyze MQL conversion rates by persona, industry, and buying stage. 
         Join with raw_leads for full-funnel attribution analysis.'
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'lead_gen.owner' = 'marketing_ops',
  'lead_gen.data_classification' = 'confidential_pii',
  'lead_gen.refresh_cadence' = 'near_real_time',
  'lead_gen.primary_use_case' = 'mql_qualification',
  'lead_gen.genie_enabled' = 'true'
);

-- ============================================================
-- TABLE 3: sql_leads
-- Sales Qualified Leads
-- ============================================================
CREATE TABLE IF NOT EXISTS lead_gen.sales_pipeline.sql_leads (
  sql_id              STRING      NOT NULL  COMMENT 'Unique SQL identifier. Format: SQL-YYYYMMDD-UUID8. Primary key.',
  mql_id              STRING      NOT NULL  COMMENT 'Foreign key to mql_leads.mql_id.',
  lead_id             STRING      NOT NULL  COMMENT 'Foreign key to raw_leads.lead_id. Full traceability.',
  created_at          TIMESTAMP   NOT NULL  COMMENT 'UTC timestamp when lead was promoted to SQL.',
  updated_at          TIMESTAMP             COMMENT 'UTC timestamp of last SQL record update.',
  qualified_at        TIMESTAMP             COMMENT 'UTC timestamp when SQL qualification was confirmed.',

  -- BANT Scoring
  sql_score           INTEGER               COMMENT 'Total SQL qualification score (0-100). Threshold defined in scoring_config.yaml.',
  bant_score_budget   INTEGER               COMMENT 'BANT Budget component score (0-25). Based on budget signals in lead data.',
  bant_score_authority INTEGER              COMMENT 'BANT Authority component score (0-25). Based on job title and decision-making power.',
  bant_score_need     INTEGER               COMMENT 'BANT Need component score (0-25). Based on pain points and use case fit.',
  bant_score_timeline INTEGER               COMMENT 'BANT Timeline component score (0-25). Based on purchase urgency signals.',

  -- Opportunity Details
  estimated_deal_size STRING                COMMENT 'Estimated deal value range. e.g. <$10K, $10K-$50K, $50K-$200K, $200K+.',
  estimated_close_date DATE                 COMMENT 'Estimated opportunity close date based on timeline signals.',
  use_case_summary    STRING                COMMENT 'Natural language summary of the primary use case and business problem to solve.',
  competitive_context STRING                COMMENT 'Known competitive situation. e.g. incumbent vendors, competitive evaluations.',
  next_step           STRING                COMMENT 'Recommended next sales action. e.g. discovery_call, product_demo, proposal, trial.',

  -- Sales Assignment
  assigned_team       STRING                COMMENT 'Sales team assigned. Values: enterprise_sales, mid_market_sales, smb_sales, channel_sales.',
  assigned_rep_id     STRING                COMMENT 'Employee ID of assigned sales representative.',
  assigned_rep_name   STRING                COMMENT 'Full name of assigned sales representative.',
  assigned_rep_email  STRING                COMMENT 'Email of assigned sales representative for CRM sync.',
  assignment_reason   STRING                COMMENT 'Reason for sales team/rep assignment. e.g. territory, vertical, company_size.',

  -- Agent Metadata
  agent_version       STRING                COMMENT 'Version of SQL agent that processed this record.',
  agent_reasoning     STRING                COMMENT 'Natural language reasoning from Claude SQL agent explaining qualification and assignment.',
  confidence_score    FLOAT                 COMMENT 'Agent confidence in SQL classification (0.0-1.0).',

  -- Status
  status              STRING      NOT NULL  COMMENT 'SQL lifecycle status. Values: sql_new, sql_contacted, sql_demo_scheduled, sql_proposal, sql_negotiation, closed_won, closed_lost, sql_recycled.',
  crm_opportunity_id  STRING                COMMENT 'CRM system opportunity ID after sales rep accepts and creates opportunity.',
  handoff_confirmed   BOOLEAN DEFAULT FALSE COMMENT 'Whether sales rep has confirmed receipt of this lead in CRM.',
  handoff_at          TIMESTAMP             COMMENT 'UTC timestamp when sales rep confirmed handoff.',

  CONSTRAINT sql_leads_pk PRIMARY KEY (sql_id),
  CONSTRAINT sql_leads_mql_fk FOREIGN KEY (mql_id) REFERENCES lead_gen.sales_pipeline.mql_leads(mql_id),
  CONSTRAINT sql_leads_raw_fk FOREIGN KEY (lead_id) REFERENCES lead_gen.sales_pipeline.raw_leads(lead_id)
)
USING DELTA
COMMENT 'Sales Qualified Leads (SQL). Contains leads that have passed BANT qualification and been assigned to a sales representative. 
         Each record represents a sales-ready opportunity with deal context, competitive intel, and rep assignment. 
         Genie tip: Query this table for pipeline value, rep workload, win rates, and average sales cycle length. 
         Join with mql_leads and raw_leads for full-funnel analysis from first touch to closed won.'
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'lead_gen.owner' = 'sales_ops',
  'lead_gen.data_classification' = 'confidential_pii',
  'lead_gen.refresh_cadence' = 'near_real_time',
  'lead_gen.primary_use_case' = 'sql_qualification',
  'lead_gen.genie_enabled' = 'true'
);

-- ============================================================
-- TABLE 4: lead_events
-- Full audit trail — every state transition
-- ============================================================
CREATE TABLE IF NOT EXISTS lead_gen.sales_pipeline.lead_events (
  event_id          STRING      NOT NULL  COMMENT 'Unique event identifier. Primary key.',
  lead_id           STRING      NOT NULL  COMMENT 'Foreign key to raw_leads.lead_id.',
  event_timestamp   TIMESTAMP   NOT NULL  COMMENT 'UTC timestamp when this event occurred.',
  event_type        STRING      NOT NULL  COMMENT 'Event classification. Values: lead_captured, triage_started, triage_completed, mql_scoring_started, mql_qualified, mql_rejected, sql_scoring_started, sql_qualified, sql_rejected, sales_assigned, handoff_confirmed, lead_recycled, lead_archived.',
  from_status       STRING                COMMENT 'Lead status before this event.',
  to_status         STRING                COMMENT 'Lead status after this event.',
  agent_name        STRING                COMMENT 'Name of the agent that triggered this event. Values: triage_agent, mql_agent, sql_agent, analytics_agent, human.',
  agent_version     STRING                COMMENT 'Version of the agent that triggered this event.',
  score_at_event    INTEGER               COMMENT 'Lead score at the time of this event.',
  event_details     STRING                COMMENT 'JSON payload with event-specific details and agent reasoning.',
  duration_seconds  INTEGER               COMMENT 'Time in seconds the agent took to process this event.',
  error_message     STRING                COMMENT 'Error details if event_type indicates a failure or exception.',

  CONSTRAINT lead_events_pk PRIMARY KEY (event_id),
  CONSTRAINT lead_events_fk FOREIGN KEY (lead_id) REFERENCES lead_gen.sales_pipeline.raw_leads(lead_id)
)
USING DELTA
COMMENT 'Immutable audit log of every state transition and agent action across the lead lifecycle. 
         This is the single source of truth for lead journey reconstruction and process analytics. 
         Genie tip: Query this table to measure agent processing times, identify pipeline bottlenecks, 
         and calculate time-to-MQL and time-to-SQL velocity metrics. Never updated — append only.'
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'false',
  'delta.appendOnly' = 'true',
  'lead_gen.owner' = 'platform_engineering',
  'lead_gen.data_classification' = 'internal',
  'lead_gen.refresh_cadence' = 'real_time',
  'lead_gen.primary_use_case' = 'audit_trail',
  'lead_gen.genie_enabled' = 'true'
);

-- ============================================================
-- TABLE 5: analytics_summary
-- Pre-aggregated metrics for Genie and dashboards
-- ============================================================
CREATE TABLE IF NOT EXISTS lead_gen.sales_pipeline.analytics_summary (
  summary_id          STRING      NOT NULL  COMMENT 'Unique summary record identifier.',
  report_date         DATE        NOT NULL  COMMENT 'Date this summary record represents.',
  report_period       STRING      NOT NULL  COMMENT 'Aggregation period. Values: daily, weekly, monthly.',
  source_channel      STRING                COMMENT 'Lead source channel for this summary row. NULL = all channels.',

  -- Volume Metrics
  leads_captured      INTEGER               COMMENT 'Total raw leads captured in this period.',
  leads_accepted      INTEGER               COMMENT 'Leads accepted by triage agent (not spam/invalid).',
  leads_rejected      INTEGER               COMMENT 'Leads rejected by triage agent.',
  leads_mql           INTEGER               COMMENT 'Leads promoted to MQL status.',
  leads_sql           INTEGER               COMMENT 'Leads promoted to SQL status.',
  leads_sales_owned   INTEGER               COMMENT 'Leads confirmed accepted by sales reps.',

  -- Conversion Rates
  acceptance_rate     FLOAT                 COMMENT 'Ratio of accepted to total captured leads. leads_accepted / leads_captured.',
  mql_conversion_rate FLOAT                 COMMENT 'Ratio of MQL to accepted leads. leads_mql / leads_accepted.',
  sql_conversion_rate FLOAT                 COMMENT 'Ratio of SQL to MQL leads. leads_sql / leads_mql.',
  sales_conversion_rate FLOAT               COMMENT 'Ratio of sales_owned to SQL leads. leads_sales_owned / leads_sql.',
  overall_funnel_rate FLOAT                 COMMENT 'End-to-end conversion from raw capture to sales owned.',

  -- Velocity Metrics (in hours)
  avg_time_to_mql     FLOAT                 COMMENT 'Average hours from lead capture to MQL qualification.',
  avg_time_to_sql     FLOAT                 COMMENT 'Average hours from MQL to SQL qualification.',
  avg_time_to_handoff FLOAT                 COMMENT 'Average hours from SQL to confirmed sales handoff.',

  -- Quality Metrics
  avg_mql_score       FLOAT                 COMMENT 'Average MQL score for qualified leads in this period.',
  avg_sql_score       FLOAT                 COMMENT 'Average SQL score for qualified leads in this period.',
  avg_agent_confidence FLOAT                COMMENT 'Average agent confidence score across all decisions.',
  human_review_rate   FLOAT                 COMMENT 'Ratio of leads requiring human review.',

  -- Pipeline Value
  estimated_pipeline_value STRING           COMMENT 'Sum of estimated deal sizes for SQL leads in this period.',

  -- Metadata
  computed_at         TIMESTAMP             COMMENT 'UTC timestamp when this summary was computed.',
  computed_by         STRING                COMMENT 'Process that computed this summary. Values: analytics_agent, scheduled_job.',

  CONSTRAINT analytics_summary_pk PRIMARY KEY (summary_id)
)
USING DELTA
COMMENT 'Pre-aggregated analytics summary table for fast dashboard queries and Genie AI analytics. 
         Refreshed daily by the analytics agent. Contains funnel metrics, conversion rates, 
         velocity KPIs, and pipeline value estimates. 
         Genie tip: This is the best table for executive reporting, trend analysis, 
         and "how is our lead pipeline performing?" type questions. 
         Join with raw_leads or lead_events for drill-down analysis.'
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'lead_gen.owner' = 'marketing_ops',
  'lead_gen.data_classification' = 'internal',
  'lead_gen.refresh_cadence' = 'daily',
  'lead_gen.primary_use_case' = 'analytics_reporting',
  'lead_gen.genie_enabled' = 'true'
);

-- ============================================================
-- TABLE 6: sales_reps
-- Sales rep roster for assignment routing
-- ============================================================
CREATE TABLE IF NOT EXISTS lead_gen.sales_pipeline.sales_reps (
  rep_id            STRING      NOT NULL  COMMENT 'Unique sales rep identifier. Primary key.',
  first_name        STRING      NOT NULL  COMMENT 'Sales rep first name.',
  last_name         STRING      NOT NULL  COMMENT 'Sales rep last name.',
  email             STRING      NOT NULL  COMMENT 'Sales rep work email. Used for lead handoff notifications.',
  team              STRING      NOT NULL  COMMENT 'Sales team assignment. Values: enterprise_sales, mid_market_sales, smb_sales, channel_sales.',
  territory         ARRAY<STRING>         COMMENT 'Geographic territory assignments. ISO country codes.',
  industries        ARRAY<STRING>         COMMENT 'Industry verticals this rep specializes in.',
  is_active         BOOLEAN DEFAULT TRUE  COMMENT 'Whether rep is currently active and available for lead assignment.',
  current_load      INTEGER DEFAULT 0     COMMENT 'Current number of open SQLs assigned to this rep. Used for load balancing.',
  max_load          INTEGER DEFAULT 50    COMMENT 'Maximum SQL capacity for this rep before overflow routing.',
  created_at        TIMESTAMP             COMMENT 'UTC timestamp when rep was added to roster.',
  updated_at        TIMESTAMP             COMMENT 'UTC timestamp of last rep record update.',

  CONSTRAINT sales_reps_pk PRIMARY KEY (rep_id)
)
USING DELTA
COMMENT 'Sales representative roster used by the SQL agent for intelligent lead routing and assignment. 
         Contains territory, industry specialization, and current workload for load-balanced assignment. 
         Genie tip: Join with sql_leads to analyze rep performance, pipeline by rep, and workload distribution.'
TBLPROPERTIES (
  'lead_gen.owner' = 'sales_ops',
  'lead_gen.data_classification' = 'internal',
  'lead_gen.refresh_cadence' = 'on_change',
  'lead_gen.genie_enabled' = 'true'
);

-- ============================================================
-- VIEWS: Genie-friendly denormalized views
-- ============================================================

CREATE OR REPLACE VIEW lead_gen.sales_pipeline.vw_full_funnel AS
SELECT
  r.lead_id,
  r.created_at                    AS captured_at,
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
  r.status                        AS current_status,
  r.rejection_reason,
  m.mql_id,
  m.mql_score,
  m.persona,
  m.buying_stage,
  m.qualified_at                  AS mql_qualified_at,
  m.confidence_score              AS mql_confidence,
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
  s.qualified_at                  AS sql_qualified_at,
  s.handoff_confirmed,
  s.status                        AS sql_status,
  DATEDIFF(HOUR, r.created_at, m.qualified_at)  AS hours_to_mql,
  DATEDIFF(HOUR, m.qualified_at, s.qualified_at) AS hours_to_sql
FROM lead_gen.sales_pipeline.raw_leads r
LEFT JOIN lead_gen.sales_pipeline.mql_leads m ON r.lead_id = m.lead_id
LEFT JOIN lead_gen.sales_pipeline.sql_leads s ON m.mql_id  = s.mql_id
COMMENT ON VIEW lead_gen.sales_pipeline.vw_full_funnel IS 
  'Denormalized full-funnel view joining raw_leads, mql_leads, and sql_leads. 
   Best starting point for Genie queries about the complete lead journey. 
   Includes velocity metrics (hours_to_mql, hours_to_sql) for pipeline efficiency analysis.';
