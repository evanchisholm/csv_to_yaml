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
    check_constraints: List[str] = field(default_factory=list)  # Column-level CHECK constraints


@dataclass
class ForeignKey:
    """Represents a foreign key relationship."""

    from_table: str
    from_columns: List[str]
    to_table: str
    to_columns: List[str]
    constraint_name: str


@dataclass
class CheckConstraint:
    """Represents a CHECK constraint."""

    name: Optional[str] = None
    expression: str = ""


@dataclass
class Table:
    """Represents a database table with its columns and relationships."""

    name: str
    schema: str = "public"
    columns: List[Column] = field(default_factory=list)
    primary_key_columns: List[str] = field(default_factory=list)
    foreign_keys: List[ForeignKey] = field(default_factory=list)
    check_constraints: List[CheckConstraint] = field(default_factory=list)  # Table-level CHECK constraints
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

        # Extract CHECK constraints from ALTER TABLE statements
        self._parse_alter_table_check_constraints(normalized)

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
                table.check_constraints = self._parse_table_check_constraints(table_def)

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

            # Extract column-level CHECK constraints (inline)
            check_constraints = self._extract_column_check_constraints(col_def)

            columns.append(
                Column(
                    name=col_name,
                    data_type=data_type,
                    is_nullable=is_nullable,
                    default_value=default_value,
                    is_unique=is_unique,
                    check_constraints=check_constraints,
                )
            )

        return columns

    def _extract_column_check_constraints(self, col_def: str) -> List[str]:
        """Extract inline CHECK constraints from a column definition.
        
        Handles nested parentheses in CHECK expressions.
        """
        check_constraints = []
        # Find all CHECK keywords
        check_pattern = r"CHECK\s*\("
        matches = list(re.finditer(check_pattern, col_def, re.IGNORECASE))
        
        for match in matches:
            # Start after the opening parenthesis
            start_pos = match.end()
            paren_depth = 1
            i = start_pos
            
            # Find the matching closing parenthesis
            while i < len(col_def) and paren_depth > 0:
                if col_def[i] == '(':
                    paren_depth += 1
                elif col_def[i] == ')':
                    paren_depth -= 1
                i += 1
            
            if paren_depth == 0:
                expression = col_def[start_pos:i-1].strip()
                check_constraints.append(expression)
        
        return check_constraints

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

    def _parse_table_check_constraints(self, table_def: str) -> List[CheckConstraint]:
        """Parse table-level CHECK constraints from a table definition.
        
        Table-level CHECK constraints are separate CONSTRAINT clauses,
        not inline with column definitions. These appear at the bottom of
        CREATE TABLE blocks as standalone CONSTRAINT definitions.
        """
        check_constraints = []
        # Split table definition to get individual parts
        parts = self._split_table_definition(table_def)
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # Look for standalone CHECK constraints (not inline with columns)
            # Pattern: CONSTRAINT name CHECK (expression) or just CHECK (expression)
            # Check if this part starts with CONSTRAINT or CHECK
            check_match = re.match(
                r"^(?:CONSTRAINT\s+(\w+)\s+)?CHECK\s*\(",
                part,
                re.IGNORECASE
            )
            
            if check_match:
                constraint_name = check_match.group(1)
                # Extract expression with balanced parentheses
                # Find the opening parenthesis after CHECK
                expression_start = part.find('(', check_match.end() - 1)
                if expression_start != -1:
                    paren_depth = 0
                    i = expression_start
                    while i < len(part):
                        if part[i] == '(':
                            paren_depth += 1
                        elif part[i] == ')':
                            paren_depth -= 1
                            if paren_depth == 0:
                                expression = part[expression_start+1:i].strip()
                                check_constraints.append(
                                    CheckConstraint(
                                        name=constraint_name,
                                        expression=expression
                                    )
                                )
                                break
                        i += 1
        
        return check_constraints

    def _parse_alter_table_foreign_keys(self, sql: str) -> None:
        """Parse FOREIGN KEY constraints added via ALTER TABLE statements.
        
        Handles both single-line and multi-line ALTER TABLE statements,
        including when all ALTER TABLE statements are grouped at the end of the file.
        Also handles cases where ALTER TABLE and ADD CONSTRAINT are on separate lines.
        """
        # Find ALTER TABLE statements - handle multi-line format including ALTER TABLE ONLY
        alter_table_pattern = r"ALTER\s+TABLE\s+(?:ONLY\s+)?(?:(\w+)\.)?(\w+)\s+(?:IF\s+EXISTS\s+)?"
        alter_matches = list(re.finditer(alter_table_pattern, sql, re.IGNORECASE | re.DOTALL))

        for alter_match in alter_matches:
            table_schema = alter_match.group(1) or "public"
            table_name = alter_match.group(2)
            alter_start = alter_match.end()
            
            # Look for ADD CONSTRAINT ... FOREIGN KEY ... after this ALTER TABLE
            # This might be on the same line or following lines (within reasonable distance)
            search_window = sql[alter_start:alter_start + 2000]  # Search within 2000 chars
            
            # Find ADD CONSTRAINT pattern (may be on same or next line)
            add_constraint_match = re.search(
                r"ADD\s+CONSTRAINT\s+(\w+)\s+",
                search_window,
                re.IGNORECASE | re.DOTALL
            )
            
            if not add_constraint_match:
                continue
            
            constraint_name = add_constraint_match.group(1)
            constraint_start = alter_start + add_constraint_match.end()
            
            # Look for FOREIGN KEY after the constraint name
            fk_search_window = sql[constraint_start:constraint_start + 1000]
            fk_match = re.search(
                r"FOREIGN\s+KEY\s*\(\s*([^)]+)\s*\)\s*"
                r"REFERENCES\s+(?:(\w+)\.)?(\w+)\s*\(\s*([^)]+)\s*\)"
                r"(?:\s+ON\s+DELETE\s+\w+)?",
                fk_search_window,
                re.IGNORECASE | re.DOTALL
            )
            
            if fk_match:
                from_cols_str = fk_match.group(1)
                ref_schema = fk_match.group(2) or "public"
                ref_table = fk_match.group(3)
                to_cols_str = fk_match.group(4)

                from_cols = [col.strip().strip('"') for col in from_cols_str.split(",")]
                to_cols = [col.strip().strip('"') for col in to_cols_str.split(",")]

                full_table_name = f"{table_schema}.{table_name}" if table_schema != "public" else table_name
                ref_table_full = f"{ref_schema}.{ref_table}" if ref_schema != "public" else ref_table

                # Only add if table exists (tables should be parsed first)
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

    def _parse_alter_table_check_constraints(self, sql: str) -> None:
        """Parse CHECK constraints added via ALTER TABLE statements.
        
        Handles both single-line and multi-line ALTER TABLE statements,
        including when all ALTER TABLE statements are grouped at the end of the file.
        Handles nested parentheses in CHECK expressions.
        """
        # Match ALTER TABLE ... ADD (CONSTRAINT ...)? CHECK ...
        alter_pattern = (
            r"ALTER\s+TABLE\s+(?:(\w+)\.)?(\w+)\s+"
            r"ADD\s+(?:CONSTRAINT\s+(\w+)\s+)?CHECK\s*\("
        )
        matches = re.finditer(alter_pattern, sql, re.IGNORECASE | re.DOTALL)

        for match in matches:
            table_schema = match.group(1) or "public"
            table_name = match.group(2)
            constraint_name = match.group(3)
            
            # Find the matching closing parenthesis for the CHECK expression
            start_pos = match.end()  # Position after opening parenthesis
            paren_depth = 1
            i = start_pos
            
            while i < len(sql) and paren_depth > 0:
                if sql[i] == '(':
                    paren_depth += 1
                elif sql[i] == ')':
                    paren_depth -= 1
                i += 1
            
            if paren_depth == 0:
                expression = sql[start_pos:i-1].strip()
                
                full_table_name = f"{table_schema}.{table_name}" if table_schema != "public" else table_name
                
                # Only add if table exists
                if full_table_name in self.tables:
                    check_constraint = CheckConstraint(
                        name=constraint_name,
                        expression=expression
                    )
                    self.tables[full_table_name].check_constraints.append(check_constraint)

    def _parse_indexes(self, sql: str) -> None:
        """Parse CREATE INDEX statements.
        
        Handles both single-line and multi-line CREATE INDEX statements,
        including when all CREATE INDEX statements are grouped at the end of the file.
        Also handles USING clauses (e.g., USING btree, USING gin, USING gist).
        PostgreSQL syntax formats:
        - CREATE INDEX name ON table (columns)
        - CREATE INDEX name ON table USING method (columns)
        - CREATE INDEX name ON table USING method(expression)
        """
        # Find CREATE INDEX statements - handle both formats
        # Pattern 1: Standard format with columns in parentheses
        index_pattern1 = (
            r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?(?:\w+\.)?(\w+)\s+"
            r"ON\s+(?:ONLY\s+)?(?:(\w+)\.)?(\w+)\s+"
            r"(?:USING\s+(\w+)\s+)?"
            r"\("
        )
        matches = re.finditer(index_pattern1, sql, re.IGNORECASE | re.DOTALL)

        for match in matches:
            index_name = match.group(1)
            schema = match.group(2) or "public"
            table_name = match.group(3)
            using_clause = match.group(4)  # USING clause before column list
            start_pos = match.end()  # Position after opening parenthesis
            
            # Extract column list/expression with balanced parentheses
            paren_depth = 1
            i = start_pos
            while i < len(sql) and paren_depth > 0:
                if sql[i] == '(':
                    paren_depth += 1
                elif sql[i] == ')':
                    paren_depth -= 1
                i += 1
            
            if paren_depth == 0:
                columns = sql[start_pos:i-1].strip()  # Exclude the closing parenthesis
                
                # Check if there's a USING clause after the column list
                if not using_clause:
                    remaining = sql[i:i+200].strip()  # Look ahead a bit for USING clause
                    using_match = re.match(r"^\s*USING\s+(\w+)", remaining, re.IGNORECASE)
                    if using_match:
                        using_clause = using_match.group(1)
                
                # Build index description
                index_desc = f"{index_name} ({columns})"
                if using_clause:
                    index_desc += f" USING {using_clause}"
                
                full_table_name = f"{schema}.{table_name}" if schema != "public" else table_name
                if full_table_name in self.tables:
                    self.tables[full_table_name].indexes.append(index_desc)
        
        # Pattern 2: Handle USING method(expression) format where USING method directly precedes parentheses
        index_pattern2 = (
            r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?(?:\w+\.)?(\w+)\s+"
            r"ON\s+(?:ONLY\s+)?(?:(\w+)\.)?(\w+)\s+"
            r"USING\s+(\w+)\("
        )
        matches2 = re.finditer(index_pattern2, sql, re.IGNORECASE | re.DOTALL)

        for match in matches2:
            index_name = match.group(1)
            schema = match.group(2) or "public"
            table_name = match.group(3)
            using_clause = match.group(4)
            start_pos = match.end()  # Position after opening parenthesis after USING method
            
            # Extract expression with balanced parentheses
            paren_depth = 1
            i = start_pos
            while i < len(sql) and paren_depth > 0:
                if sql[i] == '(':
                    paren_depth += 1
                elif sql[i] == ')':
                    paren_depth -= 1
                i += 1
            
            if paren_depth == 0:
                expression = sql[start_pos:i-1].strip()
                
                # Build index description
                index_desc = f"{index_name} ({expression}) USING {using_clause}"
                
                full_table_name = f"{schema}.{table_name}" if schema != "public" else table_name
                if full_table_name in self.tables:
                    self.tables[full_table_name].indexes.append(index_desc)

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


def _make_anchor_id(text: str) -> str:
    """Convert text to a markdown/anchor-friendly ID."""
    # Convert to lowercase, replace spaces and dots with hyphens, remove special chars
    import re
    anchor = text.lower()
    anchor = re.sub(r'[^\w\s-]', '', anchor)  # Remove special chars except word chars, spaces, hyphens
    anchor = re.sub(r'[\s._]+', '-', anchor)  # Replace spaces, dots, underscores with hyphens
    anchor = re.sub(r'-+', '-', anchor)  # Collapse multiple hyphens
    anchor = anchor.strip('-')  # Remove leading/trailing hyphens
    return anchor


def _generate_plantuml_diagram(tables: Dict[str, Table]) -> List[str]:
    """Generate PlantUML entity-relationship diagram showing parent-to-child relationships."""
    lines = []
    
    lines.append("@startuml")
    lines.append("!theme plain")
    lines.append("skinparam linetype ortho")
    lines.append("")
    
    # Define all entities (tables) with their primary keys
    for table_name in sorted(tables.keys()):
        table = tables[table_name]
        # Clean table name for PlantUML (remove schema prefix if present)
        clean_name = table_name.split('.')[-1] if '.' in table_name else table_name
        
        lines.append(f"entity \"{clean_name}\" as {clean_name.replace('.', '_')} {{")
        
        # Add primary key columns
        if table.primary_key_columns:
            for pk_col in table.primary_key_columns:
                # Find the column to get its type
                col = next((c for c in table.columns if c.name == pk_col), None)
                col_type = col.data_type if col else "INTEGER"
                lines.append(f"  * {pk_col} : {col_type} <<PK>>")
        
        # Add foreign key columns (but not if they're already PKs)
        for fk in table.foreign_keys:
            for fk_col in fk.from_columns:
                if fk_col not in table.primary_key_columns:
                    # Find the column to get its type
                    col = next((c for c in table.columns if c.name == fk_col), None)
                    col_type = col.data_type if col else "INTEGER"
                    lines.append(f"  - {fk_col} : {col_type} <<FK>>")
        
        lines.append("}")
        lines.append("")
    
    # Define relationships
    for table_name in sorted(tables.keys()):
        table = tables[table_name]
        from_clean = table_name.split('.')[-1] if '.' in table_name else table_name
        from_entity = from_clean.replace('.', '_')
        
        for fk in sorted(table.foreign_keys, key=lambda x: x.from_columns[0]):
            to_clean = fk.to_table.split('.')[-1] if '.' in fk.to_table else fk.to_table
            to_entity = to_clean.replace('.', '_')
            
            from_cols = ", ".join(fk.from_columns)
            to_cols = ", ".join(fk.to_columns)
            
            # Determine relationship cardinality
            # For now, use many-to-one (child to parent)
            # Format: Entity1 ||--o{ Entity2 (one-to-many from parent to child)
            lines.append(f"{to_entity} ||--o{{ {from_entity} : \"{from_cols} → {to_cols}\"")
    
    lines.append("")
    lines.append("@enduml")
    
    return lines


def _build_relationship_tree(tables: Dict[str, Table]) -> Dict[str, List[tuple]]:
    """Build a tree structure of parent-to-child relationships.
    
    Returns:
        Dictionary mapping parent table names to list of (child_table, fk_info) tuples
    """
    tree: Dict[str, List[tuple]] = {}
    
    for table_name, table in tables.items():
        for fk in table.foreign_keys:
            parent_table = fk.to_table
            child_table = fk.from_table
            fk_info = {
                'from_cols': fk.from_columns,
                'to_cols': fk.to_columns,
                'constraint': fk.constraint_name
            }
            
            if parent_table not in tree:
                tree[parent_table] = []
            tree[parent_table].append((child_table, fk_info))
    
    return tree


def _generate_ascii_relationship_diagram(tables: Dict[str, Table]) -> List[str]:
    """Generate ASCII art diagram showing parent-to-child relationships."""
    lines = []
    
    # Build relationship tree
    tree = _build_relationship_tree(tables)
    
    if not tree:
        lines.append("No relationships defined.")
        return lines
    
    # Find all child tables (tables that reference other tables)
    all_child_tables = set()
    for children in tree.values():
        for child_table, _ in children:
            all_child_tables.add(child_table)
    
    # Root tables are those that are parents but not children (in other relationships)
    # This excludes self-references from being considered "children"
    root_tables = []
    for parent_table in sorted(tree.keys()):
        # Check if this table is a child in any NON-self relationship
        is_child = False
        for other_parent, children_list in tree.items():
            if other_parent != parent_table:  # Exclude self-references
                for child_table, _ in children_list:
                    if child_table == parent_table:
                        is_child = True
                        break
                if is_child:
                    break
        
        if not is_child:
            root_tables.append(parent_table)
    
    # If no clear roots found, use all parent tables as roots
    if not root_tables:
        root_tables = sorted(tree.keys())
    
    def draw_table_name(table_name: str, prefix: str = "") -> str:
        """Draw table name."""
        return prefix + table_name
    
    def draw_vertical_line(prefix: str) -> str:
        """Draw vertical connector line."""
        return prefix + "│"
    
    def draw_branch_connector(is_last: bool, prefix: str = "") -> str:
        """Draw branch connector (├── or └──)."""
        if is_last:
            return prefix + "└── "
        else:
            return prefix + "├── "
    
    def draw_relationships(parent: str, visited: set, prefix: str = "", is_last: bool = True, depth: int = 0, show_table_name: bool = True):
        """Recursively draw relationships from a parent table.
        
        Args:
            parent: Table name to draw
            visited: Set of already visited tables (to avoid cycles)
            prefix: String prefix for indentation
            is_last: Whether this is the last child in its parent's list
            depth: Current depth in the tree
            show_table_name: Whether to show the table name (False when already shown in branch)
        """
        if parent not in tables:
            return
        
        if parent in visited and depth > 0:
            # Show reference but don't recurse to avoid infinite loops (self-references)
            # Don't show table name again, just the reference
            return
        
        visited.add(parent)
        
        # Draw the parent table name if needed
        if show_table_name:
            table_line = draw_table_name(parent, prefix)
            lines.append(table_line)
        
        # Get children
        if parent in tree:
            children = tree[parent]
            # Sort children for consistent output
            children = sorted(children, key=lambda x: x[0])
            
            for idx, (child_table, fk_info) in enumerate(children):
                is_last_child = (idx == len(children) - 1)
                
                # Determine prefix for connectors
                if is_last and not show_table_name:
                    # If parent wasn't shown, adjust prefix
                    connector_prefix = prefix
                    child_prefix = prefix
                elif is_last:
                    connector_prefix = prefix + "    "
                    child_prefix = prefix + "    "
                else:
                    connector_prefix = prefix + "│   "
                    child_prefix = prefix + "│   "
                
                # Check if child has children
                child_has_children = child_table in tree and tree[child_table]
                
                # Determine prefix for child's children
                if is_last_child:
                    new_prefix = prefix + "    "
                else:
                    new_prefix = prefix + "│   "
                
                # Check if this is a self-reference
                is_self_ref = (child_table == parent)
                
                # Show branch with table name and FK relationship
                branch = draw_branch_connector(is_last_child, connector_prefix)
                from_cols = ", ".join(fk_info['from_cols'])
                to_cols = ", ".join(fk_info['to_cols'])
                branch += f"{child_table} ({from_cols} → {to_cols})"
                lines.append(branch)
                
                # Handle self-references
                if is_self_ref:
                    # For self-references, show "... (see above)" and don't recurse
                    lines.append(new_prefix + "... (see above)")
                elif child_has_children:
                    # If child has children, show it as a parent table and then its children
                    child_table_line = draw_table_name(child_table, new_prefix)
                    lines.append(child_table_line)
                    # Recursively draw child relationships
                    draw_relationships(child_table, visited.copy(), new_prefix, is_last_child, depth + 1, show_table_name=False)
    
    # Draw from root tables
    for idx, root in enumerate(root_tables):
        if root in tables:
            draw_relationships(root, set(), "", True, 0)
            if idx < len(root_tables) - 1:
                lines.append("")  # Space between root trees
    
    # Remove the collect_shown code - it's not needed and causes recursion issues
    # The draw_relationships function already handles showing all tables
    
    # Show orphan tables (tables with no relationships)
    all_connected = set()
    for parent in tree.keys():
        all_connected.add(parent)
        for child, _ in tree[parent]:
            all_connected.add(child)
    
    orphan_tables = [t for t in sorted(tables.keys()) if t not in all_connected]
    if orphan_tables:
        lines.append("")
        lines.append("Standalone tables (no relationships):")
        for table in orphan_tables:
            lines.append(table)
    
    return lines


def generate_documentation(tables: Dict[str, Table], output_file: Optional[Path] = None) -> str:
    """Generate markdown documentation for the schema."""
    lines = []
    
    lines.append("# Database Schema Documentation\n")
    
    # Entity Overview with anchor - use HTML heading with ID for better markdown compatibility
    lines.append('<h2 id="table-list">Entity Overview</h2>\n')
    lines.append(f"This schema contains **{len(tables)}** table(s):\n")
    for table_name in sorted(tables.keys()):
        table = tables[table_name]
        pk_info = f" (PK: {', '.join(table.primary_key_columns)})" if table.primary_key_columns else ""
        anchor_id = _make_anchor_id(table_name)
        lines.append(f"- [`{table_name}`](#{anchor_id}){pk_info}")
    lines.append("")

    # Detailed Table Information
    lines.append("## Tables\n")
    for table_name in sorted(tables.keys()):
        table = tables[table_name]
        anchor_id = _make_anchor_id(table_name)
        # Add anchor before heading for markdown compatibility
        lines.append(f'<a name="{anchor_id}"></a>\n')
        lines.append(f"### {table_name}\n")
        
        # Add back to table list link
        lines.append(f"[↑ Back to Table List](#table-list)\n")
        lines.append("")

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

        # Display column-level CHECK constraints
        has_column_checks = any(col.check_constraints for col in table.columns)
        if has_column_checks:
            lines.append("**Column CHECK Constraints:**\n")
            for col in table.columns:
                if col.check_constraints:
                    for check_expr in col.check_constraints:
                        lines.append(f"- `{col.name}`: `{check_expr}`")
            lines.append("")

        # Display table-level CHECK constraints
        if table.check_constraints:
            lines.append("**Table CHECK Constraints:**\n")
            for check_constraint in table.check_constraints:
                if check_constraint.name:
                    lines.append(f"- `{check_constraint.name}`: `{check_constraint.expression}`")
                else:
                    lines.append(f"- `{check_constraint.expression}`")
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

        # Relationship Diagram (PlantUML)
        lines.append("### Relationship Diagram\n")
        lines.append("\nPlantUML Entity-Relationship Diagram:\n")
        lines.append("```plantuml\n")
        diagram_lines = _generate_plantuml_diagram(tables)
        lines.extend(diagram_lines)
        lines.append("```\n")

    doc = "\n".join(lines)
    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(doc, encoding="utf-8")
    return doc


def escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


def generate_confluence_documentation(tables: Dict[str, Table], output_file: Optional[Path] = None) -> str:
    """Generate Confluence-compatible HTML documentation for the schema.
    
    The output is HTML that can be directly pasted into Confluence:
    1. Copy the entire HTML content
    2. In Confluence, click Edit
    3. Click the 'Insert' menu → 'Markup'
    4. Select 'HTML' and paste the content
    Alternatively, some Confluence versions allow pasting HTML directly.
    """
    lines = []
    
    # Wrap in a div for better Confluence compatibility
    lines.append('<div class="confluence-content">')
    lines.append('')
    
    # Title
    lines.append('<h1>Database Schema Documentation</h1>')
    lines.append('')
    
    # Entity Overview with anchor
    lines.append('<h2 id="table-list">Entity Overview</h2>')
    lines.append(f'<p>This schema contains <strong>{len(tables)}</strong> table(s):</p>')
    lines.append('<ul>')
    for table_name in sorted(tables.keys()):
        table = tables[table_name]
        pk_info = f' <em>(PK: {", ".join(table.primary_key_columns)})</em>' if table.primary_key_columns else ""
        table_name_escaped = escape_html(table_name)
        anchor_id = _make_anchor_id(table_name)
        lines.append(f'<li><a href="#{anchor_id}"><code>{table_name_escaped}</code></a>{pk_info}</li>')
    lines.append('</ul>')
    lines.append('')
    
    # Detailed Table Information
    lines.append('<h2>Tables</h2>')
    for table_name in sorted(tables.keys()):
        table = tables[table_name]
        table_name_escaped = escape_html(table_name)
        anchor_id = _make_anchor_id(table_name)
        lines.append(f'<h3 id="{anchor_id}">{table_name_escaped}</h3>')
        lines.append('')
        
        # Add back to table list link
        lines.append('<p>')
        lines.append(f'<a href="#table-list">↑ Back to Table List</a>')
        lines.append('</p>')
        lines.append('')
        
        if table.comment:
            comment_escaped = escape_html(table.comment)
            lines.append(f'<p><em>{comment_escaped}</em></p>')
            lines.append('')
        
        # Columns table
        lines.append('<p><strong>Columns:</strong></p>')
        lines.append('<table class="confluenceTable">')
        lines.append('<tbody>')
        lines.append('<tr><th class="confluenceTh">Column Name</th><th class="confluenceTh">Data Type</th><th class="confluenceTh">Nullable</th><th class="confluenceTh">Default</th><th class="confluenceTh">Constraints</th></tr>')
        
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
            default = escape_html(str(col.default_value)) if col.default_value else "-"
            
            col_name_escaped = escape_html(col.name)
            data_type_escaped = escape_html(col.data_type)
            constraints_escaped = escape_html(constraints_str)
            
            lines.append(
                f'<tr>'
                f'<td class="confluenceTd"><code>{col_name_escaped}</code></td>'
                f'<td class="confluenceTd"><code>{data_type_escaped}</code></td>'
                f'<td class="confluenceTd">{nullable}</td>'
                f'<td class="confluenceTd">{default}</td>'
                f'<td class="confluenceTd">{constraints_escaped}</td>'
                f'</tr>'
            )
        
        lines.append('</tbody>')
        lines.append('</table>')
        lines.append('')
        
        # Column-level CHECK constraints
        has_column_checks = any(col.check_constraints for col in table.columns)
        if has_column_checks:
            lines.append('<p><strong>Column CHECK Constraints:</strong></p>')
            lines.append('<ul>')
            for col in table.columns:
                if col.check_constraints:
                    for check_expr in col.check_constraints:
                        col_name_escaped = escape_html(col.name)
                        check_expr_escaped = escape_html(check_expr)
                        lines.append(f'<li><code>{col_name_escaped}</code>: <code>{check_expr_escaped}</code></li>')
            lines.append('</ul>')
            lines.append('')
        
        # Table-level CHECK constraints
        if table.check_constraints:
            lines.append('<p><strong>Table CHECK Constraints:</strong></p>')
            lines.append('<ul>')
            for check_constraint in table.check_constraints:
                if check_constraint.name:
                    name_escaped = escape_html(check_constraint.name)
                    expr_escaped = escape_html(check_constraint.expression)
                    lines.append(f'<li><code>{name_escaped}</code>: <code>{expr_escaped}</code></li>')
                else:
                    expr_escaped = escape_html(check_constraint.expression)
                    lines.append(f'<li><code>{expr_escaped}</code></li>')
            lines.append('</ul>')
            lines.append('')
        
        # Foreign Keys
        if table.foreign_keys:
            lines.append('<p><strong>Foreign Keys:</strong></p>')
            lines.append('<ul>')
            for fk in table.foreign_keys:
                from_cols = ", ".join(fk.from_columns)
                to_cols = ", ".join(fk.to_columns)
                from_cols_escaped = escape_html(from_cols)
                to_table_escaped = escape_html(fk.to_table)
                to_cols_escaped = escape_html(to_cols)
                constraint_name_escaped = escape_html(fk.constraint_name)
                lines.append(
                    f'<li><code>{from_cols_escaped}</code> → '
                    f'<code>{to_table_escaped}.{to_cols_escaped}</code> '
                    f'(constraint: <code>{constraint_name_escaped}</code>)</li>'
                )
            lines.append('</ul>')
            lines.append('')
        
        # Indexes
        if table.indexes:
            lines.append('<p><strong>Indexes:</strong></p>')
            lines.append('<ul>')
            for idx in table.indexes:
                idx_escaped = escape_html(idx)
                lines.append(f'<li><code>{idx_escaped}</code></li>')
            lines.append('</ul>')
            lines.append('')
        
        lines.append('<hr>')
        lines.append('')
    
    # Relationships Summary
    lines.append('<h2>Relationships</h2>')
    if not any(table.foreign_keys for table in tables.values()):
        lines.append('<p>No foreign key relationships defined.</p>')
    else:
        lines.append('<h3>Foreign Key Relationships</h3>')
        lines.append('<table class="confluenceTable">')
        lines.append('<tbody>')
        lines.append('<tr><th class="confluenceTh">From Table</th><th class="confluenceTh">From Columns</th><th class="confluenceTh">To Table</th><th class="confluenceTh">To Columns</th></tr>')
        
        for table_name in sorted(tables.keys()):
            table = tables[table_name]
            for fk in sorted(table.foreign_keys, key=lambda x: x.from_columns[0]):
                from_cols = ", ".join(fk.from_columns)
                to_cols = ", ".join(fk.to_columns)
                from_table_escaped = escape_html(fk.from_table)
                from_cols_escaped = escape_html(from_cols)
                to_table_escaped = escape_html(fk.to_table)
                to_cols_escaped = escape_html(to_cols)
                
                lines.append(
                    f'<tr>'
                    f'<td class="confluenceTd"><code>{from_table_escaped}</code></td>'
                    f'<td class="confluenceTd"><code>{from_cols_escaped}</code></td>'
                    f'<td class="confluenceTd"><code>{to_table_escaped}</code></td>'
                    f'<td class="confluenceTd"><code>{to_cols_escaped}</code></td>'
                    f'</tr>'
                )
        
        lines.append('</tbody>')
        lines.append('</table>')
        lines.append('')
        
        # Relationship Diagram (PlantUML)
        lines.append('<h3>Relationship Diagram</h3>')
        lines.append('<p>PlantUML Entity-Relationship Diagram:</p>')
        lines.append('<pre>')
        diagram_lines = _generate_plantuml_diagram(tables)
        for line in diagram_lines:
            line_escaped = escape_html(line)
            lines.append(line_escaped)
        lines.append('</pre>')
    
    # Close the wrapper div
    lines.append('</div>')
    
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
        choices=["markdown", "text", "confluence"],
        default="markdown",
        help="Output format for documentation (default: markdown). Use 'confluence' for Confluence-compatible HTML.",
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
        elif args.format == "confluence":
            doc = generate_confluence_documentation(tables, args.output)
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

