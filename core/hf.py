import os, httpx

# Timeout razonable
_client = httpx.AsyncClient(timeout=httpx.Timeout(5.0, read=60.0, connect=5.0))

def _clean(v: str) -> str:
    # quita espacios y comillas que a veces agrega/visualiza la UI
    return (v or "").strip().strip('"').strip("'")

FALLBACK_MODEL = "microsoft/Phi-3-mini-4k-instruct"  # por si Qwen da 404/503

async def _call(model: str, token: str, prompt: str, temperature: float, max_new_tokens: int):
    url = f"https://api-inference.huggingface.co/models/{model}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        # fuerza a que el endpoint espere a que el modelo esté listo
        "X-Wait-For-Model": "true",
        "Accept": "application/json",
    }
    payload = {
        "inputs": prompt,
        "parameters": {"temperature": temperature, "max_new_tokens": max_new_tokens}
    }
    r = await _client.post(url, headers=headers, json=payload)
    r.raise_for_status()
    data = r.json()

    # distintas formas válidas de respuesta
    if isinstance(data, list) and data and "generated_text" in data[0]:
        return data[0]["generated_text"]
    if isinstance(data, dict) and "generated_text" in data:
        return data["generated_text"]
    # algunos providers devuelven { "choices": [...] }
    if isinstance(data, dict) and "choices" in data and data["choices"]:
        choice = data["choices"][0]
        return choice.get("text") or choice.get("generated_text") or str(data)
    return str(data)

async def infer(prompt: str, temperature: float, max_new_tokens: int) -> str:
    model = _clean(os.getenv("HF_MODEL"))
    token = _clean(os.getenv("HF_TOKEN"))
    try:
        return await _call(model, token, prompt, temperature, max_new_tokens)
    except httpx.HTTPStatusError as e:
        # Si el modelo devuelve 404/503, usa fallback temporal para no cortar el flujo
        if e.response is not None and e.response.status_code in (404, 503):
            return await _call(FALLBACK_MODEL, token, prompt, temperature, max_new_tokens)
        raise
