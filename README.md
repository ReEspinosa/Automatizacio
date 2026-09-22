# Instagram Comment-to-DM Automation

Automatización que envía un mensaje directo (DM) automático cuando alguien comenta una palabra clave en tus Reels o publicaciones de Instagram. El DM incluye un botón que abre un documento PDF alojado en Google Drive.

Construido sobre la Instagram Graph API (Facebook Login) y Webhooks de Meta.

## Cómo funciona

1. Alguien comenta la palabra clave (por defecto `pisa`) en uno de tus posts.
2. Meta envía una notificación (webhook) al servidor.
3. El servidor detecta la palabra clave y responde ese comentario con un DM privado.
4. El DM contiene un botón que abre el PDF en Google Drive.

## Requisitos previos

- Una cuenta de Instagram profesional (Business o Creator).
- Una Página de Facebook vinculada a esa cuenta de Instagram.
- Una app de Meta creada en [developers.facebook.com](https://developers.facebook.com) con el caso de uso "Administrar mensajes y contenido en Instagram".
- Los permisos: `instagram_basic`, `instagram_manage_messages`, `instagram_manage_comments`, `pages_show_list`, `pages_read_engagement`.
- Un Page Access Token válido.

## Seguridad del token

El Page Access Token nunca se escribe dentro del código. Se define como variable de entorno (`PAGE_ACCESS_TOKEN`) en el servidor de despliegue. El archivo `app.py` lo lee con `os.getenv()`, por lo que el repositorio puede ser público sin exponer credenciales.

## Preparar el PDF en Google Drive

1. Sube el PDF a Google Drive.
2. Clic derecho sobre el archivo, luego Compartir, y cambia el acceso a "Cualquier persona con el enlace".
3. Copia el enlace. Tiene esta forma:

   ```
   https://drive.google.com/file/d/ID_DEL_ARCHIVO/view?usp=sharing
   ```

4. Toma el `ID_DEL_ARCHIVO` (la parte entre `/d/` y `/view`) y arma el enlace de descarga directa:

   ```
   https://drive.google.com/uc?export=download&id=ID_DEL_ARCHIVO
   ```

   Ese enlace es el que se usa en la variable de entorno `PDF_LINK`.

## Variables de entorno

| Variable | Descripción |
|----------|-------------|
| `PAGE_ACCESS_TOKEN` | Token de acceso de la Página de Facebook |
| `VERIFY_TOKEN` | Contraseña que defines tú para verificar el webhook con Meta |
| `INSTAGRAM_ACCOUNT_ID` | ID de la cuenta de Instagram Business |
| `PAGE_ID` | ID de la Página de Facebook |
| `KEYWORD` | Palabra clave que dispara el DM (por defecto `pisa`) |
| `PDF_LINK` | Enlace de descarga directa del PDF en Google Drive |
| `DM_MESSAGE` | Texto del mensaje del DM |
| `BUTTON_TEXT` | Texto del botón que abre el PDF |

## Instalación local

```bash
git clone https://github.com/USUARIO/REPO.git
cd REPO
pip install -r requirements.txt
```

Crea las variables de entorno y ejecuta:

```bash
python app.py
```

El servidor corre en `http://localhost:5000`.

## Despliegue en Render

1. Sube el proyecto a un repositorio de GitHub.
2. En [render.com](https://render.com), crea un Web Service conectado a ese repositorio.
3. Render detecta el archivo `render.yaml` automáticamente.
4. Agrega las variables de entorno de la tabla anterior.
5. Despliega. Render entrega una URL pública del tipo `https://tu-app.onrender.com`.

## Configurar el Webhook en Meta

1. En developers.facebook.com, entra a tu app y a la sección de Webhooks.
2. Callback URL: `https://tu-app.onrender.com/webhook`
3. Verify Token: el mismo valor que definiste en `VERIFY_TOKEN`.
4. Suscríbete al campo `comments`.

## Suscribir la cuenta a los eventos

```bash
curl -X POST "https://graph.facebook.com/v26.0/PAGE_ID/subscribed_apps?subscribed_fields=feed&access_token=PAGE_ACCESS_TOKEN"
```

## Endpoints

| Ruta | Método | Descripción |
|------|--------|-------------|
| `/` | GET | Verificación de estado del servidor |
| `/webhook` | GET | Verificación del webhook con Meta |
| `/webhook` | POST | Recepción de eventos de comentarios |

## Estructura del proyecto

```
.
├── app.py             # Servidor Flask con la lógica del webhook y el envío de DM
├── requirements.txt   # Dependencias de Python
├── render.yaml        # Configuración de despliegue en Render
└── README.md
```

## Limitaciones conocidas

- La API de Instagram no permite adjuntar archivos PDF directamente en un DM. Por eso se envía el enlace de Google Drive. Si el botón falla, el servidor manda el enlace como texto plano de forma automática.
- Meta permite enviar un solo DM privado por comentario, dentro de los 7 días posteriores a su publicación.
- El registro de comentarios ya procesados se guarda en memoria, por lo que se reinicia si el servidor se reinicia.

## Notas

- El Page Access Token generado desde el Graph API Explorer es de corta duración. Para producción, conviene generar un token de larga duración (aproximadamente 60 días).
- Mientras la app esté en modo de desarrollo, la automatización solo funciona con cuentas agregadas como probadores. Para que funcione con cualquier persona, la app debe pasar por la revisión de Meta (App Review).
