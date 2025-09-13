import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

URL = os.getenv("DATABASE_URL")
if not URL:
    raise RuntimeError("DATABASE_URL no está definido")

eng = create_engine(URL, pool_pre_ping=True)

DDL = """
CREATE TABLE IF NOT EXISTS bot_config (
  id SERIAL PRIMARY KEY,
  system_prompt TEXT NOT NULL,
  temp REAL NOT NULL DEFAULT 0.6,
  max_new_tokens INT NOT NULL DEFAULT 300,
  allow_out_of_scope BOOLEAN NOT NULL DEFAULT FALSE,
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge (
  id SERIAL PRIMARY KEY,
  title TEXT,
  content TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);
"""

SEED = """
INSERT INTO bot_config(system_prompt, temp, max_new_tokens, allow_out_of_scope)
SELECT :sp, :t, :m, :a WHERE NOT EXISTS (SELECT 1 FROM bot_config);
"""

with eng.begin() as c:
    c.execute(text(DDL))
    c.execute(text(SEED), {
        "sp": "Eres un asistente en español, breve y claro. Si algo no está en tu conocimiento, dilo.",
        "t": float(os.getenv("TEMP_DEFAULT", "0.6")),
        "m": int(os.getenv("MAX_NEW_TOKENS_DEFAULT", "300")),
        "a": os.getenv("ALLOW_OUT_OF_SCOPE", "false").lower() == "true",
    })

print("DB inicializada ✅")
