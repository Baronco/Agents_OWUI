"""
OpenWebUI native tool: format_response
======================================

Estructura la respuesta final del asistente para WhatsApp. Esta tool vive y se
EJECUTA del lado de OpenWebUI (Workspace -> Tools), NO la ejecuta este repo.
Se versiona aquí únicamente para tener control de cambios; para desplegarla,
copia/pega este contenido en la tool nativa de OpenWebUI.

Asistente que la usa: `asistente-de-ventas-formateo-respuestas` (agente
formateador global). Debe ser SIEMPRE el último paso de cada respuesta.

Diseño:
- Devuelve un JSON string. En éxito: el objeto estructurado con los 7 campos.
- En error de esquema: un JSON con `{"error": true, ...}` y un mensaje explícito
  + `hint` accionable, para que el subagente CORRIJA y vuelva a llamar la tool.
- Valida cada caso (text/buttons/list) y rechaza duplicar las opciones dentro
  del `body` (las opciones van en sus campos, no enumeradas en el texto).
"""

import json
from pydantic import Field

# --- Límites del canal WhatsApp -------------------------------------------------
MAX_BUTTONS = 3
MAX_BUTTON_TITLE = 20
MAX_LIST_ROWS = 10
MAX_ROW_TITLE = 24
MAX_LIST_BUTTON_TEXT = 20
VALID_TYPES = ("text", "buttons", "list")


def _err(field: str, message: str, hint: str) -> str:
    """Error explícito y accionable para el subagente formateador."""
    return json.dumps(
        {"error": True, "field": field, "message": message, "hint": hint},
        ensure_ascii=False,
    )


def _coerce_str(value, default: str = "") -> str:
    """OpenWebUI a veces deja el FieldInfo sin resolver para opcionales no
    enviados; lo normalizamos a su default para que json.dumps no falle."""
    return value if isinstance(value, str) else default


def _parse_json(raw: str, field: str):
    """Devuelve (parsed, error_str). error_str es None si parseó bien."""
    try:
        return json.loads(raw), None
    except (json.JSONDecodeError, TypeError):
        return None, _err(
            field,
            f"El campo '{field}' no es un JSON string válido.",
            "Envía un JSON string correctamente escapado, ej. "
            '\'[{"id":"opc_1","title":"Opción 1"}]\'.',
        )


def _body_enumerates(body: str, titles: list) -> bool:
    """Heurística: el body no debe re-enumerar las opciones (van en sus campos).
    Marca duplicación si 2+ títulos aparecen literal dentro del body."""
    low = body.lower()
    hits = sum(1 for t in titles if t and t.lower() in low)
    return hits >= 2


class Tools:
    def __init__(self):
        pass

    def format_response(
        self,
        messageType: str = Field(
            ...,
            description=(
                'Tipo de mensaje WhatsApp. EXACTAMENTE uno de: "text", "buttons", '
                '"list". Usa "text" para respuestas conversacionales; "buttons" '
                "para 2-3 opciones cerradas; \"list\" para 4-10 opciones agrupadas."
            ),
        ),
        body: str = Field(
            ...,
            description=(
                "Texto principal mostrado al cliente. Requerido, no vacío, máx. "
                "6-8 líneas. NO enumeres aquí las opciones de botones/lista: esas "
                "van SOLO en sus campos. El body es el texto introductorio + "
                "pregunta/cierre."
            ),
        ),
        escalate: bool = Field(
            False,
            description="true si el caso debe escalar a un humano. Por defecto false.",
        ),
        buttons: str = Field(
            "",
            description=(
                "Array JSON de botones. REQUERIDO si messageType=='buttons'; "
                'string vacío "" en otro caso. Formato: '
                '\'[{"id":"opc_1","title":"Título"}]\'. Máx. 3 botones, título '
                "≤ 20 chars. El 'id' es lo que regresa WhatsApp al tocar el botón "
                "(usa product_id u opciones estables)."
            ),
        ),
        listSections: str = Field(
            "",
            description=(
                "Array JSON de secciones. REQUERIDO si messageType=='list'; "
                'string vacío "" en otro caso. Formato: '
                '\'[{"title":"Categoría","rows":[{"id":"sku-010","title":"X",'
                '"description":"desc"}]}]\'. Máx. 10 filas en total, título de '
                "fila ≤ 24 chars. El 'id' de cada fila es lo que regresa WhatsApp."
            ),
        ),
        listButtonText: str = Field(
            "",
            description=(
                "Texto del botón que abre la lista. REQUERIDO si "
                'messageType=="list"; vacío "" en otro caso. Máx. 20 chars. '
                'Ej. "Ver opciones".'
            ),
        ),
        quote: str = Field(
            "",
            description=(
                "JSON string con datos de cotización en curso, o vacío \"\" si no "
                "hay. Ej. '{\"items\":[{\"product_id\":\"sku-010\",\"quantity\":2}]}'."
            ),
        ),
    ) -> str:
        """
        Formatea y VALIDA la respuesta estructurada para WhatsApp.
        SIEMPRE es el último paso de cada respuesta.

        Devuelve el JSON estructurado en éxito, o un JSON {"error": true, ...}
        con instrucción de corrección si el esquema es inválido — en ese caso
        CORRIGE los argumentos y vuelve a llamar a format_response.
        """
        # --- Normalización defensiva (FieldInfo / tipos) -----------------------
        if not isinstance(escalate, bool):
            escalate = str(escalate).strip().lower() in ("true", "1", "yes", "sí", "si")
        buttons = _coerce_str(buttons)
        listSections = _coerce_str(listSections)
        listButtonText = _coerce_str(listButtonText)
        quote = _coerce_str(quote)
        messageType = messageType if isinstance(messageType, str) else ""
        body = body if isinstance(body, str) else ""

        # --- Validaciones comunes ---------------------------------------------
        if messageType not in VALID_TYPES:
            return _err(
                "messageType",
                f"messageType='{messageType}' inválido.",
                f"Usa exactamente uno de: {', '.join(VALID_TYPES)}.",
            )
        if not body.strip():
            return _err(
                "body",
                "El campo 'body' es obligatorio y no puede estar vacío.",
                "Escribe el texto introductorio + la pregunta/cierre para el cliente.",
            )

        # --- Validación por tipo ----------------------------------------------
        if messageType == "text":
            if buttons.strip() or listSections.strip() or listButtonText.strip():
                return _err(
                    "messageType",
                    "Con messageType='text', buttons/listSections/listButtonText "
                    "deben ir vacíos.",
                    'Deja esos campos como "" o cambia messageType a "buttons"/"list".',
                )

        elif messageType == "buttons":
            if not buttons.strip():
                return _err(
                    "buttons",
                    "messageType='buttons' requiere el campo 'buttons'.",
                    'Envía un array JSON, ej. \'[{"id":"opc_1","title":"Cotizar"}]\'.',
                )
            parsed, perr = _parse_json(buttons, "buttons")
            if perr:
                return perr
            if not isinstance(parsed, list) or not parsed:
                return _err(
                    "buttons", "'buttons' debe ser un array JSON no vacío.",
                    "Incluye entre 1 y 3 objetos con 'id' y 'title'.",
                )
            if len(parsed) > MAX_BUTTONS:
                return _err(
                    "buttons", f"Máximo {MAX_BUTTONS} botones (recibidos {len(parsed)}).",
                    f"Reduce a {MAX_BUTTONS} o usa messageType='list'.",
                )
            for i, b in enumerate(parsed):
                if not isinstance(b, dict) or not b.get("id") or not b.get("title"):
                    return _err(
                        "buttons", f"El botón #{i + 1} necesita 'id' y 'title' no vacíos.",
                        '{"id":"opc_1","title":"Texto"}.',
                    )
                if len(str(b["title"])) > MAX_BUTTON_TITLE:
                    return _err(
                        "buttons",
                        f"Título de botón '{b['title']}' supera {MAX_BUTTON_TITLE} chars.",
                        "Acorta el título.",
                    )
            titles = [str(b.get("title", "")) for b in parsed]
            if _body_enumerates(body, titles):
                return _err(
                    "body",
                    "No enumeres las opciones de los botones dentro del 'body'.",
                    "Deja el body como texto introductorio; las opciones van solo "
                    "en 'buttons'.",
                )

        elif messageType == "list":
            if not listSections.strip():
                return _err(
                    "listSections", "messageType='list' requiere 'listSections'.",
                    'Envía un array JSON de secciones con sus rows.',
                )
            if not listButtonText.strip():
                return _err(
                    "listButtonText", "messageType='list' requiere 'listButtonText'.",
                    'Ej. "Ver opciones" (máx. 20 chars).',
                )
            if len(listButtonText) > MAX_LIST_BUTTON_TEXT:
                return _err(
                    "listButtonText",
                    f"listButtonText supera {MAX_LIST_BUTTON_TEXT} chars.",
                    "Acórtalo.",
                )
            parsed, perr = _parse_json(listSections, "listSections")
            if perr:
                return perr
            if not isinstance(parsed, list) or not parsed:
                return _err(
                    "listSections", "'listSections' debe ser un array JSON no vacío.",
                    'Cada sección: {"title":"...","rows":[...]}.',
                )
            all_titles = []
            total_rows = 0
            for s, section in enumerate(parsed):
                if not isinstance(section, dict) or not isinstance(section.get("rows"), list):
                    return _err(
                        "listSections",
                        f"La sección #{s + 1} necesita 'title' y 'rows' (array).",
                        '{"title":"Categoría","rows":[{"id":"x","title":"X"}]}.',
                    )
                for r, row in enumerate(section["rows"]):
                    total_rows += 1
                    if not isinstance(row, dict) or not row.get("id") or not row.get("title"):
                        return _err(
                            "listSections",
                            f"La fila #{r + 1} de la sección #{s + 1} necesita 'id' y 'title'.",
                            '{"id":"sku-010","title":"Producto","description":"..."}.',
                        )
                    if len(str(row["title"])) > MAX_ROW_TITLE:
                        return _err(
                            "listSections",
                            f"Título de fila '{row['title']}' supera {MAX_ROW_TITLE} chars.",
                            "Acorta el título de la fila.",
                        )
                    all_titles.append(str(row["title"]))
            if total_rows == 0:
                return _err(
                    "listSections", "La lista no tiene filas.",
                    "Agrega al menos una fila con 'id' y 'title'.",
                )
            if total_rows > MAX_LIST_ROWS:
                return _err(
                    "listSections",
                    f"Máximo {MAX_LIST_ROWS} filas en total (recibidas {total_rows}).",
                    "Reduce las filas o reparte en otra interacción.",
                )
            if _body_enumerates(body, all_titles):
                return _err(
                    "body",
                    "No enumeres las opciones de la lista dentro del 'body'.",
                    "Deja el body como texto introductorio; las opciones van solo "
                    "en 'listSections'.",
                )

        # --- quote opcional ----------------------------------------------------
        if quote.strip():
            parsed_q, qerr = _parse_json(quote, "quote")
            if qerr:
                return qerr
            if not isinstance(parsed_q, dict):
                return _err(
                    "quote", "'quote' debe ser un objeto JSON.",
                    '{"items":[{"product_id":"sku-010","quantity":2}]}.',
                )

        # --- Éxito: objeto estructurado ---------------------------------------
        return json.dumps(
            {
                "messageType": messageType,
                "body": body,
                "escalate": escalate,
                "buttons": buttons,
                "listSections": listSections,
                "listButtonText": listButtonText,
                "quote": quote,
            },
            ensure_ascii=False,
        )
