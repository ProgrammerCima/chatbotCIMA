import os
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# Nombre del modelo (puede cambiar en .env)
MODEL_NAME = os.getenv("HF_MODEL", "HuggingFaceTB/SmolLM-135M")

print(f"⏳ Cargando modelo {MODEL_NAME} en CPU...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    torch_dtype=torch.float32,  # CPU
    device_map="cpu"
)
print("✅ Modelo cargado en CPU.")

async def infer(prompt: str) -> str:
    """Generar texto con el modelo local en CPU."""
    inputs = tokenizer(prompt, return_tensors="pt").to("cpu")
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=128,
            temperature=0.7,
            do_sample=True
        )
    return tokenizer.decode(outputs[0], skip_special_tokens=True)
