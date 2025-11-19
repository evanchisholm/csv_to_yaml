# CSV to YAML Converter

Small CLI that turns any headered CSV file into a YAML document. It accepts two
positional arguments: the input CSV path and the destination YAML path.

## Requirements

- Python 3.14+ (managed automatically when using `uv run`).
- `pyyaml` (declared in `pyproject.toml`).

## Usage

```bash
uv run main.py <input.csv> <output.yaml>
```

The converter preserves the CSV header names as YAML keys and writes a list of
row dictionaries. CSV values remain strings to avoid unintended type coercion.

## Example

A sample CSV is available under `examples/sample.csv`. Convert it with:

```bash
uv run main.py examples/sample.csv examples/sample.yaml
```

The generated YAML looks like:

```yaml
- name: Alice
	email: alice@example.com
	age: '30'
- name: Bob
	email: bob@example.com
	age: '25'
```
