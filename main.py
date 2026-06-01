import os
import requests
from json import dumps, loads

OWUI_BASE_URL      = os.getenv("OWUI_BASE_URL", "http://localhost:3000")
OWUI_API_KEY       = os.getenv("OWUI_API_KEY")
ECOMMERCE_BASE_URL = "https://api-development-5d8c.up.railway.app"
ECOMMERCE_API_KEY  = os.getenv("ECOMMERCE_API_KEY")


def ecommerce_headers():
    return {
        "Authorization": f"Bearer {ECOMMERCE_API_KEY}",
        "Content-Type": "application/json",
    }


TOOL_MAP = {
    "search_catalog": (
        "POST", "/v1/catalog/search", "body"
    ),
    "list_catalog_products": (
        "GET",  "/v1/catalog/products", "query"
    ),
    "get_catalog_product": (
        "GET",  "/v1/catalog/products/{product_id}", "path+query"
    ),
    "lookup_catalog_inventory": (
        "POST", "/v1/catalog/inventory-lookup", "body"
    ),
    "compare_catalog_products": (
        "POST", "/v1/catalog/comparisons", "body"
    ),
    "suggest_cross_sell_products": (
        "POST", "/v1/catalog/cross-sell-suggestions", "body"
    ),
}


def call_tool(tool_name: str, arguments: dict) -> str:
    """Ejecuta la tool real contra la API de ecommerce."""
    if tool_name not in TOOL_MAP:
        return dumps({"error": f"Tool '{tool_name}' no registrada en TOOL_MAP"}, ensure_ascii=False)

    method, path_template, params_mode = TOOL_MAP[tool_name]
    path = path_template

    for key in list(arguments.keys()):
        placeholder = f"{{{key}}}"
        if placeholder in path_template:
            path = path.replace(placeholder, str(arguments[key]))
            arguments.pop(key)

    url = f"{ECOMMERCE_BASE_URL}{path}"
    print(f"  [TOOL] {method} {url}")
    print(f"  [TOOL] args: {dumps(arguments, ensure_ascii=False)}")

    try:
        if method == "GET":
            resp = requests.get(url, params=arguments, headers=ecommerce_headers(), timeout=15)
        else:
            resp = requests.post(url, json=arguments, headers=ecommerce_headers(), timeout=15)

        resp.raise_for_status()
        result = resp.json()
        print(f"  [TOOL] ✅ {str(result)[:200]}")
        return dumps(result, ensure_ascii=False)

    except requests.HTTPError as e:
        err = {"error": f"HTTP {e.response.status_code}", "detail": e.response.text}
        print(f"  [TOOL] ❌ {err}")
        return dumps(err, ensure_ascii=False)
    except Exception as e:
        return dumps({"error": str(e)}, ensure_ascii=False)


def chat_with_tools(prompt, model="asistente-de-ventas", tool_ids=None):
    if not OWUI_API_KEY:
        raise ValueError("OWUI_API_KEY no configurado")

    url = f"{OWUI_BASE_URL.rstrip('/')}/api/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OWUI_API_KEY}",
    }
    messages = [{"role": "user", "content": prompt}]

    for iteration in range(8):
        print(f"\n[Iteración {iteration + 1}] Llamando al modelo...")
        payload = {"model": model, "messages": messages}
        if tool_ids:
            payload["tool_ids"] = tool_ids

        resp = requests.post(url, headers=headers, json=payload)
        resp.raise_for_status()

        result  = resp.json()
        choice  = result["choices"][0]
        message = choice["message"]
        finish  = choice["finish_reason"]
        print(f"  finish_reason: {finish}")

        if finish == "stop":
            return message["content"]

        if finish == "tool_calls":
            messages.append({
                "role": "assistant",
                "content": message.get("content"),
                "tool_calls": message["tool_calls"],
            })
            for tc in message["tool_calls"]:
                tool_name = tc["function"]["name"]
                tool_args = loads(tc["function"]["arguments"])
                print(f"\n  → tool: {tool_name}")
                tool_result = call_tool(tool_name, tool_args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })
            continue

        break

    raise RuntimeError("Máximo de iteraciones alcanzado.")


def main():
    prompt = "estoy buscando audífonos, ¿cuáles tienes disponibles?"
    content = chat_with_tools(prompt, model="asistente-de-ventas", tool_ids=["server:0"])
    print("\n" + "=" * 50)
    print("RESPUESTA FINAL:")
    print("=" * 50)
    print(content)


if __name__ == "__main__":
    main()
