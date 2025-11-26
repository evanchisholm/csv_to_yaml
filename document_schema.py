"""Document PostgreSQL schema entities and relationships from pg_dump schema-only SQL file."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Column:
    """Represents a database column."""

    name: str
    data_type: str
    is_nullable: bool = True
    default_value: Optional[str] = None
    is_primary_key: bool = False
    is_unique: bool = False


@dataclass
class ForeignKey:
    """Represents a foreign key relationship."""

    from_table: str
    from_columns: List[str]
    to_table: str
    to_columns: List[str]
    constraint_name: str


@dataclass
class Table:
    """Represents a database table with its columns and relationships."""

    name: str
    schema: str = "public"
    columns: List[Column] = field(default_factory=list)
    primary_key_columns: List[str] = field(default_factory=list)
    foreign_keys: List[ForeignKey] = field(default_factory=list)
    indexes: List[str] = field(default_factory=list)
    comment: Optional[str] = None


class SchemaParser:
    """Parser for PostgreSQL schema SQL files."""

    def __init__(self, sql_file: Path):
        """Initialize parser with SQL file path."""
        if not sql_file.is_file():
            raise FileNotFoundError(f"SQL file not found: {sql_file}")
        self.sql_file = sql_file
        self.sql_content: str = ""
        self.tables: Dict[str, Table] = {}
        self.relationships: List[ForeignKey] = []

    def parse(self) -> Dict[str, Table]:
        """Parse the SQL file and extract schema information."""
        with self.sql_file.open(encoding="utf-8") as f:
            self.sql_content = f.read()

        # Normalize the SQL content (remove comments, normalize whitespace)
        normalized = self._normalize_sql(self.sql_content)

        # Extract table definitions (includes foreign keys now)
        self._parse_tables(normalized)

        # Extract foreign keys from ALTER TABLE statements
        self._parse_alter_table_foreign_keys(normalized)

        # Extract indexes
        self._parse_indexes(normalized)

        # Extract table comments
        self._parse_table_comments(normalized)

        return self.tables

    def _normalize_sql(self, sql: str) -> str:
        """Normalize SQL content by removing comments and normalizing whitespace."""
        # Remove single-line comments (-- style)
        sql = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
        # Remove multi-line comments (/* */ style)
        sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
        # Normalize whitespace
        sql = re.sub(r"\s+", " ", sql)
        return sql

    def _parse_tables(self, sql: str) -> None:
        """Parse CREATE TABLE statements."""
        # Match CREATE TABLE statements - need to handle nested parentheses correctly
        pattern = r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:(\w+)\.)?(\w+)\s*\((.*?)\)(?:\s*;)?"
        
        # Need to find matching parentheses for table definitions
        i = 0
        while i < len(sql):
            create_match = re.search(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:(\w+)\.)?(\w+)\s*\(", sql[i:], re.IGNORECASE)
            if not create_match:
                break
            
            start_pos = i + create_match.start()
            schema = create_match.group(1) or "public"
            table_name = create_match.group(2)
            
            # Find the matching closing parenthesis for the table definition
            paren_pos = i + create_match.end() - 1  # Position of opening (
            paren_depth = 1
            j = paren_pos + 1
            
            while j < len(sql) and paren_depth > 0:
                if sql[j] == '(':
                    paren_depth += 1
                elif sql[j] == ')':
                    paren_depth -= 1
                j += 1
            
            if paren_depth == 0:
                table_def = sql[paren_pos + 1:j - 1]
                
                table = Table(name=table_name, schema=schema)
                table.columns = self._parse_columns(table_def)
                table.primary_key_columns = self._extract_primary_key(table_def)
                table.foreign_keys = self._parse_table_foreign_keys(table_def, table_name, schema)

                # Store table with schema-qualified name
                full_name = f"{schema}.{table_name}" if schema != "public" else table_name
                self.tables[full_name] = table
                
                # Also add to relationships list
                for fk in table.foreign_keys:
                    self.relationships.append(fk)
            
            i = j

    def _parse_columns(self, table_def: str) -> List[Column]:
        """Parse column definitions from table definition."""
        columns: List[Column] = []
        # Split by comma, but respect parentheses for complex types
        column_defs = self._split_table_definition(table_def)

        for col_def in column_defs:
            col_def = col_def.strip()
            if not col_def or col_def.upper().startswith(("CONSTRAINT", "PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "CHECK")):
                continue

            # Extract column name
            name_match = re.match(r"^(\w+)", col_def)
            if not name_match:
                continue

            col_name = name_match.group(1)
            rest = col_def[len(col_name):].strip()

            # Extract data type - handle complex types with parentheses
            # Try patterns in order of complexity
            data_type = "unknown"
            type_patterns = [
                (r"^(\w+\s+WITH\s+TIME\s+ZONE)", 20),  # TIMESTAMP WITH TIME ZONE (longest first)
                (r"^(\w+\s*\(\s*\d+(?:\s*,\s*\d+)?\s*\))", 15),  # VARCHAR(50), DECIMAL(10,2)
                (r"^(\w+)", 5),  # Simple types like INTEGER, UUID
            ]
            
            for pattern, _ in sorted(type_patterns, key=lambda x: x[1], reverse=True):
                type_match = re.match(pattern, rest, re.IGNORECASE)
                if type_match:
                    data_type = type_match.group(1).strip()
                    break

            # Check for constraints in the full column definition
            is_nullable = "NOT NULL" not in col_def.upper()
            is_unique = "UNIQUE" in col_def.upper()

            # Extract default value - handle function calls and complex expressions
            # Look for DEFAULT keyword and extract what follows until next constraint/keyword
            default_match = re.search(
                r"DEFAULT\s+((?:(?:[^,\s]+|\([^)]*\))(?:\s|,|$))*)",
                col_def,
                re.IGNORECASE
            )
            if default_match:
                default_str = default_match.group(1).strip()
                # Remove trailing keywords that might have been captured
                default_str = re.sub(r'\s+(?:NOT\s+NULL|UNIQUE|CHECK|PRIMARY|FOREIGN|CONSTRAINT).*$', '', default_str, flags=re.IGNORECASE)
                default_str = default_str.strip().rstrip(',')
                # Clean up the default value
                default_value = default_str.strip("'\"")
                # Truncate long defaults
                if len(default_value) > 50:
                    default_value = default_value[:47] + "..."
            else:
                default_value = None

            columns.append(
                Column(
                    name=col_name,
                    data_type=data_type,
                    is_nullable=is_nullable,
                    default_value=default_value,
                    is_unique=is_unique,
                )
            )

        return columns

    def _split_table_definition(self, table_def: str) -> List[str]:
        """Split table definition into individual column/constraint definitions."""
        parts = []
        current = ""
        paren_depth = 0

        for char in table_def:
            if char == "(":
                paren_depth += 1
                current += char
            elif char == ")":
                paren_depth -= 1
                current += char
            elif char == "," and paren_depth == 0:
                parts.append(current.strip())
                current = ""
            else:
                current += char

        if current.strip():
            parts.append(current.strip())

        return parts

    def _extract_primary_key(self, table_def: str) -> List[str]:
        """Extract primary key column names from table definition."""
        # Look for PRIMARY KEY constraint in column definitions
        pk_inline = re.findall(r"(\w+)\s+\w+.*?\bPRIMARY\s+KEY\b", table_def, re.IGNORECASE)
        if pk_inline:
            return pk_inline

        # Look for CONSTRAINT ... PRIMARY KEY (...) definition
        pk_pattern = r"(?:CONSTRAINT\s+\w+\s+)?PRIMARY\s+KEY\s*\(\s*([^)]+)\s*\)"
        pk_match = re.search(pk_pattern, table_def, re.IGNORECASE)
        if pk_match:
            pk_cols_str = pk_match.group(1)
            pk_cols = [col.strip().strip('"') for col in pk_cols_str.split(",")]
            return pk_cols

        return []

    def _parse_table_foreign_keys(self, table_def: str, table_name: str, schema: str) -> List[ForeignKey]:
        """Parse FOREIGN KEY constraints from a table definition."""
        foreign_keys = []
        # Match FOREIGN KEY constraints in the table definition
        fk_pattern = (
            r"(?:CONSTRAINT\s+(\w+)\s+)?FOREIGN\s+KEY\s*\(\s*([^)]+)\s*\)\s*"
            r"REFERENCES\s+(?:(\w+)\.)?(\w+)\s*\(\s*([^)]+)\s*\)"
        )
        matches = re.finditer(fk_pattern, table_def, re.IGNORECASE)

        for match in matches:
            constraint_name = match.group(1) or "unnamed"
            from_cols_str = match.group(2)
            ref_schema = match.group(3) or "public"
            ref_table = match.group(4)
            to_cols_str = match.group(5)

            from_cols = [col.strip().strip('"') for col in from_cols_str.split(",")]
            to_cols = [col.strip().strip('"') for col in to_cols_str.split(",")]

            full_table_name = f"{schema}.{table_name}" if schema != "public" else table_name
            ref_table_full = f"{ref_schema}.{ref_table}" if ref_schema != "public" else ref_table

            fk = ForeignKey(
                from_table=full_table_name,
                from_columns=from_cols,
                to_table=ref_table_full,
                to_columns=to_cols,
                constraint_name=constraint_name,
            )
            foreign_keys.append(fk)

        return foreign_keys

    def _parse_alter_table_foreign_keys(self, sql: str) -> None:
        """Parse FOREIGN KEY constraints added via ALTER TABLE statements."""
        # Match ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY ...
        # Pattern handles both single-line and multi-line ALTER TABLE statements
        alter_pattern = (
            r"ALTER\s+TABLE\s+(?:(\w+)\.)?(\w+)\s+"
            r"ADD\s+CONSTRAINT\s+(\w+)\s+"
            r"FOREIGN\s+KEY\s*\(\s*([^)]+)\s*\)\s*"
            r"REFERENCES\s+(?:(\w+)\.)?(\w+)\s*\(\s*([^)]+)\s*\)"
        )
        matches = re.finditer(alter_pattern, sql, re.IGNORECASE | re.DOTALL)

        for match in matches:
            table_schema = match.group(1) or "public"
            table_name = match.group(2)
            constraint_name = match.group(3)
            from_cols_str = match.group(4)
            ref_schema = match.group(5) or "public"
            ref_table = match.group(6)
            to_cols_str = match.group(7)

            from_cols = [col.strip().strip('"') for col in from_cols_str.split(",")]
            to_cols = [col.strip().strip('"') for col in to_cols_str.split(",")]

            full_table_name = f"{table_schema}.{table_name}" if table_schema != "public" else table_name
            ref_table_full = f"{ref_schema}.{ref_table}" if ref_schema != "public" else ref_table

            # Only add if table exists
            if full_table_name in self.tables:
                fk = ForeignKey(
                    from_table=full_table_name,
                    from_columns=from_cols,
                    to_table=ref_table_full,
                    to_columns=to_cols,
                    constraint_name=constraint_name,
                )
                self.tables[full_table_name].foreign_keys.append(fk)
                self.relationships.append(fk)

    def _parse_indexes(self, sql: str) -> None:
        """Parse CREATE INDEX statements."""
        index_pattern = r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:\w+\.)?(\w+)\s+ON\s+(?:(\w+)\.)?(\w+)\s*\(([^)]+)\)"
        matches = re.finditer(index_pattern, sql, re.IGNORECASE)

        for match in matches:
            index_name = match.group(1)
            schema = match.group(2) or "public"
            table_name = match.group(3)
            columns = match.group(4)

            full_table_name = f"{schema}.{table_name}" if schema != "public" else table_name
            if full_table_name in self.tables:
                self.tables[full_table_name].indexes.append(f"{index_name} ({columns})")

    def _parse_table_comments(self, sql: str) -> None:
        """Parse COMMENT ON TABLE statements."""
        comment_pattern = r"COMMENT\s+ON\s+TABLE\s+(?:(\w+)\.)?(\w+)\s+IS\s+'([^']+)'"
        matches = re.finditer(comment_pattern, sql, re.IGNORECASE)

        for match in matches:
            schema = match.group(1) or "public"
            table_name = match.group(2)
            comment = match.group(3)

            full_table_name = f"{schema}.{table_name}" if schema != "public" else table_name
            if full_table_name in self.tables:
                self.tables[full_table_name].comment = comment


def generate_documentation(tables: Dict[str, Table], output_file: Optional[Path] = None) -> str:
    """Generate markdown documentation for the schema."""
    lines = ["# Database Schema Documentation\n"]

    # Entity Overview
    lines.append("## Entity Overview\n")
    lines.append(f"This schema contains **{len(tables)}** table(s):\n")
    for table_name in sorted(tables.keys()):
        table = tables[table_name]
        pk_info = f" (PK: {', '.join(table.primary_key_columns)})" if table.primary_key_columns else ""
        lines.append(f"- `{table_name}`{pk_info}")
    lines.append("")

    # Detailed Table Information
    lines.append("## Tables\n")
    for table_name in sorted(tables.keys()):
        table = tables[table_name]
        lines.append(f"### {table_name}\n")

        if table.comment:
            lines.append(f"*{table.comment}*\n")

        lines.append("**Columns:**\n")
        lines.append("| Column Name | Data Type | Nullable | Default | Constraints |")
        lines.append("|-------------|-----------|----------|---------|-------------|")

        for col in table.columns:
            constraints = []
            if col.name in table.primary_key_columns:
                constraints.append("PK")
            if col.is_unique:
                constraints.append("UNIQUE")
            if not col.is_nullable and col.name not in table.primary_key_columns:
                constraints.append("NOT NULL")

            constraints_str = ", ".join(constraints) if constraints else "-"
            nullable = "No" if not col.is_nullable else "Yes"
            default = col.default_value or "-"

            lines.append(
                f"| `{col.name}` | `{col.data_type}` | {nullable} | {default} | {constraints_str} |"
            )

        lines.append("")

        # Foreign Keys
        if table.foreign_keys:
            lines.append("**Foreign Keys:**\n")
            for fk in table.foreign_keys:
                from_cols = ", ".join(fk.from_columns)
                to_cols = ", ".join(fk.to_columns)
                lines.append(
                    f"- `{from_cols}` → `{fk.to_table}.{to_cols}` "
                    f"(constraint: `{fk.constraint_name}`)"
                )
            lines.append("")

        # Indexes
        if table.indexes:
            lines.append("**Indexes:**\n")
            for idx in table.indexes:
                lines.append(f"- `{idx}`")
            lines.append("")

        lines.append("---\n")

    # Relationships Summary
    lines.append("## Relationships\n")
    if not any(table.foreign_keys for table in tables.values()):
        lines.append("No foreign key relationships defined.\n")
    else:
        lines.append("### Foreign Key Relationships\n")
        lines.append("| From Table | From Columns | To Table | To Columns |")
        lines.append("|------------|--------------|----------|------------|")

        for table_name in sorted(tables.keys()):
            table = tables[table_name]
            for fk in sorted(table.foreign_keys, key=lambda x: x.from_columns[0]):
                from_cols = ", ".join(fk.from_columns)
                to_cols = ", ".join(fk.to_columns)
                lines.append(f"| `{fk.from_table}` | `{from_cols}` | `{fk.to_table}` | `{to_cols}` |")

        lines.append("")

        # Relationship Graph (textual)
        lines.append("### Relationship Diagram\n")
        lines.append("```\n")
        for table_name in sorted(tables.keys()):
            table = tables[table_name]
            if table.foreign_keys:
                for fk in table.foreign_keys:
                    from_cols = ", ".join(fk.from_columns)
                    to_cols = ", ".join(fk.to_columns)
                    lines.append(f"{fk.from_table} ({from_cols}) --> {fk.to_table} ({to_cols})")
        lines.append("```\n")

    doc = "\n".join(lines)
    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(doc, encoding="utf-8")
    return doc


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Document PostgreSQL schema entities and relationships from pg_dump schema-only SQL file."
    )
    parser.add_argument(
        "sql_file",
        type=Path,
        help="Path to the PostgreSQL schema-only SQL file (from pg_dump --schema-only).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output file path for documentation (default: prints to stdout).",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "text"],
        default="markdown",
        help="Output format for documentation (default: markdown).",
    )
    return parser.parse_args()


def main() -> None:
    """Main entry point."""
    args = parse_args()

    try:
        parser = SchemaParser(args.sql_file)
        tables = parser.parse()

        if args.format == "markdown":
            doc = generate_documentation(tables, args.output)
            if not args.output:
                print(doc)
        else:
            # Simple text format
            lines = [f"Database Schema: {len(tables)} tables\n", "=" * 50, ""]
            for table_name in sorted(tables.keys()):
                table = tables[table_name]
                lines.append(f"\nTable: {table_name}")
                if table.comment:
                    lines.append(f"  Comment: {table.comment}")
                lines.append(f"  Columns ({len(table.columns)}):")
                for col in table.columns:
                    constraints = []
                    if col.name in table.primary_key_columns:
                        constraints.append("PK")
                    if not col.is_nullable:
                        constraints.append("NOT NULL")
                    constraint_str = f" [{', '.join(constraints)}]" if constraints else ""
                    lines.append(f"    - {col.name}: {col.data_type}{constraint_str}")

                if table.foreign_keys:
                    lines.append(f"  Foreign Keys ({len(table.foreign_keys)}):")
                    for fk in table.foreign_keys:
                        from_cols = ", ".join(fk.from_columns)
                        to_cols = ", ".join(fk.to_columns)
                        lines.append(f"    - {from_cols} -> {fk.to_table}.{to_cols}")

            doc = "\n".join(lines)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(doc, encoding="utf-8")
            else:
                print(doc)

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error parsing schema: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

