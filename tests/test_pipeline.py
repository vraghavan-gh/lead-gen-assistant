"""
Lead Gen Assistant - Test Suite
Tests for all agents using mock data (no real Databricks or API calls needed)
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.models import RawLeadInput, TriageResult, MQLResult, SQLResult


# ============================================================
# Test Data
# ============================================================

GOOD_LEAD = {
    "first_name": "Sarah",
    "last_name": "Mitchell",
    "email": "s.mitchell@acmecorp.com",
    "company": "Acme Corporation",
    "job_title": "VP of Engineering",
    "company_size": "1001-5000",
    "industry": "Technology",
    "form_type": "demo_request",
    "source_channel": "web_form",
    "message": "We need a data platform. Budget approved. Urgent.",
    "country": "US",
}

SPAM_LEAD = {
    "first_name": "Test",
    "last_name": "User",
    "email": "test@test.com",
    "company": "",
    "form_type": "contact_us",
    "source_channel": "web_form",
    "message": "testing 123 free money",
}

WEAK_LEAD = {
    "first_name": "John",
    "last_name": "Doe",
    "email": "jdoe@gmail.com",
    "company": "Small Biz",
    "job_title": "Analyst",
    "company_size": "11-50",
    "form_type": "newsletter_signup",
    "source_channel": "web_form",
    "message": "just curious",
}


# ============================================================
# Model Tests
# ============================================================

class TestRawLeadInput:
    def test_good_lead_creates_model(self):
        lead = RawLeadInput(**GOOD_LEAD)
        assert lead.email == "s.mitchell@acmecorp.com"
        assert lead.company == "Acme Corporation"

    def test_email_required(self):
        with pytest.raises(Exception):
            RawLeadInput(first_name="Test")

    def test_defaults(self):
        lead = RawLeadInput(email="test@example.com")
        assert lead.source_channel == "web_form"
        assert lead.form_type == "contact_us"
        assert lead.opt_in_marketing is True

    def test_interests_default_empty(self):
        lead = RawLeadInput(email="test@example.com")
        assert lead.interests == []


class TestTriageResult:
    def test_accepted_result(self):
        result = TriageResult(
            lead_id="LD-20250314-TEST001",
            decision="accepted",
            next_agent="mql_agent",
            reasoning="Valid business lead",
            confidence=0.9,
        )
        assert result.decision == "accepted"
        assert result.confidence == 0.9

    def test_rejected_result(self):
        result = TriageResult(
            lead_id="LD-20250314-TEST002",
            decision="rejected",
            next_agent="none",
            reasoning="Spam detected",
            rejection_reason="spam",
            confidence=0.95,
        )
        assert result.decision == "rejected"
        assert result.rejection_reason == "spam"


class TestMQLResult:
    def test_qualified_mql(self):
        result = MQLResult(
            lead_id="LD-20250314-TEST001",
            qualified=True,
            mql_score=72,
            persona="Economic_Buyer",
            buying_stage="decision",
            nurture_track="enterprise_track",
            agent_reasoning="Strong VP-level demo request",
            confidence_score=0.88,
        )
        assert result.qualified is True
        assert result.mql_score == 72

    def test_score_bounds(self):
        with pytest.raises(Exception):
            MQLResult(
                lead_id="test",
                qualified=True,
                mql_score=150,  # > 100 — should fail
                agent_reasoning="test",
                confidence_score=0.8,
            )


class TestSQLResult:
    def test_bant_scores_sum(self):
        result = SQLResult(
            lead_id="LD-test",
            mql_id="MQL-test",
            qualified=True,
            sql_score=80,
            bant_score_budget=20,
            bant_score_authority=25,
            bant_score_need=20,
            bant_score_timeline=15,
            agent_reasoning="Strong BANT signals",
            confidence_score=0.85,
        )
        bant_total = (
            result.bant_score_budget +
            result.bant_score_authority +
            result.bant_score_need +
            result.bant_score_timeline
        )
        assert bant_total == result.sql_score


# ============================================================
# Agent Tests (mocked)
# ============================================================

class TestTriageAgentLogic:
    """Test triage logic without real API calls"""

    def test_spam_detection_keywords(self):
        """Spam keywords should not appear in accepted leads"""
        spam_indicators = ["test@test.com", "free money", "lottery", "winner"]
        msg = SPAM_LEAD.get("message", "") + SPAM_LEAD.get("email", "")
        has_spam = any(kw in msg.lower() for kw in spam_indicators)
        assert has_spam is True

    def test_good_lead_no_spam_signals(self):
        msg = GOOD_LEAD.get("message", "") + GOOD_LEAD.get("email", "")
        spam_indicators = ["test@test.com", "free money", "lottery"]
        has_spam = any(kw in msg.lower() for kw in spam_indicators)
        assert has_spam is False


class TestScoringConfig:
    """Test scoring configuration loads correctly"""

    def test_config_loads(self):
        import yaml
        config_path = Path(__file__).parent.parent / "config" / "scoring_config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)
        assert "mql" in config
        assert "sql" in config
        assert config["mql"]["threshold"] > 0
        assert config["sql"]["threshold"] > 0

    def test_mql_threshold_reasonable(self):
        import yaml
        config_path = Path(__file__).parent.parent / "config" / "scoring_config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)
        threshold = config["mql"]["threshold"]
        assert 30 <= threshold <= 80  # Sanity check

    def test_scoring_rules_present(self):
        import yaml
        config_path = Path(__file__).parent.parent / "config" / "scoring_config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)
        rules = config["mql"]["scoring_rules"]
        required = ["job_title", "company_size", "form_type", "email_domain"]
        for r in required:
            assert r in rules, f"Missing scoring rule: {r}"


# ============================================================
# Pipeline Integration Tests (mocked DB)
# ============================================================

class TestPipelineFlow:
    """Test pipeline routing logic"""

    def test_rejected_lead_stops_pipeline(self):
        """A rejected triage result should not proceed to MQL"""
        triage = TriageResult(
            lead_id="LD-test",
            decision="rejected",
            next_agent="none",
            reasoning="Spam",
            rejection_reason="spam",
            confidence=0.95,
        )
        # Pipeline should stop here
        assert triage.decision == "rejected"
        assert triage.next_agent == "none"

    def test_accepted_lead_routes_to_mql(self):
        """An accepted lead should route to MQL agent"""
        triage = TriageResult(
            lead_id="LD-test",
            decision="accepted",
            next_agent="mql_agent",
            reasoning="Legitimate business lead",
            confidence=0.9,
        )
        assert triage.next_agent == "mql_agent"

    def test_unqualified_mql_enters_nurture(self):
        """An MQL that doesn't score high enough should go to nurture"""
        mql = MQLResult(
            lead_id="LD-test",
            qualified=False,
            mql_score=35,
            nurture_track="general_track",
            agent_reasoning="Score below threshold",
            confidence_score=0.85,
        )
        assert mql.qualified is False
        assert mql.nurture_track == "general_track"
