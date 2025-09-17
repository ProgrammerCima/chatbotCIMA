import os
from collections import defaultdict, deque
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import PlainTextResponse, RedirectResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from core.hf import infer_with_history
from core.kb import SimpleKB

load_dotenv()

app = FastAPI(title="HF Bot (Qwen 0.5B) + RAG estricto")

# ---- Frontend ----
app.mount("/web", StaticFiles(directory="web", html=True), name="web")

@app.get("/")
def root():
    return RedirectResponse(url="/web/")

# ---- Memoria por sesión ----
MAX_TURNS = int(os.getenv("MAX_TURNS", "8"))
SESSIONS = defaultdict(lambda: deque(maxlen=MAX_TURNS * 2))

# ---- KB / RAG ----
kb = SimpleKB(kb_dir="kb")
MIN_SIM = float(os.getenv("MIN_SIM", "0.35"))  # umbral de relevancia

# ---- Schemas ----
class ChatIn(BaseModel):
    message: Optional[str] = None
    session_id: Optional[str] = None
    reset: bool = False

class KBIn(BaseModel):
    title: str
    text: str

# ---- Chat ----
@app.post("/api/chat", response_class=PlainTextResponse)
async def chat(body: ChatIn):
    sid = (body.session_id or "default").strip()
    msg = (body.message or "").strip()

    if body.reset:
        if sid in SESSIONS:
            SESSIONS.pop(sid, None)
        if not msg:
            return "🧹 Historial reiniciado. Empecemos de cero: ¿en qué te ayudo?"

    if not msg:
        raise HTTPException(status_code=400, detail="Mensaje vacío")

    # 1) Buscar contexto en KB
    ctx, sources, best = kb.search(msg, k=4, max_chars=1200)

    # 2) Si no hay contexto suficientemente relevante -> negar educadamente
    if not ctx or best < MIN_SIM:
        topics = kb.topics()
        temas = ", ".join(topics) if topics else "—"
        return (
            "No dispongo de información suficiente en mi base de conocimiento para responderlo con precisión. "
            f"Temas cargados actualmente: {temas}. Añade el contenido a la KB y vuelve a intentar."
        )

    # 3) Inferencia con historial + contexto (estricto)
    history = list(SESSIONS.get(sid, []))
    resp = await infer_with_history(history, msg, context=ctx)

    # 4) Guardar turno
    dq = SESSIONS[sid]
    dq.append({"role": "user", "content": msg})
    dq.append({"role": "assistant", "content": resp})

    # 5) (Opcional) anexar fuentes
    if sources:
        resp = f"{resp}\n\nFuentes: " + " | ".join(dict.fromkeys(sources))

    return (resp or "").strip()

@app.post("/api/reset", response_class=PlainTextResponse)
async def reset(body: ChatIn):
    sid = (body.session_id or "default").strip()
    SESSIONS.pop(sid, None)
    return "🧹 Historial reiniciado."

# ---- Admin KB ----
@app.post("/api/kb/add", response_class=PlainTextResponse)
def kb_add(body: KBIn):
    path = kb.add_text(body.title, body.text)
    return f"✅ Añadido a la KB: {path}"

@app.post("/api/kb/reindex", response_class=PlainTextResponse)
def kb_reindex():
    kb.reindex()
    return "🔄 KB reindexada."

@app.get("/api/kb/list")
def kb_list():
    return kb.list_docs()
