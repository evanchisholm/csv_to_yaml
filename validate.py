"""Validate a YAML document against a JSON Schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a YAML file against a JSON Schema file."
    )
    parser.add_argument(
        "yaml_file",
        type=Path,
        help="Path to the YAML file to validate.",
    )
    parser.add_argument(
        "schema_file",
        type=Path,
        help="Path to the JSON Schema file.",
    )
    return parser.parse_args()


def load_yaml(path: Path):
    if not path.is_file():
        raise FileNotFoundError(f"YAML file not found: {path}")
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_yaml_with_positions(path: Path):
    """Load YAML file with position information preserved."""
    if not path.is_file():
        raise FileNotFoundError(f"YAML file not found: {path}")
    yaml_loader = YAML()
    with path.open(encoding="utf-8") as fh:
        return yaml_loader.load(fh)


def get_line_number_for_path(yaml_data_with_positions, path: list) -> int | None:
    """Get the line number for a given JSON path in the YAML file.
    
    Args:
        yaml_data_with_positions: YAML data loaded with ruamel.yaml (preserves positions)
        path: JSON path as a list (e.g., [0, 'name'] for first item's 'name' field)
    
    Returns:
        Line number (1-indexed) or None if not found
    """
    if not path:
        return None
    
    try:
        # Navigate to the parent of the target location
        current = yaml_data_with_positions
        parent = None
        key = None
        
        for i, path_key in enumerate(path):
            parent = current
            key = path_key
            
            if isinstance(current, (CommentedSeq, list)):
                if isinstance(path_key, int) and 0 <= path_key < len(current):
                    current = current[path_key]
                else:
                    return None
            elif isinstance(current, (CommentedMap, dict)):
                if path_key in current:
                    current = current[path_key]
                else:
                    return None
            else:
                return None
        
        # If we have a parent that's a CommentedMap and a key, get the line number of that key
        if isinstance(parent, CommentedMap) and isinstance(key, str) and key in parent:
            if hasattr(parent, 'lc') and parent.lc:
                try:
                    # Try to get the key line first, fall back to value line
                    key_pos = parent.lc.key(key)
                    if key_pos:
                        return key_pos[0] + 1  # ruamel.yaml uses 0-indexed, convert to 1-indexed
                    value_pos = parent.lc.value(key)
                    if value_pos:
                        return value_pos[0] + 1
                except (AttributeError, IndexError, TypeError):
                    pass
        
        # If we're at an array element, try to get the line number of that element
        if isinstance(parent, CommentedSeq) and isinstance(key, int) and 0 <= key < len(parent):
            if hasattr(parent, 'lc') and parent.lc:
                try:
                    # For list items, we can get the line number of the item itself
                    item_line = parent.lc.item(key)[0] + 1 if hasattr(parent.lc, 'item') else None
                    if item_line:
                        return item_line
                except (AttributeError, IndexError, TypeError):
                    pass
            
            # Fallback: try to get line number from the element itself if it has lc
            element = parent[key]
            if isinstance(element, (CommentedMap, CommentedSeq)):
                if hasattr(element, 'lc') and element.lc:
                    try:
                        return element.lc.line + 1
                    except (AttributeError, TypeError):
                        pass
        
        # Final fallback: try to get line number from current element
        if isinstance(current, (CommentedMap, CommentedSeq)):
            if hasattr(current, 'lc') and current.lc:
                try:
                    return current.lc.line + 1
                except (AttributeError, TypeError):
                    pass
    except Exception:
        # If anything goes wrong, return None
        pass
    
    return None


def format_path(path: list) -> str:
    """Format a JSON path list into a readable string."""
    if not path:
        return "root"
    
    result = []
    for part in path:
        if isinstance(part, int):
            result.append(f"[{part}]")
        else:
            if result:
                result.append(f".{part}")
            else:
                result.append(str(part))
    
    return "".join(result)


def load_schema(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Schema file not found: {path}")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def validate_yaml(yaml_file: Path, schema_file: Path) -> None:
    data = load_yaml(yaml_file)
    schema = load_schema(schema_file)
    validator = Draft202012Validator(schema)
    validator.validate(data)


def format_validation_error(error: ValidationError, yaml_file: Path) -> str:
    """Format a ValidationError with path and line number information."""
    # Load YAML with positions for line number tracking
    yaml_data_with_positions = load_yaml_with_positions(yaml_file)
    
    path = list(error.absolute_path) if error.absolute_path else []
    path_str = format_path(path)
    line_num = get_line_number_for_path(yaml_data_with_positions, path)
    
    error_msg = f"Validation failed at {path_str}"
    if line_num is not None:
        error_msg += f" (line {line_num})"
    error_msg += f": {error.message}"
    
    return error_msg


def main() -> None:
    args = parse_args()
    try:
        validate_yaml(args.yaml_file, args.schema_file)
    except ValidationError as exc:
        error_msg = format_validation_error(exc, args.yaml_file)
        print(f"Validation failed: {error_msg}", file=sys.stderr)
        sys.exit(1)
    print("Validation succeeded.")


if __name__ == "__main__":
    main()
