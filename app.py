"""
Instagram Comment-to-DM (ruta: API de Instagram con inicio de sesión de Instagram)

Cuando alguien comenta la palabra clave en tus posts/reels, se le manda
un DM privado (Private Reply) con tu link.

Variables de entorno (Render):
  PAGE_ACCESS_TOKEN     Token IGAA... generado en developers (Instagram Login)
  PAGE_ID               Tu Instagram User ID (17841404548004109)
  INSTAGRAM_ACCOUNT_ID  Tu Instagram User ID (para ignorar tus propios comentarios)
  VERIFY_TOKEN          Texto que también pones en "Token de verificación" en Meta
  KEYWORD               Palabra(s) clave, separadas por coma: "pisa" o "pisa,curso"
Opcionales:
  DM_LINK               Link que se manda (default: repo PISA-MX)
  DM_MESSAGE            Texto del DM
  BUTTON_TEXT           Texto del botón
  IG_APP_SECRET         Clave secreta de la app de Instagram (valida la firma de Meta)
  GRAPH_VERSION         Versión de la API (default: v26.0)
"""

import hashlib
import hmac
import json
import logging
import os
import re
import unicodedata

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# --- Configuración ---
ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN", "")
IG_USER_ID = os.getenv("PAGE_ID", "")
INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID", IG_USER_ID)
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "")
IG_APP_SECRET = os.getenv("IG_APP_SECRET", "")
GRAPH_VERSION = os.getenv("GRAPH_VERSION", "v26.0")
GRAPH_API_URL = f"https://graph.instagram.com/{GRAPH_VERSION}"

DM_LINK = os.getenv("DM_LINK", "https://github.com/ReEspinosa/PISA-MX")
DM_MESSAGE = os.getenv(
    "DM_MESSAGE",
    "¡Hola! 👋 Gracias por comentar. Aquí tienes el repositorio con todo el análisis de PISA:",
)
BUTTON_TEXT = os.getenv("BUTTON_TEXT", "📂 Ver repositorio")

processed_comments = set()


# --- Detección de palabra clave ---
def normalize(text: str) -> str:
    """
    Deja el texto en una forma comparable:
    - NFKC convierte letras 'decoradas' (𝐏𝐈𝐒𝐀, 𝓅𝒾𝓈𝒶, ＰＩＳＡ) a letras normales
    - casefold ignora mayúsculas/minúsculas (PISA, pIsa, pisA...)
    - se quitan acentos (písa -> pisa)
    """
    text = unicodedata.normalize("NFKC", text).casefold()
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


KEYWORDS = [normalize(k.strip()) for k in os.getenv("KEYWORD", "pisa").split(",") if k.strip()]
# Palabra completa: detecta "pisa", "PISA!!", "quiero pisa 🙌", "#pisa"
# pero NO "pisada", "pisar" ni "precisa"
KEYWORD_PATTERNS = [re.compile(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])") for k in KEYWORDS]


def contains_keyword(comment_text: str) -> bool:
    text = normalize(comment_text)
    return any(p.search(text) for p in KEYWORD_PATTERNS)


# --- Seguridad: validar que el POST viene de Meta ---
def valid_signature(req) -> bool:
    if not IG_APP_SECRET:
        return True  # sin secreto configurado, no se valida
    header = req.headers.get("X-Hub-Signature-256", "")
    if not header.startswith("sha256="):
        return False
    expected = hmac.new(IG_APP_SECRET.encode(), req.get_data(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(header[7:], expected)


# --- Envío del DM ---
def _post_message(payload: dict) -> bool:
    url = f"{GRAPH_API_URL}/{IG_USER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        if r.ok:
            return True
        logger.error(f"❌ Error de Meta ({r.status_code}): {r.text}")
    except Exception as e:
        logger.error(f"❌ Excepción al enviar DM: {e}")
    return False


def send_private_reply(comment_id: str) -> bool:
    # Intento 1: mensaje con botón
    button_payload = {
        "recipient": {"comment_id": comment_id},
        "message": {
            "attachment": {
                "type": "template",
                "payload": {
                    "template_type": "button",
                    "text": DM_MESSAGE,
                    "buttons": [{"type": "web_url", "url": DM_LINK, "title": BUTTON_TEXT}],
                },
            }
        },
    }
    if _post_message(button_payload):
        logger.info(f"✅ DM con botón enviado (comentario {comment_id})")
        return True

    # Intento 2: texto simple con el link
    text_payload = {
        "recipient": {"comment_id": comment_id},
        "message": {"text": f"{DM_MESSAGE}\n\n{DM_LINK}"},
    }
    if _post_message(text_payload):
        logger.info(f"✅ DM de texto enviado (comentario {comment_id})")
        return True
    return False


# --- Webhook ---
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and VERIFY_TOKEN and token == VERIFY_TOKEN:
        logger.info("✅ Webhook verificado")
        return challenge, 200
    logger.warning("⚠️ Verificación fallida: el token no coincide")
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def handle_webhook():
    if not valid_signature(request):
        logger.warning("⚠️ Firma inválida, se ignora el POST")
        return "Invalid signature", 403

    data = request.get_json(silent=True) or {}
    logger.info(f"📩 Webhook recibido: {json.dumps(data, ensure_ascii=False)}")

    if data.get("object") != "instagram":
        return "OK", 200

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") not in ("comments", "live_comments"):
                continue

            value = change.get("value", {})
            comment_id = value.get("id")
            text = value.get("text", "")
            sender = value.get("from", {})

            if not comment_id or comment_id in processed_comments:
                continue
            if sender.get("id") == INSTAGRAM_ACCOUNT_ID:
                logger.info("⏭️ Comentario propio, se ignora")
                continue

            logger.info(f"💬 @{sender.get('username', '?')}: {text}")
            if contains_keyword(text):
                processed_comments.add(comment_id)
                logger.info("🎯 Keyword detectada, enviando DM...")
                send_private_reply(comment_id)
            else:
                logger.info("⏭️ Sin keyword, se ignora")

    return "OK", 200


@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "app": "DMS comment-to-DM", "keywords": KEYWORDS})


# --- Páginas requeridas por Meta para publicar ---
PAGE_STYLE = 'style="font-family:sans-serif;max-width:700px;margin:40px auto;line-height:1.6;"'
CONTACT = "rebeca07e.r@gmail.com"


@app.route("/privacy", methods=["GET"])
def privacy_policy():
    return f"""<html><head><title>Política de Privacidad - DMS</title></head>
<body {PAGE_STYLE}>
<h1>Política de Privacidad</h1>
<p>Esta app responde automáticamente por mensaje directo a quienes comentan una
palabra clave en publicaciones de la cuenta de Instagram de su propietaria.</p>
<h2>Datos que se procesan</h2>
<p>Solo el identificador y texto del comentario, para decidir si se envía el mensaje.
No se almacena esta información de forma permanente ni se comparte con terceros.</p>
<h2>Tokens de acceso</h2>
<p>Los tokens se guardan como variables de entorno del servidor y no se exponen públicamente.</p>
<h2>Contacto</h2><p>{CONTACT}</p>
</body></html>"""


@app.route("/terms", methods=["GET"])
def terms_of_service():
    return f"""<html><head><title>Condiciones del Servicio - DMS</title></head>
<body {PAGE_STYLE}>
<h1>Condiciones del Servicio</h1>
<p>Herramienta personal de automatización para la cuenta de Instagram de su propietaria.
Su uso está sujeto a las políticas de la Plataforma de Meta.</p>
<p>Contacto: {CONTACT}</p>
</body></html>"""


@app.route("/data-deletion", methods=["GET", "POST"])
def data_deletion():
    return f"""<html><head><title>Eliminación de Datos - DMS</title></head>
<body {PAGE_STYLE}>
<h1>Eliminación de Datos</h1>
<p>Esta app no almacena datos personales de forma permanente. Los IDs de comentarios
procesados se guardan solo en memoria para evitar duplicados y se borran al reiniciar el servicio.</p>
<p>Para solicitar la eliminación de cualquier dato, escribe a: {CONTACT}</p>
</body></html>"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
