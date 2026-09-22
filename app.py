"""
Instagram Comment-to-DM Automation
===================================
Cuando alguien comenta "PISA" en tus Reels/posts de Instagram,
se le envía automáticamente un DM privado con el enlace a tu PDF (Google Drive).

Usa la Instagram Graph API (vía Facebook Login) + Webhooks.

NOTA sobre archivos: la API de Instagram NO permite adjuntar PDFs directamente.
Por eso enviamos el enlace de descarga de Google Drive dentro del mensaje.
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

# Variables de entorno (se configuran en Render — NUNCA en el código)
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "mi_token_secreto_123")
INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID")
PAGE_ID = os.getenv("PAGE_ID")

# --- Configuración de la automatización ---
# Palabra clave que dispara el DM (no importan mayúsculas/minúsculas)
KEYWORD = os.getenv("KEYWORD", "pisa").lower()

# Enlace de descarga de tu PDF en Google Drive
# (Ver README para cómo obtener el link de descarga directa)
PDF_LINK = os.getenv("PDF_LINK", "https://drive.google.com/tu-enlace-aqui")

# Texto del DM que acompaña al enlace
DM_MESSAGE = os.getenv("DM_MESSAGE",
    "¡Hola! 👋 Gracias por tu interés. "
    "Aquí tienes el documento que pediste 📄"
)

# Texto del botón que abre el PDF
BUTTON_TEXT = os.getenv("BUTTON_TEXT", "📄 Descargar PDF")

# Para evitar mandar DM duplicados al mismo comentario
processed_comments = set()

# --- API de Meta ---
GRAPH_API_URL = "https://graph.facebook.com/v26.0"


def send_private_reply_with_button(comment_id: str) -> bool:
    """
    Envía un DM privado como respuesta a un comentario, con un botón
    que abre el enlace del PDF (Google Drive).

    Usa una plantilla de botón (button template) con un botón tipo web_url.
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
                            "url": PDF_LINK,
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
            logger.info(f"✅ DM con botón enviado para comentario {comment_id}")
            return True
        else:
            logger.error(f"❌ Error al enviar DM con botón: {data}")
            # Si falla el botón (a veces por permisos), intentamos texto simple
            return send_private_reply_text(comment_id)

    except Exception as e:
        logger.error(f"❌ Excepción al enviar DM con botón: {e}")
        return send_private_reply_text(comment_id)


def send_private_reply_text(comment_id: str) -> bool:
    """
    Fallback: envía el DM como texto simple con el enlace pegado.
    Se usa si la plantilla con botón falla.
    """
    url = f"{GRAPH_API_URL}/{PAGE_ID}/messages"
    full_message = f"{DM_MESSAGE}\n\n{PDF_LINK}"
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
            logger.info(f"✅ DM de texto enviado para comentario {comment_id}")
            return True
        else:
            logger.error(f"❌ Error al enviar DM de texto: {data}")
            return False
    except Exception as e:
        logger.error(f"❌ Excepción al enviar DM de texto: {e}")
        return False


# --- Webhook Endpoints ---

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """
    Meta envía un GET para verificar que tu servidor es real.
    Debe responder con el hub.challenge si el token coincide.
    """
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("✅ Webhook verificado correctamente")
        return challenge, 200
    else:
        logger.warning("⚠️ Verificación fallida — token incorrecto")
        return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def handle_webhook():
    """
    Meta envía un POST cada vez que hay un nuevo comentario.
    Filtramos por la keyword y enviamos el DM con el PDF.
    """
    data = request.get_json()
    logger.info(f"📩 Webhook recibido: {json.dumps(data, indent=2)}")

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

            # Evitar duplicados
            if comment_id in processed_comments:
                logger.info(f"⏭️ Comentario {comment_id} ya procesado")
                continue

            # Evitar responder a tus propios comentarios
            if from_id == INSTAGRAM_ACCOUNT_ID:
                logger.info("⏭️ Comentario propio, saltando")
                continue

            logger.info(f"💬 @{commenter}: '{value.get('text', '')}'")

            # ¿Contiene la keyword?
            if KEYWORD in comment_text:
                logger.info(f"🎯 Keyword '{KEYWORD}' detectada — enviando PDF...")
                processed_comments.add(comment_id)
                send_private_reply_with_button(comment_id)
            else:
                logger.info(f"⏭️ No contiene '{KEYWORD}', ignorando")

    return "OK", 200


@app.route("/", methods=["GET"])
def health_check():
    """Endpoint de salud para verificar que el servidor está vivo."""
    return jsonify({
        "status": "ok",
        "app": "Instagram Comment-to-DM (PDF)",
        "keyword": KEYWORD,
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
