# CSV to YAML Converter

Small CLI that turns any headered CSV file into a YAML document and emits a JSON
Schema that describes the resulting YAML structure. The companion
`validate.py` script checks any YAML file against a schema.

## Requirements

- Python 3.14+ (managed automatically when using `uv run`).
- `pyyaml` (declared in `pyproject.toml`).

## Usage

```bash
uv run main.py <input.csv> <output.yaml> [--schema <schema.json>]
```

The converter preserves the CSV header names as YAML keys and writes a list of
row dictionaries. CSV values remain strings to avoid unintended type coercion.
A JSON Schema is written next to the YAML file by default (e.g.
`output.schema.json`), or to the path supplied via `--schema`.

Validate a YAML file against any JSON Schema with:

```bash
uv run validate.py <data.yaml> <schema.json>
```

## Example

A sample CSV is available under `examples/sample.csv`. Convert it (and generate
the schema) with:

```bash
uv run main.py examples/sample.csv examples/sample.yaml --schema examples/sample.schema.json
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

And the corresponding schema resembles:

```json
{
	"$schema": "https://json-schema.org/draft/2020-12/schema",
	"title": "CSV Row",
	"type": "array",
	"items": {
		"type": "object",
		"properties": {
			"name": {"type": "string"},
			"email": {"type": "string"},
			"age": {"type": "string"}
		},
		"required": ["name", "email", "age"],
		"additionalProperties": false
	}
}
```

Validate the sample output with:

```bash
uv run validate.py examples/sample.yaml examples/sample.schema.json
```
