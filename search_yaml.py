"""Search a YAML file for a specific key-value pair and return count and line numbers."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search a YAML file for a specific key-value pair and return count and line numbers."
    )
    parser.add_argument(
        "yaml_file",
        type=Path,
        help="Path to the YAML file to search.",
    )
    parser.add_argument(
        "key",
        type=str,
        help="The key to search for.",
    )
    parser.add_argument(
        "value",
        type=str,
        help="The value to match.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of human-readable format.",
    )
    return parser.parse_args()


def load_yaml_with_positions(path: Path):
    """Load YAML file with position information preserved."""
    if not path.is_file():
        raise FileNotFoundError(f"YAML file not found: {path}")
    yaml_loader = YAML()
    with path.open(encoding="utf-8") as fh:
        return yaml_loader.load(fh)


def normalize_value(value: any, target_value: str) -> bool:
    """Compare a value with the target value, handling type conversions."""
    # Convert both to string for comparison, but also check for exact type matches
    if isinstance(value, str):
        return value == target_value
    elif isinstance(value, (int, float, bool)):
        # Try to match as string representation
        if str(value) == target_value:
            return True
        # Also try to parse target_value as the same type
        try:
            if isinstance(value, int):
                return value == int(target_value)
            elif isinstance(value, float):
                return value == float(target_value)
            elif isinstance(value, bool):
                # Handle boolean string representations
                if target_value.lower() in ("true", "1", "yes", "on"):
                    return value is True
                elif target_value.lower() in ("false", "0", "no", "off"):
                    return value is False
        except (ValueError, TypeError):
            pass
    return False


def get_line_number_for_key_value(
    parent: CommentedMap, key: str, value: any
) -> int | None:
    """Get the line number for a key-value pair in a CommentedMap.
    
    Args:
        parent: The parent CommentedMap containing the key-value pair
        key: The key to find
        value: The value (used for context, but we match on key position)
    
    Returns:
        Line number (1-indexed) or None if not found
    """
    if not isinstance(parent, CommentedMap) or key not in parent:
        return None
    
    if hasattr(parent, "lc") and parent.lc:
        try:
            # Try to get the key line number
            key_pos = parent.lc.key(key)
            if key_pos:
                return key_pos[0] + 1  # ruamel.yaml uses 0-indexed, convert to 1-indexed
            # Fallback to value line number
            value_pos = parent.lc.value(key)
            if value_pos:
                return value_pos[0] + 1
        except (AttributeError, IndexError, TypeError):
            pass
    
    return None


def search_yaml_for_key_value(
    yaml_file: Path, key: str, value: str
) -> tuple[int, list[int]]:
    """Search a YAML file for a specific key-value pair.
    
    Args:
        yaml_file: Path to the YAML file to search
        key: The key to search for
        value: The value to match
    
    Returns:
        Tuple of (count, line_numbers) where:
        - count: Number of instances found
        - line_numbers: List of line numbers (1-indexed) where matches were found
    """
    yaml_data = load_yaml_with_positions(yaml_file)
    line_numbers: list[int] = []
    
    def search_recursive(data: any, parent: CommentedMap | None = None):
        """Recursively search through YAML data structure."""
        if isinstance(data, CommentedMap):
            # Check if this map has the key-value pair we're looking for
            if key in data and normalize_value(data[key], value):
                line_num = get_line_number_for_key_value(data, key, data[key])
                if line_num is not None:
                    line_numbers.append(line_num)
                else:
                    # Fallback: try to get line number from the map itself
                    if hasattr(data, "lc") and data.lc:
                        try:
                            line_num = data.lc.line + 1
                            if line_num:
                                line_numbers.append(line_num)
                        except (AttributeError, TypeError):
                            pass
            
            # Recursively search all values in this map
            for k, v in data.items():
                search_recursive(v, data)
        
        elif isinstance(data, (CommentedSeq, list)):
            # Recursively search all items in this list
            for item in data:
                search_recursive(item)
        
        elif isinstance(data, dict):
            # Handle plain dict (not CommentedMap)
            if key in data and normalize_value(data[key], value):
                # Try to find line number from parent if available
                if parent and isinstance(parent, CommentedMap):
                    line_num = get_line_number_for_key_value(parent, key, data[key])
                    if line_num is not None:
                        line_numbers.append(line_num)
            
            # Recursively search all values in this dict
            for v in data.values():
                search_recursive(v)
        
        elif isinstance(data, list):
            # Handle plain list (not CommentedSeq)
            for item in data:
                search_recursive(item)
    
    search_recursive(yaml_data)
    
    # Sort and deduplicate line numbers
    line_numbers = sorted(set(line_numbers))
    count = len(line_numbers)
    
    return count, line_numbers


def main() -> None:
    args = parse_args()
    
    try:
        count, line_numbers = search_yaml_for_key_value(args.yaml_file, args.key, args.value)
        
        if args.json:
            import json
            output = {
                "count": count,
                "line_numbers": line_numbers,
                "key": args.key,
                "value": args.value,
                "file": str(args.yaml_file),
            }
            print(json.dumps(output, indent=2))
        else:
            print(f"Found {count} instance(s) of '{args.key}: {args.value}'")
            if count > 0:
                print(f"Line numbers: {', '.join(map(str, line_numbers))}")
        
        sys.exit(0 if count > 0 else 1)
    
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

