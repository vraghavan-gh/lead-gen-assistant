"""
LangGuard Starter Pack — Demo Scenarios
Three pre-built scenarios that trigger specific policies.
Run these to experience the LangGuard Control Plane in action.

Usage:
    python policy_packs/starter/demo_scenarios.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich import box

from pipeline import LeadGenPipeline
from utils.models import RawLeadInput

console = Console()

SCENARIOS = [
    {
        "id":          "A",
        "name":        "PII in Message Field",
        "policy":      "pii_detection",
        "description": "Lead submits an SSN in the message field. PII Detection should block it before Databricks write.",
        "expected":    "🔒 PII Detection DENY — lead blocked",
        "lead": {
            "first_name":   "Robert",
            "last_name":    "Chen",
            "email":        "robert.chen@acmecorp.com",
            "company":      "Acme Corporation",
            "job_title":    "IT Manager",
            "company_size": "201-1000",
            "industry":     "Technology",
            "form_type":    "contact_us",
            "message":      "Hi, our compliance team requires SSN 123-45-6789 for vendor verification. Please advise.",
        }
    },
    {
        "id":          "B",
        "name":        "Duplicate Lead Submission",
        "policy":      "duplicate_detection",
        "description": "Same email submitted twice. Second submission should be blocked by Duplicate Detection.",
        "expected":    "🔄 Duplicate Detection DENY — second submission blocked",
        "lead": {
            "first_name":   "Maria",
            "last_name":    "Gonzalez",
            "email":        "m.gonzalez@techstart.io",
            "company":      "TechStart",
            "job_title":    "Head of Engineering",
            "company_size": "51-200",
            "industry":     "Technology",
            "form_type":    "demo_request",
            "message":      "Interested in a product demo for our team.",
        }
    },
    {
        "id":          "C",
        "name":        "High Value Enterprise Deal",
        "policy":      "approval_gate",
        "description": "VP-level lead at a 5000+ employee company requesting a demo. Should qualify as $200K+ SQL and trigger Approval Gate.",
        "expected":    "✋ Approval Gate ESCALATE — human approval required",
        "lead": {
            "first_name":   "Jennifer",
            "last_name":    "Walsh",
            "email":        "j.walsh@globalfinancial.com",
            "company":      "Global Financial Services",
            "job_title":    "VP of Technology",
            "company_size": "5000+",
            "industry":     "Financial Services",
            "form_type":    "demo_request",
            "message":      "We are evaluating data platforms for our enterprise. Budget is approved and we need to make a decision within 30 days. Looking for a product demo ASAP.",
        }
    },
]


def run_scenario(pipeline: LeadGenPipeline, scenario: dict) -> None:
    console.print(Panel(
        f"[bold]Scenario {scenario['id']}: {scenario['name']}[/bold]\n\n"
        f"[dim]Policy triggered:[/dim] [cyan]{scenario['policy']}[/cyan]\n"
        f"[dim]Description:[/dim] {scenario['description']}\n"
        f"[dim]Expected:[/dim] [yellow]{scenario['expected']}[/yellow]",
        title=f"[bold cyan]🛡️ LangGuard Demo — Scenario {scenario['id']}[/bold cyan]",
        box=box.DOUBLE_EDGE,
    ))

    lead = RawLeadInput(**scenario["lead"])

    # Scenario B — submit twice to trigger duplicate
    if scenario["id"] == "B":
        console.print("\n[dim]Submitting first time (should succeed)...[/dim]")
        pipeline.process_lead(lead)
        console.print("\n[dim]Submitting same email again (should be blocked)...[/dim]\n")

    result = pipeline.process_lead(lead)
    console.print(f"\n[dim]Final status: {result.get('final_status')}[/dim]\n")


def main():
    console.print(Panel(
        "[bold cyan]🛡️ LangGuard Starter Pack — Demo Scenarios[/bold cyan]\n\n"
        "Three scenarios that trigger specific policies.\n"
        "Watch your terminal for LangGuard policy alerts.\n\n"
        "[dim]Scenarios:[/dim]\n"
        "  A — PII Detection (SSN in message field)\n"
        "  B — Duplicate Detection (same email twice)\n"
        "  C — Approval Gate ($200K+ enterprise deal)",
        box=box.DOUBLE_EDGE,
    ))

    pipeline = LeadGenPipeline()

    for scenario in SCENARIOS:
        console.print()
        if Confirm.ask(f"Run Scenario {scenario['id']}: {scenario['name']}?", default=True):
            run_scenario(pipeline, scenario)
            console.print("─" * 80)


if __name__ == "__main__":
    main()
