def build_schema_context(dataframes: dict, metadata_catalog: dict | None = None) -> str:
    schema_text = ""
    metadata_by_table = {
        str(table.get("new_table_name") or table.get("table_name")): table
        for table in (metadata_catalog or {}).get("tables", [])
    }

    for table_name, df in dataframes.items():
        schema_text += f"\nTable: {table_name}\n"
        column_metadata = {
            str(
                column.get("new_column_name")
                or column.get("newcolumn_name")
                or column.get("column_name")
            ): column
            for column in metadata_by_table.get(table_name, {}).get("columns", [])
        }

        for col in df.columns:
            dtype = str(df[col].dtype)
            series = df[col]
            catalog_entry = column_metadata.get(str(col), {})
            metadata = catalog_entry.get("metadata", "")
            metadata_text = str(metadata).strip() if metadata is not None else ""
            if len(metadata_text) > 500:
                metadata_text = f"{metadata_text[:497]}..."

            schema_text += f"- {col} | type: {dtype}"
            if (
                str(dtype) in {"object", "str", "string", "category"}
                and series.nunique(dropna=True) <= 20
            ):
                allowed_values = [
                    str(value)[:100]
                    for value in series.dropna().drop_duplicates().head(20)
                ]
                if allowed_values:
                    schema_text += f" | allowed values: {allowed_values}"
            if metadata_text:
                schema_text += f" | meaning: {metadata_text}"
            schema_text += "\n"

    return schema_text
