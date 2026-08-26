# OpenWebUI Tools (versionado)

Este folder versiona las **tools nativas de OpenWebUI** que usa el proyecto.

> ⚠️ Estos scripts **NO los ejecuta este repo**. Viven y se ejecutan del lado de
> OpenWebUI (Workspace → Tools). Aquí solo se guardan para control de cambios.
> Para desplegar/actualizar una tool, copia el contenido del archivo y pégalo en
> la tool correspondiente dentro de OpenWebUI.

## Tools

_No hay tools versionadas actualmente._ La tool `format_response.py` (usada por
el antiguo asistente formateador) se eliminó en el spec `014-remove-formatter-pass`;
está disponible en el historial de git si se necesita de referencia.

## Despliegue manual
1. Abre OpenWebUI → Workspace → Tools.
2. Crea/edita la tool y pega el contenido del `.py` correspondiente.
3. Asígnala al asistente indicado.
