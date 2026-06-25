"""Typer CLI entrypoint.

Examples:
    resume-build list-roles
    resume-build build --mode static --gh-user JohnDoe --role cybersecurity-blueteam \
        --docs ./my-resume.tex --output ./out --formats latex,md,json
    resume-build build --mode ai --gh-user JohnDoe --role-prompt "blue team SOC analyst" \
        --docs ./my-resume.pdf --output ./out
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import typer

import json

from .config import get_settings
from .llm import get_provider
from .models import Mode
from .pipeline import BuildInputs, Pipeline
from .role import StaticRolePicker
from .sources.social import build_default_aggregator, load_scrape_config
from .sources.document import DocumentSource
from .review_orchestrator import review_resume_text

from .commands.auth_cmd import login, logout
from .commands.scrape_cmd import scrape, scrape_all

app = typer.Typer(help="GitHub-aware role-targeted resume builder.", no_args_is_help=True)

app.command()(login)
app.command()(logout)
app.command()(scrape)
app.command("scrape-all")(scrape_all)


def _parse_formats(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@app.command()
def list_roles() -> None:
    """List role ids available in config/roles.json."""
    settings = get_settings()
    picker = StaticRolePicker(settings.roles_path)
    for role in picker.list_available():
        typer.echo(f"  {role.id:30}  {role.label}")


@app.command()
def build(
    mode: Mode = typer.Option(Mode.STATIC, "--mode", help="ai | static"),
    gh_user: str = typer.Option(..., "--gh-user", help="GitHub username/org to scan."),
    role: str | None = typer.Option(None, "--role", help="Role id (static mode)."),
    role_prompt: str | None = typer.Option(
        None, "--role-prompt", help="Free-form role description (AI mode)."
    ),
    docs: Path | None = typer.Option(
        None, "--docs", help="Path to a resume file (PDF/DOCX/TEX) or a folder."
    ),
    formats: str = typer.Option(
        "latex,md,json,pdf",
        "--formats",
        help="Comma-separated output formats: latex, md, json, pdf.",
    ),
    output: Path = typer.Option(Path("./out"), "--output", help="Output directory."),
    social: Path | None = typer.Option(
        None,
        "--social",
        help="Path to a social.yaml describing handles + enabled vendors for the "
        "scraping middleman. Optional — pipeline runs fine without it.",
    ),
    llm_provider: str | None = typer.Option(
        None,
        "--llm-provider",
        help="Override LLM provider (anthropic | openai | claude-session | null). "
        "Use `claude-session` to drive AI mode interactively via stdin/stdout — "
        "no API key required.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Build a role-targeted resume."""
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    selection = role_prompt if mode == Mode.AI else role
    if not selection:
        flag = "--role-prompt" if mode == Mode.AI else "--role"
        raise typer.BadParameter(f"{flag} is required in {mode.value} mode.")

    llm = get_provider(llm_provider) if (llm_provider and mode == Mode.AI) else None
    pipeline = Pipeline(mode=mode, llm=llm)
    inputs = BuildInputs(
        gh_user=gh_user,
        role_selection=selection,
        docs_path=docs,
        formats=_parse_formats(formats),
        output_dir=output,
        social_config_path=social,
    )
    result = pipeline.run(inputs)
    typer.echo(f"\nGenerated for role: {result.resume.role.label}")
    typer.echo(f"Projects included: {len(result.resume.projects)}")
    for path in result.output_paths:
        typer.echo(f"  -> {path}")


@app.command()
def review(
    docs: Path = typer.Option(..., "--docs", help="Resume file or folder to review."),
    llm_provider: str | None = typer.Option(
        None,
        "--llm-provider",
        help="LLM provider for findings-only review: anthropic | openai | claude-session.",
    ),
    output: Path | None = typer.Option(None, "--output", help="Optional file for review output."),
) -> None:
    """Review a resume using the findings-only Resume Review Orchestrator prompt."""
    documents = DocumentSource().collect(docs)
    resume_text = "\n\n".join(d.text for d in documents if d.text.strip())
    if not resume_text.strip():
        raise typer.BadParameter("No readable resume text found in --docs.")

    llm = get_provider(llm_provider)
    findings = review_resume_text(llm, resume_text)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(findings + "\n", encoding="utf-8")
        typer.echo(f"Wrote review findings to {output}")
        return
    typer.echo(findings)


@app.command("list-vendors")
def list_vendors() -> None:
    """List registered social-media vendor handlers."""
    agg = build_default_aggregator()
    for name in agg.available_vendors():
        typer.echo(f"  {name}")


if __name__ == "__main__":
    app()
