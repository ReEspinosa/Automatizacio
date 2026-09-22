"""
Instagram Comment-to-DM Automation
===================================
Cuando alguien comenta "PISA" en un Reel o post de Instagram,
se le envía automáticamente un DM privado con el enlace al repositorio de GitHub.

Usa la Instagram Graph API (vía Facebook Login) + Webhooks de Meta.
"""

import os
import json
import logging
from flask import Flask, request, jsonify
import requests

# --- Configuración ---
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Variables de entorno (se configuran en el servidor de despliegue — NUNCA en el código)
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "mi_token_secreto_123")
INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID")
PAGE_ID = os.getenv("PAGE_ID")

# --- Configuración de la automatización ---
KEYWORD = os.getenv("KEYWORD", "pisa").lower()

# Enlace que se envía por DM
REPO_LINK = os.getenv("REPO_LINK", "https://github.com/ReEspinosa/PISA-MX")

# Texto del DM que acompaña al enlace
DM_MESSAGE = os.getenv("DM_MESSAGE",
    "¡Hola! Gracias por tu interés en PISA. Aquí tienes el repositorio con todo el análisis:"
)

# Texto del botón
BUTTON_TEXT = os.getenv("BUTTON_TEXT", "Ver repositorio")

# Para evitar mandar DM duplicados al mismo comentario
processed_comments = set()

# --- API de Meta ---
GRAPH_API_URL = "https://graph.facebook.com/v26.0"


def send_private_reply_with_button(comment_id: str) -> bool:
    """
    Envía un DM privado como respuesta a un comentario, con un botón
    que abre el enlace del repositorio de GitHub.
    """
    url = f"{GRAPH_API_URL}/{PAGE_ID}/messages"
    payload = {
        "recipient": {"comment_id": comment_id},
        "message": {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "button",
                    "text": DM_MESSAGE,
                    "buttons": [
                        {
                            "type": "web_url",
                            "url": REPO_LINK,
                            "title": BUTTON_TEXT,
                        }
                    ],
                },
            }
        },
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {PAGE_ACCESS_TOKEN}",
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        data = response.json()

        if response.ok:
            logger.info(f"DM con botón enviado para comentario {comment_id}")
            return True
        else:
            logger.error(f"Error al enviar DM con botón: {data}")
            return send_private_reply_text(comment_id)

    except Exception as e:
        logger.error(f"Excepción al enviar DM con botón: {e}")
        return send_private_reply_text(comment_id)


def send_private_reply_text(comment_id: str) -> bool:
    """
    Fallback: envía el DM como texto simple con el enlace pegado.
    Se usa si la plantilla con botón falla.
    """
    url = f"{GRAPH_API_URL}/{PAGE_ID}/messages"
    full_message = f"{DM_MESSAGE}\n\n{REPO_LINK}"
    payload = {
        "recipient": {"comment_id": comment_id},
        "message": {"text": full_message},
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {PAGE_ACCESS_TOKEN}",
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        data = response.json()
        if response.ok:
            logger.info(f"DM de texto enviado para comentario {comment_id}")
            return True
        else:
            logger.error(f"Error al enviar DM de texto: {data}")
            return False
    except Exception as e:
        logger.error(f"Excepción al enviar DM de texto: {e}")
        return False


# --- Webhook Endpoints ---

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """
    Meta envía un GET para verificar que el servidor es real.
    Responde con el hub.challenge si el token coincide.
    """
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Webhook verificado correctamente")
        return challenge, 200
    else:
        logger.warning("Verificación fallida — token incorrecto")
        return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def handle_webhook():
    """
    Meta envía un POST cada vez que hay un nuevo comentario.
    Filtra por la keyword y envía el DM con el link del repo.
    """
    data = request.get_json()
    logger.info(f"Webhook recibido: {json.dumps(data, indent=2)}")

    if data.get("object") != "instagram":
        return "OK", 200

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "comments":
                continue

            value = change.get("value", {})
            comment_id = value.get("id")
            comment_text = value.get("text", "").lower()
            commenter = value.get("from", {}).get("username", "desconocido")
            from_id = value.get("from", {}).get("id", "")

            if comment_id in processed_comments:
                logger.info(f"Comentario {comment_id} ya procesado")
                continue

            if from_id == INSTAGRAM_ACCOUNT_ID:
                logger.info("Comentario propio, saltando")
                continue

            logger.info(f"Comentario de @{commenter}: '{value.get('text', '')}'")

            if KEYWORD in comment_text:
                logger.info(f"Keyword '{KEYWORD}' detectada — enviando link del repo...")
                processed_comments.add(comment_id)
                send_private_reply_with_button(comment_id)
            else:
                logger.info(f"No contiene '{KEYWORD}', ignorando")

    return "OK", 200


@app.route("/privacy", methods=["GET"])
def privacy_policy():
    """Política de privacidad requerida por Meta para publicar la app."""
    html = """
    <html>
    <head><title>Política de Privacidad - Automatizacion</title></head>
    <body style="font-family: sans-serif; max-width: 700px; margin: 40px auto; line-height: 1.6;">
    <h1>Política de Privacidad</h1>
    <p>Última actualización: 2026.</p>
    <p>Esta aplicación ("Automatizacion") es una herramienta personal que automatiza
    el envío de mensajes directos (DM) en Instagram como respuesta a comentarios
    que contienen una palabra clave específica en publicaciones de la cuenta
    propietaria de la app.</p>
    <h2>Qué datos se procesan</h2>
    <p>La app procesa únicamente el contenido de los comentarios públicos de
    Instagram (texto del comentario, ID del comentario y nombre de usuario de
    quien comenta) con el único fin de detectar la palabra clave y enviar una
    respuesta automática. No se almacena esta información de forma permanente
    ni se comparte con terceros.</p>
    <h2>Uso de tokens de acceso</h2>
    <p>Los tokens de acceso a la API de Meta se almacenan de forma segura como
    variables de entorno del servidor y no se exponen públicamente ni se
    comparten con terceros.</p>
    <h2>Contacto</h2>
    <p>Para dudas sobre esta política, contactar a: rebeca07e.r@gmail.com</p>
    </body>
    </html>
    """
    return html


@app.route("/terms", methods=["GET"])
def terms_of_service():
    """Condiciones del servicio requeridas por Meta para publicar la app."""
    html = """
    <html>
    <head><title>Condiciones del Servicio - Automatizacion</title></head>
    <body style="font-family: sans-serif; max-width: 700px; margin: 40px auto; line-height: 1.6;">
    <h1>Condiciones del Servicio</h1>
    <p>Esta aplicación es una herramienta personal de automatización para la
    cuenta de Instagram de su propietaria. No está destinada a uso comercial
    por terceros. El uso de esta app está sujeto a las políticas de la
    Plataforma de Meta.</p>
    <p>Contacto: rebeca07e.r@gmail.com</p>
    </body>
    </html>
    """
    return html


@app.route("/data-deletion", methods=["GET", "POST"])
def data_deletion():
    """Instrucciones de eliminación de datos requeridas por Meta."""
    html = """
    <html>
    <head><title>Eliminación de Datos - Automatizacion</title></head>
    <body style="font-family: sans-serif; max-width: 700px; margin: 40px auto; line-height: 1.6;">
    <h1>Eliminación de Datos</h1>
    <p>Esta app no almacena datos personales de forma permanente. Los
    comentarios procesados solo se guardan temporalmente en memoria del
    servidor para evitar respuestas duplicadas, y se eliminan automáticamente
    al reiniciarse el servicio.</p>
    <p>Si deseas solicitar la eliminación de cualquier dato relacionado con tu
    interacción con esta app, escribe a: rebeca07e.r@gmail.com</p>
    </body>
    </html>
    """
    return html


@app.route("/", methods=["GET"])
def health_check():
    """Endpoint de salud para verificar que el servidor está vivo."""
    return jsonify({
        "status": "ok",
        "app": "Instagram Comment-to-DM (GitHub link)",
        "keyword": KEYWORD,
        "repo_link": REPO_LINK,
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
