# core/hf.py
from __future__ import annotations

import os, re
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# ======================
# Configuración
# ======================
HF_MODEL = os.getenv("HF_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
DEVICE = os.getenv("DEVICE", "cpu")              # "cpu" por defecto
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "140"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.6"))
TOP_P = float(os.getenv("TOP_P", "0.9"))
REPETITION_PENALTY = float(os.getenv("REPETITION_PENALTY", "1.15"))
NO_REPEAT_NGRAM = int(os.getenv("NO_REPEAT_NGRAM", "4"))

# Corrección gramatical opcional con LanguageTool (ES)
ENABLE_GRAMMAR_ES = os.getenv("ENABLE_GRAMMAR_ES", "1") == "1"
try:
    import language_tool_python
    _lt_es = language_tool_python.LanguageTool('es') if ENABLE_GRAMMAR_ES else None
except Exception:
    _lt_es = None

def _polish_es(text: str) -> str:
    if not _lt_es:
        return text
    try:
        matches = _lt_es.check(text)
        return language_tool_python.utils.correct(text, matches)
    except Exception:
        return text

print(f"⏳ Cargando modelo {HF_MODEL} en {DEVICE}...")
tokenizer = AutoTokenizer.from_pretrained(HF_MODEL, use_fast=True)
model = AutoModelForCausalLM.from_pretrained(HF_MODEL, torch_dtype=torch.float32)
model.to(DEVICE)
model.eval()

# Asegurar tokens especiales
if tokenizer.pad_token_id is None:
    tokenizer.pad_token = tokenizer.eos_token
if getattr(model.config, "pad_token_id", None) is None:
    model.config.pad_token_id = tokenizer.pad_token_id
if getattr(model.config, "eos_token_id", None) is None:
    model.config.eos_token_id = tokenizer.eos_token_id

print("✅ Modelo cargado.")

# ======================
# Estilo / Política de respuesta (estricta y extractiva)
# ======================
SYSTEM = (
    "Eres un asistente en ESPAÑOL, claro y amable. Responde en 1–4 frases."
    "\nREGLAS ESTRICTAS:"
    "\n1) SOLO puedes usar la información del bloque 'HECHOS' o 'CONOCIMIENTO RELEVANTE'."
    '\n2) Si esa información no es pertinente o no existe, responde exactamente: '
    '"No dispongo de información suficiente en mi base de conocimiento para responderlo con precisión."'
    "\n3) Si mencionas correos, teléfonos, montos, fechas o porcentajes, DEBEN aparecer literalmente en esos bloques."
    "\n4) No inventes datos ni completes con dominios o números supuestos. No hagas suposiciones."
)

# ======================
# Utilidades
# ======================
def _clean(text: str) -> str:
    """Limpia marcadores de rol y corta si el modelo arrancó otro turno."""
    t = text.lstrip()

    for h in ("<|assistant|>", "assistant:", "asistente:", "Assistant:", "Asistente:"):
        if t.lower().startswith(h.lower()):
            t = t[len(h):].lstrip()

    for s in ("<|user|>", "user:", "usuario:", "Usuario:", "<|system|>", "system:", "Sistema:"):
        i = t.lower().find(s.lower())
        if i != -1:
            t = t[:i]

    for sp in (tok for tok in ("<|im_end|>", "</s>", tokenizer.eos_token) if tok):
        if sp in t:
            t = t.split(sp)[0]

    return t.strip().strip('"').strip()

def _guard_from_context(text: str, context: str | None) -> bool:
    """
    True si los datos delicados citados por 'text' están presentes en 'context'.
    Si no hay 'context', exige que no haya datos delicados.
    """
    if text.strip() == "":
        return False

    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s or "").strip().lower()

    ctx = norm(context or "")
    out = norm(text)

    emails = re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, flags=re.I)
    phones = re.findall(r"\+?\d[\d\s\-]{6,}", text)
    numbers = re.findall(r"\b\d{1,4}(?:[.,]\d+)?\b", text)
    percents = re.findall(r"\b\d{1,3}\s?%\b", text)
    dates = re.findall(r"\b(?:\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\b", text)

    for e in emails:
        if norm(e) not in ctx:
            return False

    ctx_digits = re.sub(r"[^\d+]", "", ctx)
    for p in phones:
        if re.sub(r"[^\d+]", "", p) not in ctx_digits:
            return False

    for z in numbers + percents + dates:
        if norm(z) not in ctx:
            return False

    return True

# ======================
# Inferencia con historial + (opcional) contexto RAG
# ======================
async def infer_with_history(
    history: list[dict],
    user_msg: str,
    context: str | None = None
) -> str:
    """
    Genera una respuesta usando historial + (opcional) contexto externo.
    - history: [{"role":"user"|"assistant","content":"..."}]
    - user_msg: mensaje nuevo del usuario
    - context: texto recuperado de tu base de conocimiento (RAG). Opcional.
    """
    # 0) Sistema con (o sin) contexto
    sys_msg = SYSTEM
    if context:
        sys_msg += (
            "\n\n" + context.strip() + "\n"
        )

    # 1) Construir el prompt (chat_template si existe)
    msgs = [{"role": "system", "content": sys_msg}, *history, {"role": "user", "content": user_msg}]

    if getattr(tokenizer, "apply_chat_template", None):
        input_ids = tokenizer.apply_chat_template(
            msgs,
            add_generation_prompt=True,
            tokenize=True,
            return_tensors="pt",
        ).to(model.device)
        attention_mask = torch.ones_like(input_ids)
    else:
        # Fallback simple
        lines = []
        for m in msgs:
            if m["role"] == "system":
                lines.append(f"Sistema: {m['content']}")
            elif m["role"] == "user":
                lines.append(f"Usuario: {m['content']}")
            else:
                lines.append(f"Asistente: {m['content']}")
        lines.append("Asistente:")
        enc = tokenizer("\n".join(lines), return_tensors="pt").to(model.device)
        input_ids = enc["input_ids"]
        attention_mask = enc.get("attention_mask", None)

    # 2) Generar
    with torch.no_grad():
        out = model.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=True,
            temperature=TEMPERATURE,
            top_p=TOP_P,
            repetition_penalty=REPETITION_PENALTY,
            no_repeat_ngram_size=NO_REPEAT_NGRAM,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    # 3) Decodificar solo tokens NUEVOS
    new_tokens = out[:, input_ids.shape[-1]:]
    text = tokenizer.decode(new_tokens[0], skip_special_tokens=True)

    # 4) Limpieza + (opcional) pulido + verificación
    text = _clean(text)
    try:
        text = _polish_es(text)
    except Exception:
        pass

    if not _guard_from_context(text, context):
        return "No dispongo de información suficiente en mi base de conocimiento para responderlo con precisión."

    return text

# ======================
# Modo single-turn
# ======================
async def infer(msg: str) -> str:
    return await infer_with_history([], msg)
