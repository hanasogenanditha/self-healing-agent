"""
Memory Layer — pgvector-backed storage of past solved problems.

check_memory_node (in core/graph.py) calls find_similar_solution() before
generation, to pass a similar past problem as context. store_memory_node
calls store_solution() after a successful run, to remember it for next time.
"""

import os
from dataclasses import dataclass
from typing import Optional

import psycopg
from pgvector.psycopg import register_vector
from dotenv import load_dotenv
from google import genai


load_dotenv()

_DATABASE_URL = os.getenv("DATABASE_URL")
if not _DATABASE_URL:
    raise RuntimeError("DATABASE_URL not found in environment. Check your .env file.")

_API_KEY = os.getenv("GEMINI_API_KEY")
if not _API_KEY:
    raise RuntimeError("GEMINI_API_KEY not found in environment. Check your .env file.")

_client = genai.Client(api_key=_API_KEY)
_EMBED_MODEL = "gemini-embedding-001"
_EMBED_DIM = 768
_SIMILARITY_THRESHOLD = 0.75


class MemoryStoreError(Exception):
    """Raised for DB/embedding infra problems — distinct from 'no match found'.
    Named to avoid shadowing Python's built-in MemoryError."""
    pass


@dataclass
class MemoryMatch:
    problem: str
    code: str
    explanation: str
    similarity: float


def _get_raw_connection():
    try:
        return psycopg.connect(_DATABASE_URL, connect_timeout=5)
    except psycopg.OperationalError as e:
        raise MemoryStoreError(f"Could not connect to Postgres: {e}") from e


def _get_connection():
    conn = _get_raw_connection()
    try:
        register_vector(conn)
    except psycopg.ProgrammingError as e:
        conn.close()
        raise MemoryStoreError(
            f"pgvector extension not found — has init_db() been run yet? ({e})"
        ) from e
    return conn


def init_db():
    """Creates the pgvector extension and solved_problems table if missing.
    Call once at API startup."""
    conn =_get_raw_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS solved_problems (
                    id SERIAL PRIMARY KEY,
                    problem TEXT NOT NULL,
                    code TEXT NOT NULL,
                    explanation TEXT,
                    embedding VECTOR({_EMBED_DIM}),
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
        conn.commit()
    finally:
        conn.close()


def _embed_text(text: str) -> list[float]:
    try:
        response = _client.models.embed_content(
            model=_EMBED_MODEL,
            contents=text,
            config={"output_dimensionality": _EMBED_DIM},
        )
    except Exception as e:
        raise MemoryStoreError(f"Embedding call failed: {e}") from e

    return response.embeddings[0].values


def find_similar_solution(problem: str) -> Optional[MemoryMatch]:
    """Returns the most similar past solved problem if similarity is above
    the threshold, otherwise None."""
    query_embedding = _embed_text(problem)

    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT problem, code, explanation, 1 - (embedding <=> %s::vector) AS similarity
                FROM solved_problems
                ORDER BY embedding <=> %s::vector
                LIMIT 1;
                """,
                (query_embedding, query_embedding),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    matched_problem, code, explanation, similarity = row
    print(f"[DEBUG] raw similarity = {similarity}")
    if similarity < _SIMILARITY_THRESHOLD:
        return None

    return MemoryMatch(problem=matched_problem, code=code, explanation=explanation or "", similarity=float(similarity))


def store_solution(problem: str, code: str, explanation: str):
    """Stores a successfully solved problem for future retrieval."""
    embedding = _embed_text(problem)

    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO solved_problems (problem, code, explanation, embedding)
                VALUES (%s, %s, %s, %s::vector);
                """,
                (problem, code, explanation, embedding),
            )
        conn.commit()
    finally:
        conn.close()


def list_recent_solutions(limit: int = 20) -> list[dict]:
    """Returns recently solved problems, most recent first. Powers GET /history."""
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT problem, code, explanation, created_at
                FROM solved_problems
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (limit,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        {"problem": r[0], "code": r[1], "explanation": r[2], "created_at": r[3].isoformat()}
        for r in rows
    ]