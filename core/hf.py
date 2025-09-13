import os, httpx

_client = httpx.AsyncClient(timeout=httpx.Timeout(5.0, read=60.0, connect=5.0))

async def infer(prompt: str, temperature: float, max_new_tokens: int) -> str:
    url = f"https://api-inference.huggingface.co/models/{os.getenv('HF_MODEL')}"
    headers = {"Authorization": f"Bearer {os.getenv('HF_TOKEN')}", "Content-Type": "application/json"}
    payload = {"inputs": prompt, "parameters": {"temperature": temperature, "max_new_tokens": max_new_tokens}}
    r = await _client.post(url, headers=headers, json=payload)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, list) and data and "generated_text" in data[0]:
        return data[0]["generated_text"]
    if isinstance(data, dict) and "generated_text" in data:
        return data["generated_text"]
    return str(data)
