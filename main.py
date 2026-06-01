import os
import requests
from json import dumps, loads


def chat_with_model(prompt, model="asistente-de-ventas", api_key=None, base_url=None):
    """Envía un prompt a Open Web UI local y retorna la respuesta JSON."""
    base_url = base_url or os.getenv("OWUI_BASE_URL", "http://localhost:3000")
    api_key = api_key or os.getenv("OWUI_API_KEY")
    if not api_key:
        raise ValueError(
            "OWUI_API_KEY no está configurado. Establece OWUI_API_KEY con tu token de Open WebUI."
        )

    url = f"{base_url.rstrip('/')}/api/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }

    response = requests.post(url, headers=headers, json=payload)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text or response.content
        raise requests.HTTPError(
            f"{response.status_code} {response.reason}: {detail}"
        ) from exc

    return response.json()


def main():
    prompt = "estoy buscando audifonos, cuales tienes"
    result = chat_with_model(prompt, model="asistente-de-ventas")
    print(dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
