import os
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# --- Config ---
HF_MODEL = os.getenv("HF_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
DEVICE = "cpu"  # "cpu" por defecto

print(f"⏳ Cargando modelo {HF_MODEL} en {DEVICE}...")
tokenizer = AutoTokenizer.from_pretrained(HF_MODEL, use_fast=True)

# Cargar modelo en CPU (simple y compatible)
model = AutoModelForCausalLM.from_pretrained(
    HF_MODEL,
    torch_dtype=torch.float32,
)
model.to(DEVICE)
model.eval()

# Asegurar pad_token (algunos modelos no lo traen definido)
if tokenizer.pad_token_id is None:
    tokenizer.pad_token = tokenizer.eos_token
if getattr(model.config, "pad_token_id", None) is None:
    model.config.pad_token_id = tokenizer.pad_token_id
if getattr(model.config, "eos_token_id", None) is None:
    model.config.eos_token_id = tokenizer.eos_token_id

print("✅ Modelo cargado.")

SYSTEM = (
    "Eres un asistente conversacional en ESPAÑOL. "
    "Responde en tono natural, amable y CONCISO (1-3 frases). "
    "Sé claro y útil. No inventes citas, enlaces ni listas largas."
)

def _clean(text: str) -> str:
    """Limpia marcadores de rol y corta si el modelo arrancó otro turno."""
    t = text.lstrip()

    # Quitar encabezados típicos del asistente
    heads = ("<|assistant|>", "assistant:", "asistente:", "Assistant:", "Asistente:")
    for h in heads:
        if t.lower().startswith(h.lower()):
            t = t[len(h):].lstrip()

    # Cortar si aparece otro rol/sistema
    stops = ("<|user|>", "user:", "usuario:", "Usuario:", "<|system|>", "system:", "Sistema:")
    for s in stops:
        i = t.lower().find(s.lower())
        if i != -1:
            t = t[:i]
    # Cortar tokens especiales comunes
    for special in ("<|im_end|>", "</s>", tokenizer.eos_token or ""):
        if special and special in t:
            t = t.split(special)[0]

    return t.strip().strip('"').strip()

async def infer(msg: str) -> str:
    """Genera solo la respuesta del asistente (sin el prompt)."""
    # 1) Construir el prompt con chat_template cuando exista
    if getattr(tokenizer, "apply_chat_template", None):
        input_ids = tokenizer.apply_chat_template(
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user",   "content": msg},
            ],
            add_generation_prompt=True,
            tokenize=True,
            return_tensors="pt",
        ).to(model.device)
        attention_mask = torch.ones_like(input_ids)
    else:
        # Fallback simple si el tokenizer no trae plantilla
        prompt = f"Sistema: {SYSTEM}\nUsuario: {msg}\nAsistente:"
        enc = tokenizer(prompt, return_tensors="pt").to(model.device)
        input_ids = enc["input_ids"]
        attention_mask = enc.get("attention_mask", None)

    # 2) Generar
    with torch.no_grad():
        out = model.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=120,
            do_sample=True,
            temperature=0.6,
            top_p=0.9,
            repetition_penalty=1.15,
            no_repeat_ngram_size=4,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    # 3) ***CLAVE***: decodificar solo los tokens NUEVOS (sin el prompt)
    new_tokens = out[:, input_ids.shape[-1]:]
    text = tokenizer.decode(new_tokens[0], skip_special_tokens=True)

    # 4) Limpieza final
    return _clean(text)
