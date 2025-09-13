import os
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

URL = f"postgresql+psycopg2://{os.getenv('PG_USER')}:{os.getenv('PG_PASS')}@{os.getenv('PG_HOST')}:{os.getenv('PG_PORT')}/{os.getenv('PG_DB')}"
ENG = create_engine(URL, poolclass=QueuePool, pool_size=5, max_overflow=5, pool_pre_ping=True)

def get_config():
    with ENG.connect() as c:
        r = c.execute(text("""
            SELECT system_prompt, temp, max_new_tokens, allow_out_of_scope
            FROM bot_config ORDER BY updated_at DESC, id DESC LIMIT 1
        """)).fetchone()
        if not r:
            return ("Eres un asistente en español, breve y claro.", 0.6, 300, False)
        return r[0], float(r[1]), int(r[2]), bool(r[3])

def set_config(system_prompt: str, temp: float, max_new_tokens: int, allow_out: bool):
    with ENG.begin() as c:
        c.execute(text("""
            INSERT INTO bot_config(system_prompt, temp, max_new_tokens, allow_out_of_scope)
            VALUES (:sp, :t, :m, :a)
        """), {"sp": system_prompt, "t": temp, "m": max_new_tokens, "a": allow_out})

def add_knowledge(title: str, content: str):
    with ENG.begin() as c:
        c.execute(text("INSERT INTO knowledge(title, content) VALUES (:t,:c)"),
                  {"t": title, "c": content})

def search_knowledge(q: str, topk: int = 4):
    with ENG.connect() as c:
        rows = c.execute(text("""
            SELECT title, content FROM knowledge
            WHERE title ILIKE :q OR content ILIKE :q
            ORDER BY created_at DESC LIMIT :k
        """), {"q": f"%{q}%", "k": topk}).fetchall()
    return rows
