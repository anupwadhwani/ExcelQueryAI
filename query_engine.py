from pathlib import Path

import duckdb


DATABASE_PATH = Path(__file__).resolve().parent / "excel_data.duckdb"
SCHEMA_SAMPLE_SIZE = 1000


def quote_identifier(identifier: str) -> str:
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'


def rebuild_database(dataframes: dict, database_path: Path = DATABASE_PATH) -> None:
    connection = duckdb.connect(str(database_path))

    try:
        connection.execute("BEGIN TRANSACTION")

        objects = connection.execute(
            """
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            ORDER BY CASE WHEN table_type = 'VIEW' THEN 0 ELSE 1 END
            """
        ).fetchall()

        for schema_name, object_name, object_type in objects:
            qualified_name = (
                f"{quote_identifier(schema_name)}.{quote_identifier(object_name)}"
            )
            drop_type = "VIEW" if object_type == "VIEW" else "TABLE"
            connection.execute(f"DROP {drop_type} IF EXISTS {qualified_name}")

        for index, (table_name, dataframe) in enumerate(dataframes.items()):
            source_name = f"_excel_source_{index}"
            connection.register(source_name, dataframe)
            connection.execute(
                f"CREATE TABLE {quote_identifier(table_name)} AS "
                f"SELECT * FROM {quote_identifier(source_name)}"
            )
            connection.unregister(source_name)

        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def load_database_samples(
    database_path: Path = DATABASE_PATH,
    sample_size: int = SCHEMA_SAMPLE_SIZE,
) -> dict:
    if not database_path.is_file():
        return {}

    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        table_names = [
            row[0]
            for row in connection.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'main' AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """
            ).fetchall()
        ]

        return {
            table_name: connection.execute(
                f"SELECT * FROM {quote_identifier(table_name)} "
                f"LIMIT {int(sample_size)}"
            ).df()
            for table_name in table_names
        }
    finally:
        connection.close()


def run_sql(sql: str, database_path: Path = DATABASE_PATH):
    cleaned = sql.strip().lower()

    if not cleaned.startswith("select"):
        raise ValueError("Only SELECT queries are allowed.")

    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        return connection.execute(sql).df()
    finally:
        connection.close()
