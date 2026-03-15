"""
Lead Gen Assistant - Pydantic Data Models
Defines the core data structures for the lead pipeline
"""

from __future__ import annotations
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, validator, ConfigDict
from enum import Enum


# ============================================================
# Enums
# ============================================================

class LeadStatus(str, Enum):
    NEW           = "new"
    PROCESSING    = "processing"
    ACCEPTED      = "accepted"
    REJECTED      = "rejected"
    MQL           = "mql"
    SQL           = "sql"
    SALES_OWNED   = "sales_owned"

class SourceChannel(str, Enum):
    WEB_FORM      = "web_form"
    LINKEDIN      = "linkedin"
    TWITTER       = "twitter"
    FACEBOOK      = "facebook"
    INSTAGRAM     = "instagram"
    EMAIL         = "email_campaign"
    PAID_SEARCH   = "paid_search"
    ORGANIC       = "organic_search"
    REFERRAL      = "referral"
    EVENT         = "event"

class FormType(str, Enum):
    DEMO_REQUEST        = "demo_request"
    CONTACT_US          = "contact_us"
    WHITEPAPER          = "whitepaper_download"
    NEWSLETTER          = "newsletter_signup"
    WEBINAR             = "webinar_registration"
    FREE_TRIAL          = "free_trial"

class BuyingStage(str, Enum):
    AWARENESS     = "awareness"
    CONSIDERATION = "consideration"
    DECISION      = "decision"

class SalesTeam(str, Enum):
    ENTERPRISE    = "enterprise_sales"
    MID_MARKET    = "mid_market_sales"
    SMB           = "smb_sales"
    CHANNEL       = "channel_sales"


# ============================================================
# Raw Lead Input (from web form / social)
# ============================================================

class RawLeadInput(BaseModel):
    """
    Represents a raw lead as it comes in from web/social channels.
    This is the input to the Triage Agent.
    """
    # Source
    source_channel:   SourceChannel = SourceChannel.WEB_FORM
    source_campaign:  Optional[str] = None
    source_url:       Optional[str] = None
    form_type:        FormType      = FormType.CONTACT_US
    utm_source:       Optional[str] = None
    utm_medium:       Optional[str] = None
    utm_campaign:     Optional[str] = None

    # Contact
    first_name:       Optional[str] = None
    last_name:        Optional[str] = None
    email:            str            = Field(..., description="Required — primary identifier")
    phone:            Optional[str] = None
    linkedin_url:     Optional[str] = None

    # Firmographic
    company:          Optional[str] = None
    job_title:        Optional[str] = None
    department:       Optional[str] = None
    company_size:     Optional[str] = None
    industry:         Optional[str] = None
    country:          Optional[str] = None
    state_region:     Optional[str] = None

    # Content
    message:          Optional[str] = None
    interests:        list[str]     = Field(default_factory=list)
    opt_in_marketing: bool          = True

    model_config = ConfigDict(use_enum_values=True)


# ============================================================
# Triage Result
# ============================================================

class TriageResult(BaseModel):
    lead_id:          str
    decision:         str   # accepted | rejected | needs_review
    next_agent:       Optional[str] = None  # mql_agent | human_review
    reasoning:        str
    rejection_reason: Optional[str] = None
    confidence:       float = Field(ge=0.0, le=1.0)


# ============================================================
# MQL Result
# ============================================================

class MQLResult(BaseModel):
    lead_id:          str
    mql_id:           Optional[str] = None
    qualified:        bool
    mql_score:        int   = Field(ge=0, le=100)
    score_breakdown:  dict  = Field(default_factory=dict)

    # Enriched data
    enriched_company:   Optional[str] = None
    enriched_industry:  Optional[str] = None
    enriched_employees: Optional[int] = None
    enriched_revenue:   Optional[str] = None
    technologies_used:  list[str]     = Field(default_factory=list)

    # Classification
    persona:          Optional[str]          = None
    buying_stage:     Optional[BuyingStage]  = None
    product_interest: list[str]              = Field(default_factory=list)
    pain_points:      list[str]              = Field(default_factory=list)
    nurture_track:    Optional[str]          = None

    # Agent metadata
    agent_reasoning:  str
    confidence_score: float = Field(ge=0.0, le=1.0)
    agent_version:    str   = "1.0.0"


# ============================================================
# SQL Result
# ============================================================

class SQLResult(BaseModel):
    lead_id:          str
    mql_id:           str
    sql_id:           Optional[str] = None
    qualified:        bool

    # BANT
    sql_score:             int   = Field(ge=0, le=100)
    bant_score_budget:     int   = Field(ge=0, le=25)
    bant_score_authority:  int   = Field(ge=0, le=25)
    bant_score_need:       int   = Field(ge=0, le=25)
    bant_score_timeline:   int   = Field(ge=0, le=25)

    # Opportunity
    estimated_deal_size:   Optional[str]  = None
    estimated_close_date:  Optional[date] = None
    use_case_summary:      Optional[str]  = None
    competitive_context:   Optional[str]  = None
    next_step:             Optional[str]  = None

    # Assignment
    assigned_team:         Optional[SalesTeam] = None
    assigned_rep_id:       Optional[str]       = None
    assigned_rep_name:     Optional[str]       = None
    assigned_rep_email:    Optional[str]       = None
    assignment_reason:     Optional[str]       = None

    # Agent metadata
    agent_reasoning:  str
    confidence_score: float = Field(ge=0.0, le=1.0)
    agent_version:    str   = "1.0.0"


# ============================================================
# Analytics Report
# ============================================================

class FunnelMetrics(BaseModel):
    period_days:           int
    leads_captured:        int
    leads_accepted:        int
    leads_rejected:        int
    leads_mql:             int
    leads_sql:             int
    leads_sales_owned:     int
    acceptance_rate:       float
    mql_conversion_rate:   float
    sql_conversion_rate:   float
    overall_funnel_rate:   float

class LeadTimelineEvent(BaseModel):
    event_timestamp:  datetime
    event_type:       str
    agent_name:       str
    from_status:      Optional[str]
    to_status:        Optional[str]
    score_at_event:   Optional[int]
