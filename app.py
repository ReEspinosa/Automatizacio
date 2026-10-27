"""
Instagram Comment-to-DM (ruta: API de Instagram con inicio de sesión de Instagram)

Cuando alguien comenta la palabra clave en tus posts/reels, se le manda
un DM privado (Private Reply) con tu link.

Variables de entorno (Render):
  PAGE_ACCESS_TOKEN     Token IGAA... generado en developers (Instagram Login)
  PAGE_ID               Tu Instagram User ID (17841404548004109)
  INSTAGRAM_ACCOUNT_ID  Tu Instagram User ID (para ignorar tus propios comentarios)
  VERIFY_TOKEN          Texto que también pones en "Token de verificación" en Meta
  (las palabras clave, mensajes y links se configuran en CAMPAIGNS dentro de este archivo)
Opcionales:
  COMMENT_REPLIES       Respuestas públicas al comentario, separadas por |
  IG_APP_SECRET         Clave secreta de la app de Instagram (valida la firma de Meta)
  GRAPH_VERSION         Versión de la API (default: v26.0)
"""

import hashlib
import hmac
import json
import logging
import os
import random
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

# --- Palabras clave: una entrada por campaña ---
# Para agregar otra palabra, copia un bloque y cambia los valores.
CAMPAIGNS = {
    "pisa": {
        "message": "holaaa\ngraciass por tu interés en PISA, aquí tienes el drive con todo el análisis:",
        "link": "https://drive.google.com/drive/folders/1uQIzXDYUGsg4DkG7Qdf-hlW0gKSN6lRw?usp=sharing",
        "button": "📂 Ver drive",
    },
    "curso": {
        "message": "Listo, aquí tienes el link del Google AI Professional Certificate en Coursera 🤍",
        "link": "https://bit.ly/3Tg8MyK",
        "button": "🎓 Ver curso",
    },
    "fisica": {
        "message": "holaaa 🫶🏼\naquí tienes la info del Premio Nobel de Física 2026:",
        "link": "https://www.nobelprize.org/prizes/physics/2026/popular-information/",
        "button": "⚛️ Ver info",
    },
    "mexico": {
        "message": "holaaa 🫶🏼\naquí tienes los eventos de Mexico Tech Week:",
        "link": "https://www.mexicotechweek.mx/es-mx/events",
        "button": "Ver eventos",
    },
    # Para agregar otra palabra, copia un bloque de arriba y cambia los valores.
    # Agrega "followers_only": True (y gate_message / not_following_message)
    # si quieres que esa palabra sea solo para seguidores.
}
for _key, _cfg in CAMPAIGNS.items():
    _cfg["key"] = _key

# Variantes que mandan lo mismo que otra palabra
# (mayúsculas y acentos ya se ignoran solos: FÍSICA, Física, fisica... = "fisica")
CAMPAIGNS["cursos"] = CAMPAIGNS["curso"]

FOLLOW_BUTTON_TEXT = "✅ Ya te sigo"
FOLLOW_PAYLOAD_PREFIX = "FOLLOW_CHECK:"

# Respuestas públicas al comentario (se elige una al azar). En Render: separadas por |
COMMENT_REPLIES = [
    r.strip()
    for r in os.getenv(
        "COMMENT_REPLIES",
        "listooo✨|listoo, revisa tus dms💕✨|listoo, checa tus mensajes🫶🏼",
    ).split("|")
    if r.strip()
]

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


# Palabra completa: detecta "pisa", "PISA!!", "quiero pisa 🙌", "#pisa"
# pero NO "pisada", "pisar" ni "precisa"
KEYWORD_PATTERNS = [
    (re.compile(rf"(?<![a-z0-9]){re.escape(normalize(k))}(?![a-z0-9])"), cfg)
    for k, cfg in CAMPAIGNS.items()
]
KEYWORDS = list(CAMPAIGNS.keys())


def find_campaign(comment_text: str):
    """Regresa la campaña de la primera palabra clave encontrada, o None."""
    text = normalize(comment_text)
    for pattern, cfg in KEYWORD_PATTERNS:
        if pattern.search(text):
            return cfg
    return None


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


def _button_template(recipient: dict, text: str, button: dict) -> dict:
    return {
        "recipient": recipient,
        "message": {
            "attachment": {
                "type": "template",
                "payload": {"template_type": "button", "text": text, "buttons": [button]},
            }
        },
    }


def _follow_button(cfg: dict) -> dict:
    return {
        "type": "postback",
        "title": FOLLOW_BUTTON_TEXT,
        "payload": f"{FOLLOW_PAYLOAD_PREFIX}{cfg['key']}",
    }


def _link_button(cfg: dict) -> dict:
    return {"type": "web_url", "url": cfg["link"], "title": cfg["button"]}


def send_link(recipient: dict, cfg: dict) -> bool:
    """Manda el mensaje con el botón del link (o texto simple si falla)."""
    if _post_message(_button_template(recipient, cfg["message"], _link_button(cfg))):
        logger.info(f"✅ DM con botón enviado ({cfg['key']})")
        return True
    text_payload = {"recipient": recipient, "message": {"text": f"{cfg['message']}\n\n{cfg['link']}"}}
    if _post_message(text_payload):
        logger.info(f"✅ DM de texto enviado ({cfg['key']})")
        return True
    return False


def send_private_reply(comment_id: str, cfg: dict) -> bool:
    recipient = {"comment_id": comment_id}
    if cfg.get("followers_only"):
        # Primero se pide que te sigan; el link llega al tocar "Ya te sigo"
        ok = _post_message(_button_template(recipient, cfg["gate_message"], _follow_button(cfg)))
        if ok:
            logger.info(f"✅ DM de 'sígueme' enviado ({cfg['key']}, comentario {comment_id})")
        return ok
    return send_link(recipient, cfg)


# --- Verificación de seguidores ---
def user_follows_me(igsid: str):
    """True/False si el usuario te sigue; None si Meta no lo pudo confirmar."""
    try:
        r = requests.get(
            f"{GRAPH_API_URL}/{igsid}",
            params={"fields": "username,is_user_follow_business"},
            headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
            timeout=10,
        )
        if r.ok:
            data = r.json()
            follows = data.get("is_user_follow_business")
            logger.info(f"👤 @{data.get('username', '?')} te sigue: {follows}")
            return follows
        logger.error(f"❌ Error al revisar seguidor ({r.status_code}): {r.text}")
    except Exception as e:
        logger.error(f"❌ Excepción al revisar seguidor: {e}")
    return None


def handle_follow_check(sender_id: str, payload: str):
    key = payload[len(FOLLOW_PAYLOAD_PREFIX):]
    cfg = CAMPAIGNS.get(key)
    if not cfg:
        logger.warning(f"⚠️ Campaña desconocida en postback: {key}")
        return
    recipient = {"id": sender_id}
    follows = user_follows_me(sender_id)
    if follows is False:
        _post_message(_button_template(recipient, cfg["not_following_message"], _follow_button(cfg)))
        logger.info("🙅 Aún no te sigue, se le pidió de nuevo")
        return
    # True, o None si Meta no respondió (mejor mandarlo que dejarlo sin nada)
    send_link(recipient, cfg)


def reply_to_comment(comment_id: str) -> bool:
    """Responde públicamente el comentario en el post/reel."""
    if not COMMENT_REPLIES:
        return False
    reply = random.choice(COMMENT_REPLIES)
    try:
        r = requests.post(
            f"{GRAPH_API_URL}/{comment_id}/replies",
            data={"message": reply},
            headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
            timeout=10,
        )
        if r.ok:
            logger.info(f"💬 Comentario respondido: '{reply}'")
            return True
        logger.error(f"❌ Error al responder comentario ({r.status_code}): {r.text}")
    except Exception as e:
        logger.error(f"❌ Excepción al responder comentario: {e}")
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
        # Botón "Ya te sigo" tocado en el DM
        for event in entry.get("messaging", []):
            postback = event.get("postback", {})
            payload = postback.get("payload", "")
            sender_id = event.get("sender", {}).get("id")
            if payload.startswith(FOLLOW_PAYLOAD_PREFIX) and sender_id and sender_id != INSTAGRAM_ACCOUNT_ID:
                logger.info(f"🔘 Tocaron '{postback.get('title')}' ({payload})")
                handle_follow_check(sender_id, payload)

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
            cfg = find_campaign(text)
            if cfg:
                processed_comments.add(comment_id)
                logger.info("🎯 Keyword detectada, enviando DM...")
                if send_private_reply(comment_id, cfg):
                    reply_to_comment(comment_id)
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
