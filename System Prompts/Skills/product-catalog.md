---
name: product-catalog
description: This feature allows you to consult the online store's product catalog, which includes descriptions, prices, inventory availability, and cross-reference recommendations.
---

# Skills: product-catalog

Estas tools permiten consultar el catálogo de productos del tenant.

> **IMPORTANTE — product_id siempre es UUID**
> El campo `product_id` es el identificador interno del producto (UUID, formato `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`).
> **Nunca uses un SKU** (ej. `sku-010`) como `product_id` — causará error 422.
> Para obtener el UUID de un producto, primero llama `search_catalog` o `list_catalog_products`.

---

## Manejo de errores

- Si una tool retorna un error, **NO inventes** información ni continúes como si hubiera funcionado.
- Ante cualquier error de tool, detente y responde al usuario con el mensaje de error genérico definido en tu system prompt.
- Error 422 con `product_id`: usaste un SKU en lugar de un UUID. Llama primero a `search_catalog` para obtener el UUID real.

---

## 1. search_catalog

Busca productos en el catálogo según texto libre y filtros opcionales.

```yaml
name: search_catalog
description: Busca productos en el catálogo del tenant por texto libre y filtros opcionales.
input_schema:
  type: object
  properties:
    tenant_id:
      type: string
      description: Identificador del tenant. Usar siempre el tenant_id del parámetro interno.
    query:
      type: string
      description: Texto libre de búsqueda (ej. "audífonos bluetooth", "lámpara led").
    top_k:
      type: integer
      description: Máximo de resultados a devolver. Entre 1 y 10. Default 3.
    filters:
      type: object
      description: Filtros adicionales opcionales (categoría, precio, etc.).
      nullable: true
  required:
    - tenant_id
    - query
```

- Ruta: `POST /v1/catalog/search`
- Devuelve lista de productos con su `id` (UUID), nombre, precio y stock.

---

## 2. list_catalog_products

Lista todos los productos del tenant con paginación y filtro de categoría opcional.

```yaml
name: list_catalog_products
description: Lista productos del catálogo del tenant con paginación y filtro de categoría.
input_schema:
  type: object
  properties:
    tenant_id:
      type: string
      description: Identificador del tenant.
    limit:
      type: integer
      description: Número máximo de productos a devolver. Default 100.
    offset:
      type: integer
      description: Desplazamiento para paginación. Default 0.
    category:
      type: string
      description: Filtra por categoría de producto. Opcional.
      nullable: true
  required:
    - tenant_id
```

- Ruta: `GET /v1/catalog/products`
- Devuelve lista con `id` (UUID) de cada producto.

---

## 3. get_catalog_product

Obtiene la ficha completa de un producto específico por su UUID.

```yaml
name: get_catalog_product
description: Obtiene la ficha completa de un producto por su UUID interno.
input_schema:
  type: object
  properties:
    product_id:
      type: string
      format: uuid
      description: >
        UUID del producto (formato xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx).
        Obtenido de search_catalog o list_catalog_products.
        NUNCA usar un SKU aquí.
    tenant_id:
      type: string
      description: Identificador del tenant.
  required:
    - product_id
    - tenant_id
```

- Ruta: `GET /v1/catalog/products/{product_id}`

---

## 4. lookup_catalog_inventory

Consulta disponibilidad e inventario de uno o varios productos por sus UUIDs.

```yaml
name: lookup_catalog_inventory
description: Consulta disponibilidad e inventario de productos por sus UUIDs internos.
input_schema:
  type: object
  properties:
    tenant_id:
      type: string
      description: Identificador del tenant.
    product_ids:
      type: array
      items:
        type: string
        format: uuid
      description: >
        Lista de UUIDs de productos (1 a 20).
        Cada elemento debe ser un UUID obtenido de search_catalog o list_catalog_products.
        NUNCA usar SKUs aquí.
      minItems: 1
      maxItems: 20
  required:
    - tenant_id
    - product_ids
```

- Ruta: `POST /v1/catalog/inventory-lookup`

---

## 5. compare_catalog_products

Compara atributos de 2 a 5 productos para facilitar la elección del cliente.

```yaml
name: compare_catalog_products
description: Compara atributos de 2 a 5 productos para ayudar al cliente a elegir.
input_schema:
  type: object
  properties:
    tenant_id:
      type: string
      description: Identificador del tenant.
    product_ids:
      type: array
      items:
        type: string
        format: uuid
      description: >
        Lista de 2 a 5 UUIDs de productos a comparar.
        Obtener UUIDs previamente con search_catalog o list_catalog_products.
      minItems: 2
      maxItems: 5
  required:
    - tenant_id
    - product_ids
```

- Ruta: `POST /v1/catalog/comparisons`

---

## 6. suggest_cross_sell_products

Sugiere productos complementarios para venta cruzada a partir de un producto base.

```yaml
name: suggest_cross_sell_products
description: Sugiere productos complementarios (cross-sell) para un producto base dado su UUID.
input_schema:
  type: object
  properties:
    tenant_id:
      type: string
      description: Identificador del tenant.
    product_id:
      type: string
      format: uuid
      description: >
        UUID del producto base (formato xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx).
        NUNCA pasar un SKU (ej. "sku-010") — causará error 422.
        Si solo tienes el nombre o SKU del producto, llama primero a search_catalog
        para obtener el UUID real.
    context:
      type: object
      description: Contexto adicional para mejorar las sugerencias (categoría, caso de uso, etc.). Opcional.
      nullable: true
  required:
    - tenant_id
    - product_id
```

- Ruta: `POST /v1/catalog/cross-sell-suggestions`

---

## Flujo correcto para usar product_id

```
1. search_catalog(query="nombre del producto") → devuelve [{id: "uuid-real", ...}]
2. suggest_cross_sell_products(product_id="uuid-real") ✅

❌ INCORRECTO: suggest_cross_sell_products(product_id="sku-010")
```
