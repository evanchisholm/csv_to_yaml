"""Batch convert files of a specified type in a folder using a convert function."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

from main import build_schema, convert_csv_to_yaml, derive_schema_path, write_schema


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch convert files of a specified type in a folder."
    )
    parser.add_argument(
        "folder",
        type=Path,
        help="Path to the folder containing files to convert.",
    )
    parser.add_argument(
        "--extension",
        "-e",
        type=str,
        default="csv",
        help="File extension to filter by (default: csv). Include the dot if needed (e.g., '.csv').",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        help="Output directory for converted files (default: same as input folder).",
    )
    parser.add_argument(
        "--schema",
        "-s",
        action="store_true",
        help="Generate JSON Schema files alongside YAML files.",
    )
    parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        help="Recursively search subdirectories.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be converted without actually converting.",
    )
    return parser.parse_args()


def normalize_extension(ext: str) -> str:
    """Normalize extension to always start with a dot."""
    if not ext.startswith("."):
        return f".{ext.lower()}"
    return ext.lower()


def find_files_by_extension(
    folder: Path, extension: str, recursive: bool = False
) -> list[Path]:
    """Find all files with the specified extension in the folder.
    
    Args:
        folder: Directory to search in
        extension: File extension to match (e.g., '.csv')
        recursive: Whether to search subdirectories recursively
    
    Returns:
        List of matching file paths, sorted by name
    """
    extension = normalize_extension(extension)
    files: list[Path] = []
    
    if recursive:
        pattern = f"**/*{extension}"
        files = sorted(folder.glob(pattern))
    else:
        pattern = f"*{extension}"
        files = sorted(folder.glob(pattern))
    
    # Filter to only include files (not directories)
    return [f for f in files if f.is_file()]


def convert_file(
    input_file: Path,
    output_dir: Path,
    generate_schema: bool = True,
    overwrite: bool = False,
    dry_run: bool = False,
) -> bool:
    """Convert a single CSV file to YAML (and optionally schema).
    
    Args:
        input_file: Path to the input CSV file
        output_dir: Directory for output files
        generate_schema: Whether to generate a JSON Schema file
        overwrite: Whether to overwrite existing files
        dry_run: If True, only print what would be done
    
    Returns:
        True if conversion was successful (or would be in dry-run mode), False otherwise
    """
    # Determine output file paths
    yaml_file = output_dir / f"{input_file.stem}.yaml"
    schema_file = output_dir / f"{input_file.stem}.schema.json"
    
    # Check if files already exist
    if yaml_file.exists() and not overwrite:
        print(f"  ⏭️  Skipped (YAML already exists): {yaml_file.name}")
        return True
    
    if schema_file.exists() and generate_schema and not overwrite:
        print(f"  ⏭️  Skipped (Schema already exists): {schema_file.name}")
        return True
    
    if dry_run:
        print(f"  📝 Would convert: {input_file.name} -> {yaml_file.name}")
        if generate_schema:
            print(f"  📝 Would generate: {schema_file.name}")
        return True
    
    try:
        # Convert CSV to YAML
        rows, fieldnames = convert_csv_to_yaml(input_file, yaml_file)
        print(f"  ✓ Converted: {yaml_file.name} ({len(rows)} rows)")
        
        # Generate schema if requested
        if generate_schema:
            schema = build_schema(fieldnames)
            write_schema(schema, schema_file)
            print(f"  ✓ Generated schema: {schema_file.name}")
        
        return True
    
    except FileNotFoundError as e:
        print(f"  ✗ Error: {e}", file=sys.stderr)
        return False
    except ValueError as e:
        print(f"  ✗ Error: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  ✗ Unexpected error: {e}", file=sys.stderr)
        return False


def batch_convert(
    folder: Path,
    extension: str = "csv",
    output_dir: Path | None = None,
    generate_schema: bool = True,
    recursive: bool = False,
    overwrite: bool = False,
    dry_run: bool = False,
    convert_func: Callable | None = None,
) -> tuple[int, int]:
    """Batch convert files of a specified type in a folder.
    
    Args:
        folder: Directory containing files to convert
        extension: File extension to filter by (e.g., 'csv' or '.csv')
        output_dir: Output directory (default: same as input folder)
        generate_schema: Whether to generate JSON Schema files
        recursive: Whether to search subdirectories recursively
        overwrite: Whether to overwrite existing files
        dry_run: If True, only show what would be converted
        convert_func: Optional custom convert function (uses default CSV converter if None)
    
    Returns:
        Tuple of (success_count, total_count)
    """
    if not folder.is_dir():
        raise NotADirectoryError(f"Folder not found: {folder}")
    
    # Determine output directory
    if output_dir is None:
        output_dir = folder
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
    
    # Find matching files
    files = find_files_by_extension(folder, extension, recursive)
    
    if not files:
        ext = normalize_extension(extension)
        print(f"No {ext} files found in {folder}")
        if recursive:
            print("(including subdirectories)")
        return 0, 0
    
    print(f"Found {len(files)} {normalize_extension(extension)} file(s) to process")
    if dry_run:
        print("DRY RUN MODE - No files will be modified")
    print()
    
    success_count = 0
    total_count = len(files)
    
    for i, file_path in enumerate(files, 1):
        print(f"[{i}/{total_count}] Processing: {file_path.name}")
        
        # Use custom convert function if provided, otherwise use default
        if convert_func:
            try:
                result = convert_func(file_path, output_dir, generate_schema, overwrite, dry_run)
                if result:
                    success_count += 1
            except Exception as e:
                print(f"  ✗ Error: {e}", file=sys.stderr)
        else:
            # Use default CSV converter
            if convert_file(file_path, output_dir, generate_schema, overwrite, dry_run):
                success_count += 1
        
        print()
    
    return success_count, total_count


def main() -> None:
    args = parse_args()
    
    try:
        success_count, total_count = batch_convert(
            folder=args.folder,
            extension=args.extension,
            output_dir=args.output_dir,
            generate_schema=args.schema,
            recursive=args.recursive,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )
        
        print("=" * 60)
        print(f"Summary: {success_count}/{total_count} files processed successfully")
        
        if success_count < total_count:
            sys.exit(1)
        sys.exit(0)
    
    except NotADirectoryError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

