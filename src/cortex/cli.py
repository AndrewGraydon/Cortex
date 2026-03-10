"""Cortex CLI entry point."""

from __future__ import annotations

from pathlib import Path

import click

from cortex.config import load_config


@click.group()
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to cortex.yaml config file.",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default=None,
    help="Override log level.",
)
@click.pass_context
def main(ctx: click.Context, config_path: Path | None, log_level: str | None) -> None:
    """Cortex — local voice assistant for Raspberry Pi 5 + NPU."""
    ctx.ensure_object(dict)
    cfg = load_config(config_path)
    if log_level is not None:
        cfg.system.log_level = log_level.upper()
    ctx.obj["config"] = cfg


@main.command()
@click.option("--mock/--no-mock", default=True, help="Use mock HAL services (default: mock).")
@click.option(
    "--models-dir",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Override models directory (default: ~/models).",
)
@click.pass_context
def run(ctx: click.Context, mock: bool, models_dir: Path | None) -> None:
    """Start the Cortex voice assistant."""
    import asyncio

    from cortex.utils.logging import configure_logging

    cfg = ctx.obj["config"]
    configure_logging(log_level=cfg.system.log_level)

    click.echo(f"Starting Cortex (log_level={cfg.system.log_level}, mock={mock})...")

    from cortex.core.service import run_cortex

    asyncio.run(run_cortex(mock=mock, models_dir=models_dir, config=cfg))


@main.command()
@click.pass_context
def config(ctx: click.Context) -> None:
    """Show loaded configuration."""
    cfg = ctx.obj["config"]
    click.echo(cfg.model_dump_json(indent=2))


@main.command()
def version() -> None:
    """Show version."""
    click.echo("cortex 0.1.0")
