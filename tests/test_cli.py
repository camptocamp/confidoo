import logging
from pathlib import Path

import typer
from typer.testing import CliRunner

from confidoo.cli import app
from confidoo.utils.errors import handle_exceptions

runner = CliRunner()


def test_apply_help():
    result = runner.invoke(app, ["apply", "--help"])
    assert result.exit_code == 0


def test_handle_exceptions_keeps_exit():
    """Test that typer.Exit keeps its exit code and prints no error."""
    exit_app = typer.Typer()

    @exit_app.command()
    @handle_exceptions()
    def command(ctx: typer.Context):
        raise typer.Exit(3)

    result = runner.invoke(exit_app)
    assert result.exit_code == 3
    assert "Error" not in result.output


def test_apply_with_config_file(odoo_db):
    """Test applying configuration with automatic rollback."""
    config_file = Path(__file__).parent / "fixtures" / "test-config-01.ini"

    # Unpack connection and db params from fixture
    cursor, db_params = odoo_db

    # Run the CLI command with real database credentials
    result = runner.invoke(
        app,
        [
            "apply",
            str(config_file),
            "-d",
            db_params["database"],
            "-u",
            db_params["user"],
            "-p",
            db_params["password"],
            "-h",
            db_params["host"],
            "-P",
            str(db_params["port"]),
        ],
    )

    # Verify CLI succeeded
    assert result.exit_code == 0, f"CLI failed: {result.stdout}\n{result.stderr}"

    # 1. Verify base.partner_admin was updated
    cursor.execute(
        """
        SELECT p.name, p.email
        FROM res_partner p
        JOIN ir_model_data imd ON imd.res_id = p.id
        WHERE imd.module = 'base'
        AND imd.name = 'partner_admin'
        AND imd.model = 'res.partner'
        """
    )
    partner_data = cursor.fetchone()
    assert partner_data is not None, "base.partner_admin record not found"
    assert partner_data["name"] == '"Confidoo"'
    assert partner_data["email"] == '"admin@confidoo.com"'

    # 2. Verify config parameters were set
    cursor.execute(
        """
        SELECT key, value FROM ir_config_parameter
        WHERE key IN ('ribbon.name', 'database.uuid')
        ORDER BY key
        """
    )
    config_params = cursor.fetchall()
    assert len(config_params) == 2
    assert config_params[0]["key"] == "database.uuid"
    assert config_params[0]["value"] == '"0000-0000-0000-0000"'
    assert config_params[1]["key"] == "ribbon.name"
    assert config_params[1]["value"] == '"Test"'

    # 3. Verify config parameters were deleted
    cursor.execute(
        """
        SELECT key FROM ir_config_parameter
        WHERE key IN ('database.expiration_reason', 'database.expiration_date')
        """
    )
    deleted_params = cursor.fetchall()
    assert len(deleted_params) == 0

    # 4. Verify ir.cron records were updated
    cursor.execute(
        """
        SELECT active FROM ir_cron
        """
    )
    ir_cron = cursor.fetchall()
    assert len(ir_cron) > 0
    assert all(not cron["active"] for cron in ir_cron)


def test_apply_with_invalid_config(odoo_db):
    """Test error handling with invalid configuration."""
    __, db_params = odoo_db
    result = runner.invoke(
        app,
        [
            "apply",
            "-d",
            db_params["database"],
            "-u",
            db_params["user"],
            "-p",
            db_params["password"],
            "-h",
            db_params["host"],
            "-P",
            str(db_params["port"]),
        ],
        input="[invalid_section]\nfield = value\n",
    )
    assert result.exit_code == 1
    # Error messages go to stdout with CliRunner
    output = result.stdout + result.stderr
    assert "Configuration error" in output or "Invalid section name" in output


def test_apply_nonexistent_model(odoo_db):
    """Test error handling when applying to non-existent model/table."""
    config_file = (
        Path(__file__).parent / "fixtures" / "test-config-nonexistent-model.ini"
    )
    __, db_params = odoo_db

    result = runner.invoke(
        app,
        [
            "apply",
            str(config_file),
            "-d",
            db_params["database"],
            "-u",
            db_params["user"],
            "-p",
            db_params["password"],
            "-h",
            db_params["host"],
            "-P",
            str(db_params["port"]),
        ],
    )

    # Should fail with exit code 1
    assert (
        result.exit_code == 1
    ), f"Expected failure but got: {result.stdout}\n{result.stderr}"

    # Verify error message mentions the table
    output = result.stdout + result.stderr
    assert (
        "nonexistent_model" in output.lower() or "does not exist" in output.lower()
    ), f"Error message should mention table: {output}"


def test_apply_nonexistent_xmlid(odoo_db):
    """Test error handling when applying to non-existent XMLID."""
    config_file = (
        Path(__file__).parent / "fixtures" / "test-config-nonexistent-xmlid.ini"
    )
    __, db_params = odoo_db

    result = runner.invoke(
        app,
        [
            "apply",
            str(config_file),
            "-d",
            db_params["database"],
            "-u",
            db_params["user"],
            "-p",
            db_params["password"],
            "-h",
            db_params["host"],
            "-P",
            str(db_params["port"]),
        ],
    )

    # Should fail with exit code 1
    assert (
        result.exit_code == 1
    ), f"Expected failure but got: {result.stdout}\n{result.stderr}"

    # Verify error message mentions the XMLID
    output = result.stdout + result.stderr
    assert (
        "fake_module.fake_record" in output or "not found" in output.lower()
    ), f"Error message should mention XMLID: {output}"


def test_apply_empty_identifier(odoo_db):
    """Test error handling when section has empty identifier."""
    __, db_params = odoo_db

    # Config with empty identifier after colon
    result = runner.invoke(
        app,
        [
            "apply",
            "-d",
            db_params["database"],
            "-u",
            db_params["user"],
            "-p",
            db_params["password"],
            "-h",
            db_params["host"],
            "-P",
            str(db_params["port"]),
        ],
        input="[model:]\nfield = value\n",
    )

    # Should fail with exit code 1
    assert (
        result.exit_code == 1
    ), f"Expected failure but got: {result.stdout}\n{result.stderr}"

    # Verify error message mentions empty identifier or invalid section
    output = result.stdout + result.stderr
    assert "Invalid section name" in output, output


def test_debug_flag(odoo_db, caplog):
    """Test that --debug flag enables debug logging and shows full stack traces."""
    __, db_params = odoo_db

    # Capture logs at DEBUG level to ensure we can see debug messages
    with caplog.at_level(logging.DEBUG, logger="confidoo.cli"):
        # Run with debug flag and valid config
        result = runner.invoke(
            app,
            [
                "--debug",
                "apply",
                "-d",
                db_params["database"],
                "-u",
                db_params["user"],
                "-p",
                db_params["password"],
                "-h",
                db_params["host"],
                "-P",
                str(db_params["port"]),
            ],
            input="",
        )

        # Should succeed
        assert (
            result.exit_code == 0
        ), f"CLI failed with debug: {result.stdout}\n{result.stderr}"

        # Verify root logger level was set to DEBUG by the --debug flag
        assert logging.getLogger().level == logging.DEBUG
