import os
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from core.db import get_config, set_config, add_knowledge, search_knowledge
from core.hf import infer
from sqlalchemy import text
from core.db import ENG  # usa el engine que ya tienes configurado con DATABASE_URL


load_dotenv()
app = FastAPI(title="Simple Bot (HF Inference API)")

# ✅ Servir web SOLO en /web y dejar libre /api/*
app.mount("/web", StaticFiles(directory="web", html=True), name="web")

# ✅ Redirigir la raíz a /web/
@app.get("/")
def root():
    return RedirectResponse(url="/web/")

# -------- API --------
class ChatIn(BaseModel):
    message: str

@app.post("/api/chat")
async def chat(body: ChatIn):
    msg = (body.message or "").strip()
    if not msg:
        raise HTTPException(400, "Mensaje vacío")

    system, temp, max_new, allow_out = get_config()
    hits = search_knowledge(msg, topk=4)
    ctx = "\n".join([f"• {(h[0] or '')} {h[1][:700]}" for h in hits]) or "(sin conocimiento relevante)"

    if not allow_out:
        system += "\nResponde SOLO con el contexto proporcionado. Si falta info, di que no la tienes."

    prompt = f"{system}\n\nContexto:\n{ctx}\n\nUsuario: {msg}\nAsistente:"
    resp = await infer(prompt, temp, max_new)
    return {"response": resp}

@app.get("/api/config")
def get_cfg():
    system, temp, max_new, allow_out = get_config()
    return {
        "system_prompt": system,
        "temp": temp,
        "max_new_tokens": max_new,
        "allow_out_of_scope": allow_out
    }

@app.put("/api/config")
def set_cfg(
    system_prompt: str = Form(...),
    temp: float = Form(...),
    max_new_tokens: int = Form(...),
    allow_out_of_scope: bool = Form(...)
):
    set_config(system_prompt, temp, max_new_tokens, allow_out_of_scope)
    return {"ok": True}

@app.post("/api/docs")
async def upload_doc(file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".txt", ".md")):
        raise HTTPException(400, "Solo .txt o .md")
    content = (await file.read()).decode("utf-8", errors="ignore")
    add_knowledge(file.filename, content)
    return {"ok": True, "filename": file.filename}

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

-- seed si no hay registros
INSERT INTO bot_config(system_prompt, temp, max_new_tokens, allow_out_of_scope)
SELECT 'Eres un asistente en español, breve y claro. Si algo no está en tu conocimiento, dilo.',
       0.6, 300, FALSE
WHERE NOT EXISTS (SELECT 1 FROM bot_config);
"""

@app.on_event("startup")
def ensure_schema():
    with ENG.begin() as c:
        c.execute(text(DDL))
