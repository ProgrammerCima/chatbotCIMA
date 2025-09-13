import os
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from core.db import get_config, set_config, add_knowledge, search_knowledge
from core.hf import infer
from fastapi.responses import RedirectResponse


load_dotenv()
app = FastAPI(title="Simple Bot (HF Inference API)")

# Servir web estática (frontend simple)
app.mount("/", StaticFiles(directory="web", html=True), name="web")

# -------- API --------
class ChatIn(BaseModel):
    message: str

    
# Servir web en /web y NO en "/"
app.mount("/web", StaticFiles(directory="web", html=True), name="web")

@app.get("/")
def root():
    return RedirectResponse(url="/web/")

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
    if not file.filename.lower().endswith((".txt",".md")):
        raise HTTPException(400, "Solo .txt o .md")
    content = (await file.read()).decode("utf-8", errors="ignore")
    add_knowledge(file.filename, content)
    return {"ok": True, "filename": file.filename}
