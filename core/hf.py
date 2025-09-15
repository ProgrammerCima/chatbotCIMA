# core/hf.py
import os, httpx

# Cliente con timeout razonable
_client = httpx.AsyncClient(timeout=httpx.Timeout(5.0, read=60.0, connect=5.0))

def _clean(v: str) -> str:
    # Quita espacios/comillas que a veces aparecen en variables de Railway
    return (v or "").strip().strip('"').strip("'")

FALLBACK_MODEL = "microsoft/Phi-3-mini-4k-instruct"

async def _call_chat_v1(model: str, token: str, prompt: str, temperature: float, max_new_tokens: int) -> str:
    """
    Ruta OpenAI-compatible de HF Serverless:
    POST https://api-inference.huggingface.co/v1/chat/completions
    """
    url = "https://api-inference.huggingface.co/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Wait-For-Model": "true",
        "Accept": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": float(temperature),
        "max_tokens": int(max_new_tokens),
    }
    r = await _client.post(url, headers=headers, json=payload)
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        body = r.text
        raise httpx.HTTPStatusError(f"{e} | body={body}", request=r.request, response=r)
    data = r.json()
    if isinstance(data, dict) and "choices" in data and data["choices"]:
        msg = data["choices"][0].get("message", {})
        return (msg.get("content") or "").strip() or str(data)
    return str(data)

async def _call_legacy_models_endpoint(model: str, token: str, prompt: str, temperature: float, max_new_tokens: int) -> str:
    """
    Ruta clásica:
    POST https://api-inference.huggingface.co/models/{model}
    (quedará como plan B)
    """
    url = f"https://api-inference.huggingface.co/models/{model}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Wait-For-Model": "true",
        "Accept": "application/json",
    }
    payload = {
        "inputs": prompt,
        "parameters": {"temperature": float(temperature), "max_new_tokens": int(max_new_tokens)}
    }
    r = await _client.post(url, headers=headers, json=payload)
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        body = r.text
        raise httpx.HTTPStatusError(f"{e} | body={body}", request=r.request, response=r)
    data = r.json()
    if isinstance(data, list) and data and "generated_text" in data[0]:
        return data[0]["generated_text"]
    if isinstance(data, dict) and "generated_text" in data:
        return data["generated_text"]
    if isinstance(data, dict) and "choices" in data and data["choices"]:
        choice = data["choices"][0]
        return (choice.get("text") or choice.get("generated_text") or "").strip() or str(data)
    return str(data)

async def infer(prompt: str, temperature: float, max_new_tokens: int) -> str:
    model = _clean(os.getenv("HF_MODEL"))
    token = _clean(os.getenv("HF_TOKEN"))
    # 1) intenta la API OpenAI-compatible
    try:
        return await _call_chat_v1(model, token, prompt, temperature, max_new_tokens)
    except httpx.HTTPStatusError as e1:
        # 2) si falla (404/503/etc), intenta endpoint legacy
        try:
            return await _call_legacy_models_endpoint(model, token, prompt, temperature, max_new_tokens)
        except httpx.HTTPStatusError as e2:
            # 3) fallback de modelo (por si el repo del modelo en uso falla)
            if e2.response is not None and e2.response.status_code in (404, 503):
                return await _call_chat_v1(FALLBACK_MODEL, token, prompt, temperature, max_new_tokens)
            raise httpx.HTTPStatusError(
                f"HF failed. chat_v1: {e1.response.status_code if e1.response else 'N/A'} | "
                f"models_ep: {e2.response.status_code if e2.response else 'N/A'} | "
                f"body1={(e1.response.text if e1.response else '')[:400]} | "
                f"body2={(e2.response.text if e2.response else '')[:400]}",
                request=e2.request, response=e2.response
            )
