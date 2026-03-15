#!/usr/bin/env python3
"""
Lead Gen Assistant - Interactive CLI
The main entry point for interacting with the Lead Gen pipeline.

Usage:
    python main.py

Commands:
    submit   — Submit a new lead through the pipeline
    status   — Check status of an existing lead
    report   — Run analytics report
    demo     — Run a demo with sample leads
    setup    — Initialize Databricks schema
    quit     — Exit
"""

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich import box
from dotenv import load_dotenv

load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from pipeline import LeadGenPipeline
from utils.models import RawLeadInput, SourceChannel, FormType

console = Console()
app     = typer.Typer()

BANNER = """
[bold cyan]
╔══════════════════════════════════════════════════════════╗
║         🎯  LEAD GEN ASSISTANT  v1.0.0                  ║
║         Multi-Agent Sales Pipeline                       ║
║         Powered by Claude + Databricks                   ║
╚══════════════════════════════════════════════════════════╝
[/bold cyan]
"""

SAMPLE_LEADS = [
    {
        "name": "Strong Enterprise Lead",
        "data": {
            "first_name": "Sarah",
            "last_name": "Mitchell",
            "email": "s.mitchell@acmecorp.com",
            "company": "Acme Corporation",
            "job_title": "VP of Engineering",
            "company_size": "1001-5000",
            "industry": "Technology",
            "form_type": "demo_request",
            "source_channel": "web_form",
            "message": "We're evaluating data platforms to replace our current solution. Budget approved for Q1. Looking to demo ASAP and make a decision within 30 days.",
            "country": "US",
            "phone": "+1-555-0100",
        }
    },
    {
        "name": "Mid-Market MQL Lead",
        "data": {
            "first_name": "James",
            "last_name": "Park",
            "email": "jpark@startupco.io",
            "company": "StartupCo",
            "job_title": "Head of Data",
            "company_size": "51-200",
            "industry": "Financial Services",
            "form_type": "whitepaper_download",
            "source_channel": "web_form",
            "message": "Downloaded your whitepaper on real-time analytics. Interested in learning more about how this could apply to our use case.",
            "country": "US",
        }
    },
    {
        "name": "Likely Rejected Lead",
        "data": {
            "first_name": "Test",
            "last_name": "User",
            "email": "test@test.com",
            "company": "",
            "job_title": "",
            "form_type": "contact_us",
            "source_channel": "web_form",
            "message": "testing 123",
        }
    },
]


def print_banner():
    console.print(BANNER)
    console.print("Type [bold cyan]help[/bold cyan] for available commands\n")


def interactive_lead_form() -> Optional[RawLeadInput]:
    """Interactive form to collect lead data from CLI."""
    console.print(Panel(
        "[bold]Enter Lead Information[/bold]\n"
        "[dim]Press Enter to skip optional fields[/dim]",
        box=box.ROUNDED
    ))

    try:
        first_name = Prompt.ask("[cyan]First Name[/cyan]")
        last_name  = Prompt.ask("[cyan]Last Name[/cyan]")
        email      = Prompt.ask("[cyan]Email[/cyan]  [bold red]*required[/bold red]")
        company    = Prompt.ask("[cyan]Company[/cyan]")
        job_title  = Prompt.ask("[cyan]Job Title[/cyan]")
        company_size = Prompt.ask(
            "[cyan]Company Size[/cyan]",
            choices=["1-10","11-50","51-200","201-1000","1001-5000","5000+",""],
            default=""
        )
        industry   = Prompt.ask("[cyan]Industry[/cyan]", default="")
        country    = Prompt.ask("[cyan]Country[/cyan]", default="US")
        form_type  = Prompt.ask(
            "[cyan]Form Type[/cyan]",
            choices=["demo_request","contact_us","whitepaper_download","newsletter_signup","free_trial"],
            default="contact_us"
        )
        message    = Prompt.ask("[cyan]Message[/cyan]", default="")

        return RawLeadInput(
            first_name   = first_name or None,
            last_name    = last_name  or None,
            email        = email,
            company      = company    or None,
            job_title    = job_title  or None,
            company_size = company_size or None,
            industry     = industry   or None,
            country      = country    or None,
            form_type    = form_type,
            source_channel = "web_form",
            message      = message    or None,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled[/yellow]")
        return None


def run_demo(pipeline: LeadGenPipeline):
    """Run pipeline with sample leads."""
    console.print(Panel(
        "[bold]Demo Mode — Running Sample Leads[/bold]\n"
        "This demonstrates the full multi-agent pipeline",
        box=box.ROUNDED
    ))

    for i, sample in enumerate(SAMPLE_LEADS, 1):
        console.print(f"\n[bold cyan]━━━ Demo Lead {i}/{len(SAMPLE_LEADS)}: {sample['name']} ━━━[/bold cyan]")
        if Confirm.ask(f"Process this lead?", default=True):
            lead = RawLeadInput(**sample["data"])
            result = pipeline.process_lead(lead)
            console.print(f"[dim]Result saved with Lead ID: {result.get('lead_id')}[/dim]")

            if i < len(SAMPLE_LEADS):
                console.print()


def main():
    print_banner()

    try:
        pipeline = LeadGenPipeline()
        console.print("[green]✓ Connected to Databricks[/green]\n")
    except Exception as e:
        console.print(f"[yellow]⚠ Databricks connection: {e}[/yellow]")
        console.print("[dim]Running in demo mode — data will not be persisted[/dim]\n")
        pipeline = None

    # Main REPL loop
    while True:
        try:
            command = Prompt.ask(
                "\n[bold cyan]lead-gen>[/bold cyan]",
                default=""
            ).strip().lower()

            if not command:
                continue

            elif command in ("help", "h", "?"):
                console.print(Panel(
                    "[bold cyan]submit[/bold cyan]    — Submit a new lead through the pipeline\n"
                    "[bold cyan]status[/bold cyan]    — Check status of a lead by ID\n"
                    "[bold cyan]report[/bold cyan]    — Run analytics funnel report\n"
                    "[bold cyan]demo[/bold cyan]      — Run demo with sample leads\n"
                    "[bold cyan]setup[/bold cyan]     — Initialize Databricks schema\n"
                    "[bold cyan]quit[/bold cyan]      — Exit",
                    title="Available Commands",
                    box=box.ROUNDED,
                ))

            elif command in ("submit", "s"):
                lead = interactive_lead_form()
                if lead and pipeline:
                    pipeline.process_lead(lead)
                elif lead:
                    console.print("[yellow]No DB connection — showing lead data:[/yellow]")
                    console.print(lead.model_dump_json(indent=2))

            elif command in ("status", "st"):
                lead_id = Prompt.ask("[cyan]Enter Lead ID[/cyan]")
                if pipeline:
                    pipeline.get_lead_status(lead_id.strip())
                else:
                    console.print("[yellow]No DB connection[/yellow]")

            elif command in ("report", "r"):
                days = int(Prompt.ask("[cyan]Lookback period (days)[/cyan]", default="30"))
                if pipeline:
                    pipeline.get_analytics(days=days)
                else:
                    # Demo analytics without DB
                    from agents.analytics_agent import AnalyticsAgent
                    agent = AnalyticsAgent()
                    agent._display_funnel_table(
                        agent._fetch_funnel_metrics(days), days
                    )

            elif command in ("demo", "d"):
                if pipeline:
                    run_demo(pipeline)
                else:
                    console.print("[yellow]Running demo without DB persistence...[/yellow]")
                    from agents.analytics_agent import AnalyticsAgent
                    agent = AnalyticsAgent()
                    agent._display_funnel_table(
                        agent._fetch_funnel_metrics(30), 30
                    )

            elif command == "setup":
                schema_path = Path(__file__).parent / "schema" / "databricks_schema.sql"
                if schema_path.exists() and pipeline:
                    console.print("[cyan]Initializing Databricks schema...[/cyan]")
                    pipeline.db.execute_script(str(schema_path))
                    console.print("[green]✓ Schema initialized[/green]")
                else:
                    console.print(f"[yellow]Run this manually in Databricks:[/yellow]")
                    console.print(f"[dim]{schema_path}[/dim]")

            elif command in ("quit", "exit", "q"):
                console.print("[bold cyan]👋 Goodbye![/bold cyan]")
                break

            else:
                console.print(f"[red]Unknown command: '{command}'[/red] — type [cyan]help[/cyan]")

        except KeyboardInterrupt:
            console.print("\n[yellow]Use 'quit' to exit[/yellow]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            console.print("[dim]Type 'help' for available commands[/dim]")


if __name__ == "__main__":
    main()
