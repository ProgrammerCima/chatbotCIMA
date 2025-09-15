import os, httpx

_client = httpx.AsyncClient(timeout=httpx.Timeout(5.0, read=60.0))

def _clean(v: str) -> str:
    return (v or "").strip().strip('"').strip("'")

async def infer(prompt: str, temperature: float = 0.7, max_new_tokens: int = 200) -> str:
    model = _clean(os.getenv("HF_MODEL"))
    token = _clean(os.getenv("HF_TOKEN"))
    url = f"https://api-inference.huggingface.co/models/{model}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"inputs": prompt, "parameters": {"temperature": temperature, "max_new_tokens": max_new_tokens}}
    r = await _client.post(url, headers=headers, json=payload)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, list) and data and "generated_text" in data[0]:
        return data[0]["generated_text"]
    return str(data)
