# Copyright 2026 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from functools import wraps

import typer


def handle_exceptions():
    """Decorator to handle exceptions and print a nice error message.

    If `debug` is set in the context, the function is run without catching
    exceptions so that the full stack trace is shown.
    Otherwise, a short error message is printed and the
    command exits with code 1.

    The decorated function must take the typer context as `ctx`, e.g:

    .. code-block:: python

        @app.command()
        @handle_exceptions()
        def my_command(ctx: typer.Context):
            ...

    """

    def decorator(func):
        @wraps(func)
        def wrapper(ctx: typer.Context, *args, **kwargs):
            # Check the current context (e.g: command options)
            # and the root context (e.g: global options)
            debug = ctx.params.get("debug") or ctx.find_root().params.get("debug")
            # If debug mode is enabled, run the function without catching exceptions
            if debug:
                return func(ctx, *args, **kwargs)
            # Otherwise, print a short error message
            try:
                return func(ctx, *args, **kwargs)
            except typer.Exit:
                raise
            except Exception as e:
                typer.echo(f"Error: Failed to {func.__name__}: {e}", err=True)
                raise typer.Exit(1) from e

        return wrapper

    return decorator
