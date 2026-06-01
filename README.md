# Open WebUI + Ecommerce Tool Integration

Este README describe las 6 herramientas (`tool_ids`) que el agente puede usar contra la API de ecommerce. Cada herramienta documenta la ruta, el método HTTP, los parámetros o el body JSON obligatorio y opcional, y una breve explicación de su propósito.

## Requisitos

- `OWUI_API_KEY`: token Bearer para Open WebUI
- `OWUI_BASE_URL`: base URL de Open WebUI (por defecto `http://localhost:3000`)
- `ECOMMERCE_API_KEY`: token Bearer para la API de ecommerce
- `ECOMMERCE_BASE_URL`: la URL de la API de ecommerce (`https://api-development-5d8c.up.railway.app`)

## Tool map usados

El agente usa `tool_ids=["server:0"]` en Open WebUI. El `tool_name` que envía el modelo corresponde a las siguientes herramientas:

| tool_name | API endpoint | Método | Descripción |
|---|---|---|---|
| `search_catalog` | `/v1/catalog/search` | POST | Busca productos en catálogo por texto y filtros. |
| `list_catalog_products` | `/v1/catalog/products` | GET | Lista productos del catálogo con paginación y categoría. |
| `get_catalog_product` | `/v1/catalog/products/{product_id}` | GET | Obtiene detalles de un producto por su id. |
| `lookup_catalog_inventory` | `/v1/catalog/inventory-lookup` | POST | Consulta inventario para una lista de productos. |
| `compare_catalog_products` | `/v1/catalog/comparisons` | POST | Compara varios productos seleccionados. |
| `suggest_cross_sell_products` | `/v1/catalog/cross-sell-suggestions` | POST | Sugiere productos complementarios para venta cruzada. |

## Headers comunes

Todos los llamados a la API de ecommerce deben incluir:

```http
Authorization: Bearer <ECOMMERCE_API_KEY>
Content-Type: application/json
```

---

## 1. search_catalog

- Ruta: `POST /v1/catalog/search`
- Request body: JSON

```json
{
  "tenant_id": "string",
  "query": "string",
  "top_k": 3,
  "filters": { ... }
}
```

- `tenant_id` (string, requerido): identificador del tenant.
- `query` (string, requerido): término de búsqueda libre.
- `top_k` (integer, opcional): máximo de resultados, entre 1 y 10. Default: 3.
- `filters` (object|null, opcional): filtros adicionales de catálogo.

Breve: busca productos en el catálogo según texto y condiciones adicionales.

---

## 2. list_catalog_products

- Ruta: `GET /v1/catalog/products`
- Query params:

| Parámetro | Tipo | Requerido | Descripción |
|---|---|---|---|
| `tenant_id` | string | sí | Tenant que solicita el catálogo. |
| `limit` | integer | no | Número máximo de productos. Default: 100. |
| `offset` | integer | no | Desplazamiento para paginación. Default: 0. |
| `category` | string/null | no | Filtra por categoría. |

Breve: lista productos del catálogo del tenant con paginación y categoría opcional.

---

## 3. get_catalog_product

- Ruta: `GET /v1/catalog/products/{product_id}`
- Path param:
  - `product_id` (string, requerido)
- Query params:
  - `tenant_id` (string, requerido)

Breve: obtiene la ficha completa de un producto específico.

---

## 4. lookup_catalog_inventory

- Ruta: `POST /v1/catalog/inventory-lookup`
- Request body: JSON

```json
{
  "tenant_id": "string",
  "product_ids": ["string", "string"]
}
```

- `tenant_id` (string, requerido)
- `product_ids` (array[string], requerido): lista de ids de producto, 1 a 20.

Breve: consulta disponibilidad e inventario de los productos pedidos.

---

## 5. compare_catalog_products

- Ruta: `POST /v1/catalog/comparisons`
- Request body: JSON

```json
{
  "tenant_id": "string",
  "product_ids": ["string", "string"]
}
```

- `tenant_id` (string, requerido)
- `product_ids` (array[string], requerido): lista de 2 a 5 ids de producto.

Breve: compara atributos de varios productos para ayudar en la elección.

---

## 6. suggest_cross_sell_products

- Ruta: `POST /v1/catalog/cross-sell-suggestions`
- Request body: JSON

```json
{
  "tenant_id": "string",
  "product_id": "string",
  "context": { ... }
}
```

- `tenant_id` (string, requerido)
- `product_id` (string, requerido)
- `context` (object|null, opcional): contexto extra para mejorar sugerencias.

Breve: sugiere productos complementarios para venta cruzada basada en un producto base.

---

## Ejemplo de llamada desde el agente

El modelo puede devolver una llamada a herramienta con este formato:

```json
{
  "function": {
    "name": "search_catalog",
    "arguments": "{\"tenant_id\": \"123\", \"query\": \"audífonos bluetooth\"}"
  }
}
```

El backend debe ejecutar la tool real y luego enviar el resultado al historial como role `tool`.

---

## Recomendación

Usa estas 6 herramientas exclusivamente para las consultas de catálogo e inventario, y deja que el agente volteé a Open WebUI para la coordinación de `tool_calls`.
