from __future__ import annotations

from pathlib import Path

import typer

from mcm_agent.config import load_settings
from mcm_agent.corpus.ingest import CorpusKB, ingest_corpus
from mcm_agent.corpus.manifest import build_manifest
from mcm_agent.providers.factory import build_provider_bundle
from mcm_agent.utils.json_io import read_json

kb_app = typer.Typer(help="Build and query the MCM outstanding-paper knowledge base.")


def _parse_set(value: str | None, cast):
    if not value:
        return None
    return {cast(item.strip()) for item in value.split(",") if item.strip()}


def _where(section: str, problem_type: str) -> dict | None:
    conditions: list[dict] = []
    if section:
        conditions.append({"section_type": section})
    if problem_type:
        conditions.append({"problem_type": problem_type})
    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


@kb_app.command("build")
def build(
    corpus: Path = typer.Option(Path("assets/mcm_icm_corpus"), "--corpus", help="Corpus dir"),
    kb: Path = typer.Option(Path("corpus_kb"), "--kb", help="Output KB dir"),
    years: str = typer.Option("", "--years", help="Comma list e.g. 2018,2019; empty=all"),
    problems: str = typer.Option("", "--problems", help="Comma list of letters; empty=all"),
    env_file: str | None = typer.Option(None, "--env-file"),
    config_file: str | None = typer.Option(None, "--config-file"),
) -> None:
    """Build the corpus knowledge base from outstanding-paper PDFs."""
    settings = load_settings(env_file, config_file)
    bundle = build_provider_bundle(settings, workspace_root=Path.cwd())
    entries = build_manifest(corpus)
    typer.echo(f"Manifest: {len(entries)} papers discovered.")
    summary = ingest_corpus(
        entries,
        kb,
        mineru_provider=bundle.mineru,
        embedding_provider=bundle.embedding,
        embedding_model=settings.embedding_model,
        years=_parse_set(years, int),
        problems=_parse_set(problems, str),
    )
    typer.echo(
        f"Ingested papers={summary.papers_ingested} chunks={summary.chunks_indexed} "
        f"skipped={summary.skipped} -> {kb}"
    )


@kb_app.command("status")
def status(kb: Path = typer.Option(Path("corpus_kb"), "--kb")) -> None:
    """Show how many papers are indexed in the KB, by year."""
    manifest = read_json(kb / "manifest.json", [])
    typer.echo(f"KB at {kb}: {len(manifest)} papers indexed.")
    by_year: dict = {}
    for entry in manifest:
        by_year[entry.get("year")] = by_year.get(entry.get("year"), 0) + 1
    for year in sorted(by_year, key=lambda y: (y is None, y)):
        typer.echo(f"  {year}: {by_year[year]}")


@kb_app.command("query")
def query(
    text: str = typer.Argument(..., help="Query text"),
    kb: Path = typer.Option(Path("corpus_kb"), "--kb"),
    section: str = typer.Option("", "--section", help="Filter by section_type"),
    problem_type: str = typer.Option("", "--problem-type", help="Filter by problem_type"),
    top_k: int = typer.Option(5, "--top-k"),
    env_file: str | None = typer.Option(None, "--env-file"),
    config_file: str | None = typer.Option(None, "--config-file"),
) -> None:
    """Query the corpus KB, optionally filtered by section/problem type."""
    settings = load_settings(env_file, config_file)
    bundle = build_provider_bundle(settings, workspace_root=Path.cwd())
    hits = CorpusKB(kb).query(
        text,
        bundle.embedding,
        bundle.reranker,
        where=_where(section, problem_type),
        top_k=top_k,
    )
    for hit in hits:
        meta = hit.metadata
        typer.echo(
            f"[{meta.get('paper_id')} {meta.get('problem_type')}/{meta.get('section_type')}] "
            f"{hit.content[:200].strip()}"
        )
