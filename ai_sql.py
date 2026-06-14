import os

from ollama import Client

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.6")
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "16384"))

client = Client(host=OLLAMA_HOST)


def generate_sql(question: str, schema_context: str) -> str:
    response = client.chat(
        model=OLLAMA_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a data analyst who converts plain-English "
                    "questions into DuckDB SQL. Use only the provided tables "
                    "and columns. Return exactly one SELECT statement and no "
                    "explanation or Markdown. Join tables using likely matching "
                    "keys only when needed. SQL must reference the table and "
                    "column names shown in the schema. Column metadata is "
                    "plain-text business context. When allowed values are "
                    "provided for a column, copy the matching value exactly, "
                    "including its capitalization, into SQL string literals. "
                    "Do not invent a differently cased value."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Schema:\n{schema_context}\n\n"
                    f"Question:\n{question}"
                ),
            },
        ],
        think=False,
        stream=False,
        options={
            "temperature": 0,
            "num_ctx": OLLAMA_NUM_CTX,
            "num_predict": 512,
        },
    )

    if response.done_reason == "length":
        raise ValueError(
            "Ollama stopped because the context or output limit was reached. "
            "Reduce the schema metadata or increase OLLAMA_NUM_CTX."
        )

    sql = response.message.content.strip()
    sql = sql.replace("```sql", "").replace("```", "").strip()

    if not sql:
        raise ValueError(f"Ollama model {OLLAMA_MODEL} returned an empty response.")
    if not sql.lower().startswith("select"):
        raise ValueError(
            f"Ollama model {OLLAMA_MODEL} did not return a SELECT query: {sql}"
        )

    return sql
