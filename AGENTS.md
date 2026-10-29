# Confidoo Architecture

This document describes the architecture and components of Confidoo, a declarative configuration tool for Odoo databases.

## Overview

Confidoo is a command-line tool that applies declarative configuration to Odoo databases. It parses INI-formatted configuration files and applies model-wide settings, record-specific settings, and system parameters to target Odoo databases.

## Core Components

### 1. CLI Interface ([cli.py](confidoo/cli.py))

The command-line interface built with Typer provides the user-facing commands:

- **Main Application**: `app = typer.Typer()` - The root CLI application
- **apply Command**: The primary command that connects to a database and applies configuration

**Responsibilities:**
- Parse command-line arguments and options
- Handle database connection parameters (via CLI options or environment variables)
- Read configuration from files or stdin
- Delegate to `Confidoo.apply_config()` for execution
- Display progress and error messages via Rich logging

**Key Features:**
- Supports multiple input methods: file argument, stdin pipe, or environment variable
- Database credentials can be provided via CLI flags or PostgreSQL environment variables (PGDATABASE, PGUSER, PGPASSWORD, PGHOST, PGPORT)
- Debug mode for detailed error traces
- Automatic transaction management with commit/rollback
- Row count reporting for visibility into changes

**Implementation:**
```python
Confidoo.apply_config(
    database=database,
    user=user,
    password=password,
    host=host,
    port=port,
    config_content=config_content,
)
```

The CLI is a thin wrapper that handles argument parsing and delegates actual work to the `Confidoo` class.

### 2. Configuration Parser ([config.py](confidoo/config.py))

The parser transforms INI configuration files into structured Python objects.

**Key Classes:**

#### `ConfidooConfigParser`
Main parser class that processes INI files with special section syntax.

**Responsibilities:**
- Parse INI content using Python's ConfigParser
- Validate section syntax and structure
- Extract fields and special attributes
- Build ordered configuration operations

**Features:**
- Preserves insertion order of sections (critical for correct application sequence)
- Allows repeated sections: each occurrence becomes its own operation, in file order
  (never merged). Internally, `_OrderedSectionsParser` (a `ConfigParser` subclass)
  hooks `SECTCRE` while reading so each header occurrence is stored under a unique
  internal name, mapped back to the real name when building operations and in error
  messages. `[DEFAULT]` is left untouched, and duplicate keys within a single
  occurrence are still rejected (strict mode)
- Supports variable interpolation disabled for literal values
- Allows empty values for unsetting parameters

#### `ParsedConfig`
Container for parsed configuration operations.

**Responsibilities:**
- Maintain ordered list of configuration operations
- Provide iteration interface for processing operations sequentially

#### Operation Types

All operations inherit from `ConfigOperation` base class:

##### `ModelOperation`
Represents model-wide settings that apply to all records of a model.

**Format**: `[model:model_name]`

**Attributes:**
- `identifier`: The Odoo model name (e.g., "ir.mail_server")
- `fields`: Dictionary of field names to values
- `table`: Optional custom database table name (via `_table` attribute)

##### `RecordOperation`
Represents settings for a specific record identified by XML ID.

**Format**: `[record:xml_id]`

**Attributes:**
- `identifier`: The XML ID of the record (e.g., "customer_module.sftp_server")
- `fields`: Dictionary of field names to values
- `table`: Optional custom database table name (via `_table` attribute)

##### `ConfigParamOperation`
Represents system parameter configuration.

**Format**: `[config:set_param]`

**Attributes:**
- `identifier`: The operation identifier (typically "set_param")
- `fields`: Dictionary of parameter keys to values

**Special Features:**
- Config operations cannot have `_table` attribute
- Empty values (e.g., `param =`) are used to unset parameters

### 3. Main Application Logic ([main.py](confidoo/main.py))

The main module provides the high-level API for applying configuration to Odoo databases.

**Key Class:**

#### `Confidoo`
Main class that orchestrates configuration loading and application.

**Initialization:**
```python
Confidoo(
    database: str,
    user: str,
    password: str,
    host: str = "localhost",
    port: int = 5432,
    config_content: str | None = None,
    config_path: str | Path | None = None,
    config_file: TextIO | None = None,
)
```

**Three Usage Patterns:**

1. **One-liner (convenience method):**
   ```python
   Confidoo.apply_config(
       config_content="[model:ir.mail_server]\nsmtp_host=localhost",
       database="mydb",
       user="odoo",
       password="odoo"
   )
   ```

2. **Constructor with config:**
   ```python
   confidoo = Confidoo(
       database="mydb",
       user="odoo",
       password="odoo",
       config_content="[model:ir.mail_server]\nsmtp_host=localhost"
   )
   with confidoo.connect():
       confidoo.apply()
   ```

3. **Separate load (for programmatic control):**
   ```python
   confidoo = Confidoo(database="mydb", user="odoo", password="odoo")
   confidoo.load_config(content)
   with confidoo.connect():
       confidoo.apply()
   ```

**Key Methods:**

- **`load_config(content: str)`**: Parse configuration from string
- **`load_config_file(path: str | Path)`**: Parse configuration from file
- **`connect() -> OdooDatabase`**: Returns database context manager
- **`apply()`**: Apply all operations within a transaction
- **`apply_config(...)`**: Class method combining all steps

**Properties:**

- **`config`**: Returns ParsedConfig or raises RuntimeError if not loaded
- **`db`**: Returns OdooDatabase or raises RuntimeError if not connected

**Operation Handlers (Private):**

- **`_apply_operation(operation)`**: Dispatcher based on operation type (isinstance checks)
- **`_apply_model_operation(operation)`**: Executes `UPDATE table SET fields` for all records
- **`_apply_record_operation(operation)`**: Resolves XMLID, then `UPDATE table SET fields WHERE id = res_id`
- **`_apply_config_param_operation(operation)`**: For each parameter:
  - Empty value: `DELETE FROM ir_config_parameter WHERE key = %s`
  - Non-empty: `INSERT ... ON CONFLICT DO UPDATE` (PostgreSQL UPSERT)

### 4. Database Connection ([db.py](confidoo/db.py))

The database module handles PostgreSQL connections and Odoo-specific operations.

**Key Components:**

#### `ConnectionParams`
Dataclass encapsulating database connection parameters.

**Attributes:**
- `database`, `user`, `password`, `host`, `port`

**Methods:**
- `to_dsn()`: Converts to psycopg2 connection string

#### `OdooDatabase`
Context manager for database connections with automatic transaction management.

**Context Manager Behavior:**
- **`__enter__`**:
  - Connects to PostgreSQL with RealDictCursor
  - Validates this is an Odoo database (checks for `ir_module_module` table)
  - Extracts Odoo version from base module
  - Returns self for use in `with` statement
- **`__exit__`**:
  - Commits transaction on success
  - Rolls back transaction on exception
  - Always closes cursor and connection

**Properties:**

- **`cr`**: Returns psycopg2 cursor or raises RuntimeError if not connected
  - Provides direct access to cursor for SQL operations
  - Used pattern: `db.cr.execute(query, params)` and `db.cr.rowcount`

**Key Methods:**

- **`resolve_xmlid(xmlid: str) -> tuple[str, int]`**:
  - Converts XML ID (e.g., "base.user_admin") to (model, res_id) tuple
  - Queries `ir_model_data` table
  - Raises XmlIdNotFoundError if not found

- **`resolve_table_name(model: str) -> str`**:
  - Converts Odoo model name to database table name
  - Simple transformation: replace `.` with `_` (e.g., "ir.mail_server" → "ir_mail_server")

**Private Methods:**

- **`_check_odoo_database()`**: Validates `ir_module_module` table exists
- **`_get_odoo_version()`**: Extracts version from base module's `latest_version` field

### 5. Exception Hierarchy ([exceptions.py](confidoo/exceptions.py))

Custom exception classes for error handling:

**Configuration Exceptions:**
- **`ConfidooError`**: Base exception for all Confidoo errors
- **`ConfigParseError`**: Raised when configuration parsing fails
- **`InvalidSectionError`**: Raised when section syntax is invalid

**Database Exceptions:**
- **`DatabaseError`**: Base exception for database operations
- **`DatabaseConnectionError`**: Connection to database failed
- **`NotOdooDatabaseError`**: Database validation failed (missing `ir_module_module` table)
- **`OdooVersionError`**: Version detection failed
- **`XmlIdNotFoundError`**: XMLID resolution failed (record not found in `ir_model_data`)
- **`TransactionError`**: Transaction operation failed

### 4. Utilities ([utils/](confidoo/utils/))

#### Exception Handler ([utils/errors.py](confidoo/utils/errors.py))

**`handle_exceptions()` Decorator**

Provides unified exception handling for CLI commands, which must take the typer context as `ctx`.

**Behavior:**
- In debug mode: Allows exceptions to propagate with full stack traces
- In normal mode: Catches exceptions and displays user-friendly error messages
- Checks both command-level and global debug flags

## Data Flow

The complete flow from configuration file to database commit:

```
┌─────────────────┐
│  Config File    │
│  (INI format)   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│  ConfidooConfigParser   │
│  - Read INI content     │
│  - Validate sections    │
│  - Extract fields       │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  ParsedConfig           │
│  - Ordered operations   │
│    • ModelOperation     │
│    • RecordOperation    │
│    • ConfigParamOperation│
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Confidoo Class         │
│  (main.py)              │
│  - apply_config() or    │
│  - __init__() + apply() │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  OdooDatabase Context   │
│  (db.py)                │
│  - Connect to database  │
│  - Begin transaction    │
│  - Validate Odoo DB     │
│  - Get version          │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Apply Operations       │
│  For each operation:    │
│                         │
│  ModelOperation →       │
│    UPDATE table         │
│    SET fields           │
│                         │
│  RecordOperation →      │
│    resolve_xmlid()      │
│    UPDATE table         │
│    SET fields           │
│    WHERE id = res_id    │
│                         │
│  ConfigParamOperation → │
│    For each param:      │
│    - UPSERT or DELETE   │
│      ir_config_parameter│
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Commit & Cleanup       │
│  - Commit transaction   │
│    (or rollback on err) │
│  - Close connection     │
└─────────────────────────┘
```

## Configuration Format

### Section Syntax

All sections follow the pattern: `[type:identifier]`

Where `type` is one of:
- `model` - Model-wide settings
- `record` - Record-specific settings
- `config` - System parameters

Sections may be repeated (e.g. several `[config:set_param]` sections). Each
occurrence is a separate operation, applied in the order it appears in the file.
Duplicate keys within a single occurrence are an error.

### Special Attributes

- **`_table`**: Specifies custom database table name (for model and record sections only)
  - If not specified, table name is inferred by replacing `.` with `_` in the model name

### Field Values

- Regular values: `field_name = value`
- Empty values (unset): `field_name =` or `field_name`
- Values are stripped of leading/trailing whitespace
- No variable interpolation occurs (values are literal)

## Architectural Patterns

The codebase uses several key design patterns to ensure robustness and clean API design.

### 1. Context Manager for Transaction Management

The `OdooDatabase` class implements the context manager protocol to ensure proper transaction handling:

```python
with confidoo.connect() as db:
    confidoo.apply()
    # Automatic commit on success
    # Automatic rollback on exception
    # Connection cleanup in finally block
```

**Benefits:**
- Automatic commit when operations succeed
- Automatic rollback when exceptions occur
- Guaranteed connection cleanup
- No manual transaction management needed

### 2. Property Validation Pattern

Properties with lazy validation provide clear error messages when accessed before initialization:

```python
@property
def config(self) -> ParsedConfig:
    if self._config is None:
        raise RuntimeError("No configuration loaded. Call load_config() first.")
    return self._config
```

**Used in:**
- `Confidoo.config` - Ensures config is loaded before apply()
- `Confidoo.db` - Ensures connection active before database operations
- `OdooDatabase.cr` - Ensures cursor exists before SQL operations

**Benefits:**
- Type-safe return values (no Optional types needed)
- Clear error messages guide users to correct usage
- Centralized validation logic

### 3. Operation Dispatch Pattern

The `_apply_operation()` method uses isinstance checks for type-based dispatch:

```python
def _apply_operation(self, operation: ConfigOperation) -> None:
    if isinstance(operation, ModelOperation):
        self._apply_model_operation(operation)
    elif isinstance(operation, RecordOperation):
        self._apply_record_operation(operation)
    elif isinstance(operation, ConfigParamOperation):
        self._apply_config_param_operation(operation)
```

**Benefits:**
- Extensible for new operation types
- Type-safe dispatch
- Clear separation of concerns

### 4. Direct Cursor Access Pattern

The `cr` property provides direct access to psycopg2 cursor for SQL operations:

```python
self.db.cr.execute(query, values)
rows_affected = self.db.cr.rowcount
```

**Benefits:**
- Full access to psycopg2 cursor API
- No wrapper methods needed
- Follows Odoo's familiar `self.env.cr` pattern
- Efficient - no method call overhead

## Extension Points

### Adding New Operation Types

To add a new operation type:

1. Add enum value to `OperationType`
2. Create new operation class inheriting from `ConfigOperation`
3. Update section pattern regex if needed
4. Add parsing logic in `ConfidooConfigParser._parse_section()`
5. Add handler method in `Confidoo` class (e.g., `_apply_new_operation()`)
6. Update `_apply_operation()` dispatcher with isinstance check

### Custom Field Processing

Field extraction logic is centralized in `ConfidooConfigParser._extract_fields()`. To add custom field processing:

1. Check for special field names (like `_table`)
2. Apply custom validation or transformation
3. Store in appropriate attribute (fields dict or separate attribute)

## Testing

Test files are located in [tests/](tests/):
- [test_parser.py](tests/test_parser.py) - Configuration parser tests

Tests use pytest framework and can be run with:
```bash
uv run pytest
```

## Future Development

### Completed Features

✓ **Database Application Logic**: Fully implemented in `Confidoo` class with handlers for all three operation types
✓ **Transaction Management**: Automatic commit/rollback via `OdooDatabase` context manager
✓ **Row Count Reporting**: Operations report number of rows affected

### Planned Features

1. **Schema Validation**: Pre-application validation of operations against database schema
   - Verify fields exist in target model
   - Validate field types match provided values
   - Check for required fields

2. **Dry-run Mode**: Preview changes without applying them
   - Show SQL statements that would be executed
   - Display affected records count estimation
   - Useful for testing configuration files

3. **Change History Tracking**: Track applied changes for auditing and rollback
   - Store before/after values
   - Record timestamp and user
   - Enable selective rollback beyond transaction-level

4. **Backup/Restore**: Automatic backup before applying changes
   - Create database backup or affected tables backup
   - Restore on failure
   - Configurable backup retention

5. **Multi-database Support**: Apply same configuration to multiple databases
   - Parallel or sequential execution
   - Aggregate results and errors
   - Useful for managing multiple Odoo instances

### Architectural Considerations

- **Ordered Operations**: The parser maintains strict ordering of operations to ensure correct application sequence. Repeated sections are kept as separate operations at their position in the file, rather than merged
- **Immutable Operations**: All operation classes are frozen dataclasses to prevent accidental modification
- **Separation of Concerns**: The design separates parsing (config.py), database (db.py), and application logic (main.py)
- **PostgreSQL-Specific**: Current implementation uses PostgreSQL-specific features (UPSERT with ON CONFLICT)
  - Future: Could be abstracted for different database backends
- **Property-Based Validation**: Properties ensure correct API usage at runtime with clear error messages
- **Context Manager Pattern**: Ensures proper resource cleanup and transaction management
- **Direct Cursor Access**: No abstraction layer over psycopg2 for maximum flexibility

## Development Setup

1. Install with uv: `uv tool install git+https://github.com/camptocamp/confidoo`
2. Run tests: `uv run pytest`
3. Enable debug mode: `confidoo --debug apply <config.ini>`

## Related Documentation

- [README.md](README.md) - User guide and installation instructions
- [LICENSE](LICENSE) - AGPL-3.0 license
