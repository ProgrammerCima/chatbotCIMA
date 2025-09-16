import os
import inspect
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import PlainTextResponse, RedirectResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from core.hf import infer

load_dotenv()

app = FastAPI(title="HF Bot")

# Servir frontend
app.mount("/web", StaticFiles(directory="web", html=True), name="web")

# Redirigir raíz -> /web
@app.get("/")
def root():
    return RedirectResponse(url="/web/")

# Modelo de entrada
class ChatIn(BaseModel):
    message: str

# Solo texto plano como respuesta
@app.post("/api/chat", response_class=PlainTextResponse)
async def chat(body: ChatIn):
    msg = (body.message or "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Mensaje vacío")

    # Soporta infer() sync o async
    result = infer(msg)
    resp = await result if inspect.isawaitable(result) else result

    return (resp or "").strip()
