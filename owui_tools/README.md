# OpenWebUI Tools (versionado)

Este folder versiona las **tools nativas de OpenWebUI** que usa el proyecto.

> ⚠️ Estos scripts **NO los ejecuta este repo**. Viven y se ejecutan del lado de
> OpenWebUI (Workspace → Tools). Aquí solo se guardan para control de cambios.
> Para desplegar/actualizar una tool, copia el contenido del archivo y pégalo en
> la tool correspondiente dentro de OpenWebUI.

## Tools

### `format_response.py`
- **Asistente que la usa**: `asistente-de-ventas-formateo-respuestas` (agente
  formateador global, ver spec `007-structured-response-formatter`).
- **Propósito**: estructurar la respuesta final para WhatsApp (`messageType`,
  `body`, `escalate`, `buttons`, `listSections`, `listButtonText`, `quote`).
- **Mejoras vs. versión inicial**:
  - Descripciones más claras de cuándo/cómo usar cada campo.
  - Validación de esquema por tipo (`text`/`buttons`/`list`) con **errores
    explícitos y accionables** (`{"error": true, "field", "message", "hint"}`)
    para que el subagente corrija y reintente.
  - Rechaza **duplicar las opciones dentro del `body`** (las opciones van solo en
    sus campos).
  - Límites de WhatsApp validados (máx. botones/filas y longitudes de títulos).
  - Normalización defensiva de `FieldInfo`/tipos para evitar el error
    "Object of type FieldInfo is not JSON serializable".

## Despliegue manual
1. Abre OpenWebUI → Workspace → Tools.
2. Crea/edita la tool y pega el contenido del `.py` correspondiente.
3. Asígnala al asistente indicado.
