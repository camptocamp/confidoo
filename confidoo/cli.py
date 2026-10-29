# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import sys
from typing import Annotated

import typer
from rich.console import Console
from rich.logging import RichHandler

from .main import Confidoo
from .utils.errors import handle_exceptions

# Configure Rich console
console = Console()

# Configure logging to output progress messages
logging.basicConfig(
    level=logging.INFO,
    handlers=[
        RichHandler(console=console, show_time=False, show_level=True, show_path=False)
    ],
    format="%(message)s",
)

logger = logging.getLogger(__name__)


app = typer.Typer(
    name="Confidoo",
    help="Declarative configuration for Odoo",
)


@app.callback()
@handle_exceptions()
def main(
    ctx: typer.Context,
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Enable debug mode", is_eager=True),
    ] = False,
):
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled")


@app.command()
@handle_exceptions()
def apply(
    ctx: typer.Context,
    database: Annotated[
        str,
        typer.Option(
            "--database",
            "-d",
            envvar="PGDATABASE",
            help="Database to apply configuration to.",
        ),
    ],
    user: Annotated[
        str | None,
        typer.Option(
            "--db-user",
            "-u",
            envvar="PGUSER",
            help="Database user. Defaults to the current OS user.",
        ),
    ] = None,
    password: Annotated[
        str | None,
        typer.Option(
            "--db-password",
            "-p",
            envvar="PGPASSWORD",
            help="Database password. If omitted, ~/.pgpass, peer or trust auth apply.",
        ),
    ] = None,
    host: Annotated[
        str | None,
        typer.Option(
            "--db-host",
            "-h",
            envvar="PGHOST",
            help="Database host or Unix socket directory. "
            "Defaults to the local Unix socket.",
        ),
    ] = None,
    port: Annotated[
        int | None,
        typer.Option(
            "--db-port",
            "-P",
            envvar="PGPORT",
            help="Database port. Defaults to 5432.",
        ),
    ] = None,
    file: Annotated[typer.FileText | None, typer.Argument()] = None,
):
    """Apply a declarative configuration to an Odoo database.

    The file can be provided as an argument or piped in from stdin.

    Example:

        confidoo apply config.ini

        confidoo apply < config.ini

        echo $CONFIDOO_CONFIG | confidoo apply
    """
    # Read configuration content from file or stdin
    if file is not None:
        config_file = file
    elif not sys.stdin.isatty():
        config_file = sys.stdin
    else:
        logger.error("No configuration file provided")
        raise typer.Exit(1)

    # Apply configuration
    Confidoo.apply_config(
        database=database,
        user=user,
        password=password,
        host=host,
        port=port,
        config_file=config_file,
    )
