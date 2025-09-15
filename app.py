import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from core.hf import infer

load_dotenv()

app = FastAPI(title="HF Bot")

# Servir frontend en /web
app.mount("/web", StaticFiles(directory="web", html=True), name="web")

# Redirigir la raíz a /web/
@app.get("/")
def root():
    return RedirectResponse(url="/web/")

class ChatIn(BaseModel):
    message: str

@app.post("/api/chat")
async def chat(body: ChatIn):
    msg = (body.message or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Mensaje vacío")
    resp = await infer(msg)
    return {"response": resp}
