import json
from pathlib import Path

import pandas as pd
import streamlit as st

from query_engine import (
    DATABASE_PATH,
    load_database_samples,
    rebuild_database,
    run_sql,
)
from data_profiler import build_schema_context
from ai_sql import OLLAMA_MODEL, generate_sql

DATA_DIR = Path(__file__).resolve().parent / "data"
METADATA_PATH = DATA_DIR / "excel_metadata.json"
EXCEL_EXTENSIONS = {".xlsx", ".xlsm", ".xls"}


def make_table_name(name: str, existing_names: set[str]) -> str:
    table_name = "".join(
        character if character.isalnum() else "_"
        for character in name.lower()
    ).strip("_")
    table_name = table_name or "data"

    if table_name[0].isdigit():
        table_name = f"table_{table_name}"

    base_name = table_name
    suffix = 2
    while table_name in existing_names:
        table_name = f"{base_name}_{suffix}"
        suffix += 1

    return table_name


def load_dataframes(data_dir: Path) -> tuple[dict[str, pd.DataFrame], list[str]]:
    dataframes = {}
    errors = []

    if not data_dir.is_dir():
        return dataframes, [f"Data folder not found: {data_dir}"]

    excel_files = sorted(
        (
            path
            for path in data_dir.iterdir()
            if path.is_file() and path.suffix.lower() in EXCEL_EXTENSIONS
        ),
        key=lambda path: path.name.lower(),
    )

    for file_path in excel_files:
        try:
            workbook = pd.ExcelFile(file_path)
            multiple_sheets = len(workbook.sheet_names) > 1

            for sheet_name in workbook.sheet_names:
                source_name = (
                    f"{file_path.stem}_{sheet_name}"
                    if multiple_sheets
                    else file_path.stem
                )
                table_name = make_table_name(source_name, set(dataframes))
                dataframes[table_name] = workbook.parse(sheet_name=sheet_name)
        except Exception as exc:
            errors.append(f"{file_path.name}: {exc}")

    return dataframes, errors


def make_column_name(name: str) -> str:
    column_name = "".join(
        character if character.isalnum() else "_"
        for character in name.lower()
    ).strip("_")
    return column_name or "column"


def build_metadata_catalog(dataframes: dict[str, pd.DataFrame]) -> dict:
    tables = []

    for table_name, df in dataframes.items():
        columns = []
        used_column_names = set()

        for column in df.columns:
            column_name = str(column)
            new_column_name = make_column_name(column_name)
            base_name = new_column_name
            suffix = 2

            while new_column_name in used_column_names:
                new_column_name = f"{base_name}_{suffix}"
                suffix += 1

            used_column_names.add(new_column_name)
            columns.append(
                {
                    "column_name": column_name,
                    "new_column_name": new_column_name,
                    "column_data_type": str(df[column].dtype),
                    "metadata": "",
                }
            )

        tables.append(
            {
                "table_name": table_name,
                "new_table_name": table_name,
                "columns": columns,
            }
        )

    return {"tables": tables}


def load_metadata_catalog(metadata_path: Path) -> dict | None:
    if not metadata_path.is_file():
        return None

    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def convert_column_data_type(series: pd.Series, data_type: str) -> pd.Series:
    normalized_type = data_type.strip().lower().replace(" ", "")

    if normalized_type in {"str", "string", "text", "object"}:
        return series.astype("string")
    if normalized_type in {"int", "integer", "int64", "int32", "long"}:
        return pd.to_numeric(series, errors="raise").astype("Int64")
    if normalized_type in {
        "float",
        "float64",
        "float32",
        "double",
        "decimal",
        "number",
        "numeric",
    }:
        return pd.to_numeric(series, errors="raise").astype("Float64")
    if normalized_type in {"bool", "boolean"}:
        if pd.api.types.is_bool_dtype(series):
            return series.astype("boolean")

        boolean_values = {
            "true": True,
            "false": False,
            "yes": True,
            "no": False,
            "y": True,
            "n": False,
            "1": True,
            "0": False,
        }
        converted = series.astype("string").str.strip().str.lower().map(boolean_values)
        invalid_values = series.notna() & converted.isna()
        if invalid_values.any():
            raise ValueError("contains values that cannot be converted to boolean")
        return converted.astype("boolean")
    if normalized_type == "date" or normalized_type.startswith("datetime"):
        converted = pd.to_datetime(series, errors="raise")
        return converted.dt.normalize() if normalized_type == "date" else converted
    if normalized_type in {"category", "categorical"}:
        return series.astype("category")

    raise ValueError(f"unsupported data type '{data_type}'")


def apply_metadata_catalog(
    dataframes: dict[str, pd.DataFrame],
    metadata_catalog: dict | None,
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    if not metadata_catalog:
        return dataframes, []

    tables = {
        table.get("table_name"): table
        for table in metadata_catalog.get("tables", [])
        if isinstance(table, dict) and table.get("table_name")
    }
    processed_dataframes = {}
    errors = []

    for table_name, df in dataframes.items():
        table_metadata = tables.get(table_name, {})
        new_table_name = str(
            table_metadata.get("new_table_name") or table_name
        ).strip()
        new_table_name = new_table_name or table_name
        rename_map = {}
        processed_df = df.copy()

        for column in table_metadata.get("columns", []):
            original_name = str(column.get("column_name", ""))
            new_name = str(
                column.get("new_column_name")
                or column.get("newcolumn_name")
                or original_name
            ).strip()
            data_type = str(
                column.get("column_data_type")
                or column.get("data_type")
                or (
                    column.get("metadata", {}).get("data_type")
                    if isinstance(column.get("metadata"), dict)
                    else ""
                )
                or ""
            ).strip()

            matching_column = next(
                (
                    dataframe_column
                    for dataframe_column in processed_df.columns
                    if str(dataframe_column) == original_name
                ),
                None,
            )
            if matching_column is None:
                errors.append(
                    f"{table_name}: column '{original_name}' was not found."
                )
                continue

            if data_type:
                try:
                    processed_df[matching_column] = convert_column_data_type(
                        processed_df[matching_column],
                        data_type,
                    )
                except (TypeError, ValueError) as exc:
                    errors.append(
                        f"{table_name}.{original_name}: {exc}. "
                        "The original data type was retained."
                    )

            if new_name:
                rename_map[matching_column] = new_name

        renamed_columns = [
            rename_map.get(column, str(column))
            for column in processed_df.columns
        ]
        duplicate_columns = sorted(
            {
                column
                for column in renamed_columns
                if renamed_columns.count(column) > 1
            }
        )

        if duplicate_columns:
            errors.append(
                f"{table_name}: duplicate new column name(s): "
                f"{', '.join(duplicate_columns)}. Original names were retained."
            )
        else:
            processed_df = processed_df.rename(columns=rename_map)

        if new_table_name in processed_dataframes:
            errors.append(
                f"{table_name}: new table name '{new_table_name}' is already in use. "
                "The original table name was retained."
            )
            new_table_name = table_name
            suffix = 2
            while new_table_name in processed_dataframes:
                new_table_name = f"{table_name}_{suffix}"
                suffix += 1

        processed_dataframes[new_table_name] = processed_df

    return processed_dataframes, errors


st.set_page_config(page_title="Excel AI Analyst", layout="wide")

st.title("Excel AI Analyst")
st.caption(f"Reading Excel workbooks from {DATA_DIR}")
st.caption(f"Generating SQL locally with Ollama model {OLLAMA_MODEL}")
st.caption(f"Persistent DuckDB database: {DATABASE_PATH}")

if "dataframes" not in st.session_state:
    try:
        st.session_state.dataframes = load_database_samples()
        st.session_state.database_load_error = ""
    except Exception as exc:
        st.session_state.dataframes = {}
        st.session_state.database_load_error = str(exc)
if "load_errors" not in st.session_state:
    st.session_state.load_errors = []
if "metadata_catalog" not in st.session_state:
    st.session_state.metadata_catalog = load_metadata_catalog(METADATA_PATH)
if "sql_editor" not in st.session_state:
    st.session_state.sql_editor = ""
if "query_result" not in st.session_state:
    st.session_state.query_result = None

process_column, metadata_column = st.columns(2)

with process_column:
    process_files = st.button(
        "Parse Excel files and recreate database",
        use_container_width=True,
    )

with metadata_column:
    generate_metadata = st.button(
        "Generate table and column JSON",
        use_container_width=True,
    )

if process_files:
    with st.spinner("Processing Excel files..."):
        dataframes, load_errors = load_dataframes(DATA_DIR)
        metadata_catalog = load_metadata_catalog(METADATA_PATH)
        dataframes, rename_errors = apply_metadata_catalog(
            dataframes,
            metadata_catalog,
        )
        load_errors.extend(rename_errors)
        rebuild_database(dataframes)
        st.session_state.dataframes = dataframes
        st.session_state.load_errors = load_errors
        st.session_state.metadata_catalog = metadata_catalog
        st.session_state.database_load_error = ""
        st.session_state.sql_editor = ""
        st.session_state.query_result = None

    if dataframes:
        st.success(
            f"Recreated the database with {len(dataframes)} table(s)."
        )

if generate_metadata:
    with st.spinner("Reading Excel files and generating metadata..."):
        dataframes, load_errors = load_dataframes(DATA_DIR)
        st.session_state.load_errors = load_errors

        if dataframes:
            metadata_catalog = build_metadata_catalog(dataframes)
            METADATA_PATH.write_text(
                json.dumps(metadata_catalog, indent=2, ensure_ascii=True),
                encoding="utf-8",
            )
            st.session_state.metadata_catalog = metadata_catalog
            st.success(f"Metadata JSON generated at {METADATA_PATH}.")

dataframes = st.session_state.dataframes
load_errors = st.session_state.load_errors
metadata_catalog = st.session_state.metadata_catalog

if st.session_state.get("database_load_error"):
    st.error(
        "Could not read the existing DuckDB database: "
        f"{st.session_state.database_load_error}"
    )

for error in load_errors:
    st.error(f"Could not load {error}")

if not dataframes:
    st.info(
        f"Add one or more .xlsx, .xlsm, or .xls files to {DATA_DIR} "
        "and click Parse Excel files and recreate database."
    )

if dataframes:
    schema_context = build_schema_context(dataframes, metadata_catalog)
    question = st.text_input("Ask a question about your data")

    if st.button("Generate SQL") and question:
        try:
            sql = generate_sql(question, schema_context)
            st.session_state.sql_editor = sql
            st.session_state.query_result = None
        except Exception as exc:
            st.session_state.sql_editor = ""
            st.session_state.query_result = None
            st.error(f"Unable to generate SQL: {exc}")

    st.text_area(
        "SQL query",
        key="sql_editor",
        height=180,
        placeholder="Generate a query with AI or enter a SELECT statement.",
    )

    if st.button("Run SQL", disabled=not st.session_state.sql_editor.strip()):
        try:
            st.session_state.query_result = run_sql(
                st.session_state.sql_editor
            )
        except Exception as exc:
            st.session_state.query_result = None
            st.error(f"Unable to run SQL: {exc}")

    if st.session_state.query_result is not None:
        st.subheader("Query result")
        st.dataframe(st.session_state.query_result, use_container_width=True)
