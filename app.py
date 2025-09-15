import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from core.hf import infer

load_dotenv()

app = FastAPI(title="HF Bot")

# servir frontend en /web
app.mount("/web", StaticFiles(directory="web", html=True), name="web")

class ChatIn(BaseModel):
    message: str

@app.post("/api/chat")
async def chat(body: ChatIn):
    msg = body.message.strip()
    if not msg:
        raise HTTPException(400, "Mensaje vacío")
    resp = await infer(msg)
    return {"response": resp}
