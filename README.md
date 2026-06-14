# ExcelQueryAI

ExcelQueryAI is a local Streamlit application that converts natural-language
questions about Excel data into DuckDB SQL using an Ollama model.

The application:

- Reads `.xlsx`, `.xlsm`, and `.xls` files from the `data` folder.
- Loads every workbook sheet as a queryable table.
- Applies optional table names, column names, data types, and descriptions from
  a generated metadata JSON file.
- Recreates a persistent local DuckDB database when requested.
- Uses Ollama and `qwen3.6` to generate read-only SQL.
- Lets you review and edit generated SQL before running it.

## Requirements

- Python 3.10 or newer
- [Ollama](https://ollama.com/)
- The `qwen3.6` Ollama model

## Setup

Clone the repository and enter its directory:

```powershell
git clone https://github.com/anupwadhwani/ExcelQueryAI.git
cd ExcelQueryAI
```

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the Python dependencies:

```powershell
pip install -r requirements.txt
```

Install the Ollama model:

```powershell
ollama pull qwen3.6
```

Make sure Ollama is running before starting the application.

## Add Excel Data

Place one or more Excel files inside:

```text
data/
```

Excel files are intentionally excluded from Git.

Each workbook sheet becomes a DuckDB table. For a workbook with one sheet, the
table name is based on the workbook filename. For workbooks with multiple
sheets, the generated table name includes both the workbook and sheet names.

## Run

Start the Streamlit application from the repository directory:

```powershell
streamlit run app.py
```

Streamlit normally opens:

```text
http://localhost:8501
```

## Application Workflow

1. Click **Generate table and column JSON** to scan the Excel workbooks and
   create `data/excel_metadata.json`.
2. Optionally edit the generated JSON to provide clearer table names, column
   names, data types, and business descriptions.
3. Click **Parse Excel files and recreate database**.
4. Enter a question about the data.
5. Click **Generate SQL**.
6. Review or edit the generated query.
7. Click **Run SQL**.

The database is recreated only when **Parse Excel files and recreate database**
is clicked. Reloading the application does not reparse the Excel files.

## Metadata Format

The generated metadata file uses this structure:

```json
{
  "tables": [
    {
      "table_name": "original_table",
      "new_table_name": "contracts",
      "columns": [
        {
          "column_name": "Agreement Name",
          "new_column_name": "agreement_name",
          "column_data_type": "string",
          "metadata": "Human-readable name of the agreement."
        }
      ]
    }
  ]
}
```

Supported `column_data_type` values include:

- `string`
- `integer`
- `float`
- `boolean`
- `date`
- `datetime`
- `category`

The `metadata` field is plain-text business context passed to the AI when it
generates SQL.

## DuckDB Database

Processed data is stored locally in:

```text
excel_data.duckdb
```

This file is excluded from Git. When the app reloads, it reads schema samples
from the existing database so the question and SQL controls remain available.
Queries execute against the complete persisted tables.

Only SQL statements beginning with `SELECT` are accepted by the application.

## Ollama Configuration

The following environment variables are optional:

```powershell
$env:OLLAMA_HOST = "http://localhost:11434"
$env:OLLAMA_MODEL = "qwen3.6"
$env:OLLAMA_NUM_CTX = "16384"
streamlit run app.py
```

Increase `OLLAMA_NUM_CTX` if a workbook contains a very large number of tables
or columns and Ollama reports that its context limit was reached.

## Project Structure

```text
ExcelQueryAI/
|-- app.py              # Streamlit UI and Excel processing
|-- ai_sql.py           # Ollama SQL generation
|-- data_profiler.py    # AI schema context generation
|-- query_engine.py     # Persistent DuckDB management and SQL execution
|-- requirements.txt
|-- data/               # Local Excel and metadata files
`-- README.md
```

## Local Files Excluded from Git

The repository ignores:

- Excel workbooks
- JSON metadata files
- DuckDB databases and WAL files
- Python cache files
- Virtual environments
- Local environment and editor configuration

