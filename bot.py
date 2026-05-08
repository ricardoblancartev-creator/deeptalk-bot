import os
import requests
from dotenv import load_dotenv
from groq import Groq
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
PAYMENT_LINK = os.getenv("PAYMENT_LINK")
FREE_MESSAGE_LIMIT = int(os.getenv("FREE_MESSAGE_LIMIT", "20"))

if not BOT_TOKEN:
    raise ValueError("Falta BOT_TOKEN en .env")
if not GROQ_API_KEY:
    raise ValueError("Falta GROQ_API_KEY en .env")
if not SUPABASE_URL:
    raise ValueError("Falta SUPABASE_URL en .env")
if not SUPABASE_SERVICE_ROLE_KEY:
    raise ValueError("Falta SUPABASE_SERVICE_ROLE_KEY en .env")
if not PAYMENT_LINK:
    raise ValueError("Falta PAYMENT_LINK en .env")

groq_client = Groq(api_key=GROQ_API_KEY)

SUPABASE_HEADERS = {
    "apikey": SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

def sb_url(table):
    return f"{SUPABASE_URL}/rest/v1/{table}"

def supabase_get_user(telegram_id):
    response = requests.get(
        sb_url("pp_users"),
        headers=SUPABASE_HEADERS,
        params={"telegram_id": f"eq.{telegram_id}", "select": "*"},
    )
    if response.status_code >= 400:
        print("ERROR GET USER:", response.text)
        return None
    data = response.json()
    return data[0] if data else None

def supabase_insert_user(user):
    payload = {
        "telegram_id": str(user.id),
        "username": user.username,
        "first_name": user.first_name,
        "is_premium": False,
        "free_messages_used": 0,
    }
    response = requests.post(sb_url("pp_users"), headers=SUPABASE_HEADERS, json=payload)
    if response.status_code >= 400:
        print("ERROR INSERT USER:", response.text)

def supabase_update_user(user):
    payload = {
        "username": user.username,
        "first_name": user.first_name,
    }
    response = requests.patch(
        sb_url("pp_users"),
        headers=SUPABASE_HEADERS,
        params={"telegram_id": f"eq.{user.id}"},
        json=payload,
    )
    if response.status_code >= 400:
        print("ERROR UPDATE USER:", response.text)

def create_or_update_user(user):
    existing = supabase_get_user(str(user.id))
    if existing:
        supabase_update_user(user)
    else:
        supabase_insert_user(user)

def save_message(telegram_id, username, role, content):
    payload = {
        "telegram_id": str(telegram_id),
        "username": username,
        "role": role,
        "content": content,
    }
    response = requests.post(sb_url("pp_messages"), headers=SUPABASE_HEADERS, json=payload)
    if response.status_code >= 400:
        print("ERROR SAVE MESSAGE:", response.text)

def get_recent_messages(telegram_id, limit=10):
    response = requests.get(
        sb_url("pp_messages"),
        headers=SUPABASE_HEADERS,
        params={
            "telegram_id": f"eq.{telegram_id}",
            "select": "role,content,created_at",
            "order": "created_at.desc",
            "limit": str(limit),
        },
    )
    if response.status_code >= 400:
        print("ERROR GET MESSAGES:", response.text)
        return []

    data = response.json()
    data.reverse()

    formatted = []
    for msg in data:
        if msg.get("role") in ["user", "assistant"]:
            formatted.append({"role": msg["role"], "content": msg["content"]})
    return formatted

def increment_free_messages(telegram_id):
    user = supabase_get_user(str(telegram_id))
    if not user:
        return 0

    used = int(user.get("free_messages_used") or 0) + 1

    response = requests.patch(
        sb_url("pp_users"),
        headers=SUPABASE_HEADERS,
        params={"telegram_id": f"eq.{telegram_id}"},
        json={"free_messages_used": used},
    )
    if response.status_code >= 400:
        print("ERROR INCREMENT:", response.text)

    return used

SYSTEM_PROMPT = """
Eres DeepTalk, una IA privada de inteligencia emocional.

Tu función es escuchar, ordenar ideas y ayudar al usuario a pensar con claridad emocional.

No eres terapeuta.
No das diagnósticos clínicos.
No prometes curar ansiedad, depresión, trauma ni conflictos personales.
No sustituyes ayuda psicológica profesional.

Estilo:
- Inteligente, sobrio, cálido y directo.
- Español mexicano natural.
- Premium, claro, elegante, no cursi.
- Nada de poesía fumada.
- Nada de misticismo.
- Nada de frases dramáticas.
- Máximo 2 párrafos por respuesta.
- Máximo 1 pregunta al final.
- Si el usuario solo saluda, responde breve y sugiere temas concretos.

Puedes ayudar con:
- ordenar pensamientos
- inteligencia emocional
- conflictos de pareja
- comunicación asertiva
- límites personales
- autoestima
- toma de decisiones
- manejo de enojo
- estrés
- análisis de patrones emocionales
- reflexión sobre personalidad sin diagnosticar

Cuando el usuario pida personalidad, aclara que no es diagnóstico y ofrece una lectura orientativa basada en lo que cuente.

Si detectas riesgo de autolesión o daño a otros, recomienda buscar ayuda inmediata con emergencias o una persona de confianza.
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_or_update_user(user)

    text = """
Bienvenido a DeepTalk.

Una interfaz privada de inteligencia emocional.

Puedes usarlo para pensar con más claridad, desahogarte o entender mejor lo que estás sintiendo.

Algunas cosas que puedes tratar aquí:

• Tengo un desacuerdo con mi pareja
• Quiero comunicarme de forma más asertiva
• Me cuesta poner límites
• Quiero entender qué tipo de personalidad tengo
• Estoy estresado y quiero ordenar mis ideas
• Quiero tomar una decisión sin actuar desde el impulso

Escribe lo que traes en mente.
"""
    await update.message.reply_text(text)

async def premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = f"""
DeepTalk Plus

Acceso privado mensual: $99 MXN

Incluye:

• Conversaciones extendidas
• Memoria emocional
• Continuidad entre sesiones
• Respuestas más profundas
• Acompañamiento 24/7
• Análisis de patrones emocionales
• Reflexión sobre vínculos, personalidad y decisiones

Activa tu acceso aquí:

{PAYMENT_LINK}

Después de pagar escribe:

PAGADO
"""
    await update.message.reply_text(text)

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
Comandos:

/start - Iniciar
/premium - Activar Plus
/ayuda - Ver ayuda

También puedes escribir directamente lo que quieres trabajar.
"""
    await update.message.reply_text(text)

async def pagado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_or_update_user(user)

    username_text = f"@{user.username}" if user.username else "sin username"

    text = f"""
Perfecto.

Envíame captura de tu pago aquí mismo.

Usuario:
{username_text}

ID interno:
{user.id}

Tu acceso será activado después de verificar el pago.
"""
    await update.message.reply_text(text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    telegram_id = str(user.id)
    username = user.username
    user_message = update.message.text

    create_or_update_user(user)

    normalized = user_message.upper().strip()

    if normalized == "PAGADO":
        await pagado(update, context)
        return

    db_user = supabase_get_user(telegram_id)

    if not db_user:
        await update.message.reply_text("Hubo un problema creando tu usuario.")
        return

    is_premium = bool(db_user.get("is_premium", False))
    free_used = int(db_user.get("free_messages_used") or 0)

    if not is_premium and free_used >= FREE_MESSAGE_LIMIT:
        await update.message.reply_text(
            f"""
Has llegado al límite de la versión inicial de DeepTalk.

Para continuar con DeepTalk Plus:

{PAYMENT_LINK}

Después de pagar escribe:

PAGADO
"""
        )
        return

    save_message(telegram_id, username, "user", user_message)

    try:
        recent_messages = get_recent_messages(telegram_id)

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(recent_messages)

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.35,
            max_tokens=420,
        )

        reply = response.choices[0].message.content

        save_message(telegram_id, username, "assistant", reply)

        if not is_premium:
            increment_free_messages(telegram_id)

        await update.message.reply_text(reply)

    except Exception as e:
        print("ERROR IA:", e)
        await update.message.reply_text("Hubo un problema procesando tu mensaje.")

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("premium", premium))
app.add_handler(CommandHandler("ayuda", ayuda))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("DeepTalk está corriendo...")

app.run_polling()
