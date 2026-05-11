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
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID")

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
if not ADMIN_TELEGRAM_ID:
    raise ValueError("Falta ADMIN_TELEGRAM_ID en .env")

groq_client = Groq(api_key=GROQ_API_KEY)

SUPABASE_HEADERS = {
    "apikey": SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

def sb_url(table):
    return f"{SUPABASE_URL}/rest/v1/{table}"

def is_admin(user_id):
    return str(user_id) == str(ADMIN_TELEGRAM_ID)

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

    response = requests.post(
        sb_url("pp_users"),
        headers=SUPABASE_HEADERS,
        json=payload,
    )

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

    response = requests.post(
        sb_url("pp_messages"),
        headers=SUPABASE_HEADERS,
        json=payload,
    )

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
            formatted.append(
                {
                    "role": msg["role"],
                    "content": msg["content"],
                }
            )

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
Eres DeepTalk, una inteligencia emocional conversacional privada.

Tu función es ayudar al usuario a pensar con más claridad, ordenar emociones y confrontar lo que está evitando.

Tono:
- breve
- humano
- directo
- cálido
- inteligente
- mexicano natural
- nada místico
- nada poético
- nada de "oscuridad", "noche", "vacío" o frases fumadas
- máximo 2 párrafos
- máximo 1 pregunta al final

Estilo:
Más como alguien emocionalmente inteligente que escucha bien.
Menos como terapeuta formal.

Puedes ser un poco directivo cuando convenga:
- "vamos por partes"
- "eso sí duele"
- "ahí hay algo que no estás queriendo mirar"
- "no huyas de esa pregunta"
- "eso suena a que te sentiste usado"
- "creo que estás confundiendo costumbre con amor"
- "antes de actuar, separa lo que sientes de lo que realmente pasó"

No des diagnósticos clínicos.
No digas que eres terapeuta.
No prometas curar ansiedad, depresión o trauma.
No reemplazas ayuda profesional.

Seguridad:
- No sexualices menores.
- No participes en roleplay sexual con menores.
- No ayudes con violencia, autolesión, abuso o delitos.
- Si hay abuso, autolesión, suicidio, violencia o menores en contexto sexual, corta la escalada y recomienda buscar ayuda humana/profesional inmediata.
- No profundices en detalles sexuales con menores.

Privacidad:
Si preguntan por privacidad, di que las conversaciones pueden almacenarse para continuidad y funcionamiento del servicio. Recomienda no compartir datos extremadamente sensibles.
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_or_update_user(user)

    text = """
Bienvenido a DeepTalk.

Una interfaz privada de inteligencia emocional.

Puedes usarlo para:
• ordenar lo que sientes
• hablar sin sentirte juzgado
• pensar con más claridad
• confrontar lo que estás evitando
• entender patrones emocionales

Ejemplos:
“¿Por qué me cuesta soltar a alguien?”
“¿Cómo dejo de sobrepensar?”
“¿Estoy actuando desde el miedo?”
“¿Cómo pongo límites sin sentir culpa?”

DeepTalk no reemplaza ayuda profesional.

Escribe lo que traes en mente.
"""
    await update.message.reply_text(text)

async def premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = f"""
DeepTalk Plus

México: $99 MXN / mes
Internacional: $5 USD / mes

Incluye:

• Conversaciones extendidas
• Memoria emocional
• Continuidad entre sesiones
• Respuestas más profundas
• Acceso 24/7
• Análisis de patrones emocionales
• Reflexión sobre vínculos, personalidad y decisiones

Activa aquí:

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

Ahora envía aquí mismo la captura de tu pago.

Usuario:
{username_text}

ID interno:
{user.id}

Cuando verifiquemos tu pago, activaremos DeepTalk Plus.
"""
    await update.message.reply_text(text)

    await context.bot.send_message(
        chat_id=int(ADMIN_TELEGRAM_ID),
        text=f"""
Solicitud de pago recibida.

Usuario:
{username_text}

ID:
{user.id}

Espera captura de comprobante.
"""
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_or_update_user(user)

    username_text = f"@{user.username}" if user.username else "sin username"

    save_message(
        user.id,
        user.username,
        "user",
        "[PHOTO_SENT]"
    )

    await context.bot.send_message(
        chat_id=int(ADMIN_TELEGRAM_ID),
        text=f"""
Comprobante/foto recibido.

Usuario:
{username_text}

ID:
{user.id}
"""
    )

    await context.bot.forward_message(
        chat_id=int(ADMIN_TELEGRAM_ID),
        from_chat_id=update.message.chat_id,
        message_id=update.message.message_id,
    )

    await update.message.reply_text(
        "Recibido. Revisaremos tu comprobante y activaremos tu acceso manualmente."
    )

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("No autorizado.")
        return

    text = """
Panel Admin DeepTalk

Comandos:

/stats
Ver métricas generales

/users
Ver usuarios recientes

/hot
Ver usuarios con más uso

/activar TELEGRAM_ID
Activar premium

/desactivar TELEGRAM_ID
Quitar premium

/mensaje TELEGRAM_ID texto
Enviar mensaje manual a un usuario
"""
    await update.message.reply_text(text)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("No autorizado.")
        return

    users_res = requests.get(
        sb_url("pp_users"),
        headers=SUPABASE_HEADERS,
        params={"select": "*"},
    )

    messages_res = requests.get(
        sb_url("pp_messages"),
        headers=SUPABASE_HEADERS,
        params={"select": "*"},
    )

    users = users_res.json() if users_res.status_code < 400 else []
    messages = messages_res.json() if messages_res.status_code < 400 else []

    total_users = len(users)
    premium_users = len([u for u in users if u.get("is_premium")])
    active_users = len([u for u in users if int(u.get("free_messages_used") or 0) > 0])
    hot_users = len([u for u in users if int(u.get("free_messages_used") or 0) >= 5])
    total_messages = len(messages)

    text = f"""
DeepTalk Stats

Usuarios totales: {total_users}
Usuarios activos: {active_users}
Usuarios calientes 5+: {hot_users}
Premium: {premium_users}
Mensajes totales: {total_messages}
"""
    await update.message.reply_text(text)

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("No autorizado.")
        return

    res = requests.get(
        sb_url("pp_users"),
        headers=SUPABASE_HEADERS,
        params={
            "select": "telegram_id,username,first_name,is_premium,free_messages_used,created_at",
            "order": "created_at.desc",
            "limit": "15",
        },
    )

    if res.status_code >= 400:
        await update.message.reply_text("Error consultando usuarios.")
        return

    data = res.json()

    text = "Usuarios recientes:\n\n"

    for u in data:
        premium = "PLUS" if u.get("is_premium") else "FREE"
        username = f"@{u.get('username')}" if u.get("username") else "sin username"
        name = u.get("first_name") or "sin nombre"
        used = u.get("free_messages_used") or 0

        text += f"{premium} | {used} msgs\n{name} | {username}\nID: {u.get('telegram_id')}\n\n"

    await update.message.reply_text(text)

async def hot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("No autorizado.")
        return

    res = requests.get(
        sb_url("pp_users"),
        headers=SUPABASE_HEADERS,
        params={
            "select": "telegram_id,username,first_name,is_premium,free_messages_used,created_at",
            "order": "free_messages_used.desc",
            "limit": "15",
        },
    )

    if res.status_code >= 400:
        await update.message.reply_text("Error consultando usuarios.")
        return

    data = res.json()

    text = "Usuarios con más uso:\n\n"

    for u in data:
        premium = "PLUS" if u.get("is_premium") else "FREE"
        username = f"@{u.get('username')}" if u.get("username") else "sin username"
        name = u.get("first_name") or "sin nombre"
        used = u.get("free_messages_used") or 0

        text += f"{premium} | {used} msgs\n{name} | {username}\nID: {u.get('telegram_id')}\n\n"

    await update.message.reply_text(text)

async def activar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("No autorizado.")
        return

    if not context.args:
        await update.message.reply_text("Usa: /activar TELEGRAM_ID")
        return

    telegram_id = context.args[0]

    res = requests.patch(
        sb_url("pp_users"),
        headers=SUPABASE_HEADERS,
        params={"telegram_id": f"eq.{telegram_id}"},
        json={"is_premium": True},
    )

    if res.status_code >= 400:
        await update.message.reply_text("Error activando premium.")
        return

    await update.message.reply_text(f"Premium activado para {telegram_id}.")

    try:
        await context.bot.send_message(
            chat_id=int(telegram_id),
            text="DeepTalk Plus ha sido activado. Ya tienes acceso extendido."
        )
    except Exception as e:
        print("ERROR NOTIFY USER:", e)

async def desactivar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("No autorizado.")
        return

    if not context.args:
        await update.message.reply_text("Usa: /desactivar TELEGRAM_ID")
        return

    telegram_id = context.args[0]

    res = requests.patch(
        sb_url("pp_users"),
        headers=SUPABASE_HEADERS,
        params={"telegram_id": f"eq.{telegram_id}"},
        json={"is_premium": False},
    )

    if res.status_code >= 400:
        await update.message.reply_text("Error desactivando premium.")
        return

    await update.message.reply_text(f"Premium desactivado para {telegram_id}.")

async def mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("No autorizado.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usa: /mensaje TELEGRAM_ID texto")
        return

    telegram_id = context.args[0]
    text = " ".join(context.args[1:])

    try:
        await context.bot.send_message(
            chat_id=int(telegram_id),
            text=text
        )
        await update.message.reply_text(f"Mensaje enviado a {telegram_id}.")
    except Exception as e:
        print("ERROR SEND MESSAGE:", e)
        await update.message.reply_text("No se pudo enviar el mensaje.")

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
            model="llama3-70b-8192",
            messages=messages,
            temperature=0.32,
            max_tokens=360,
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

app.add_handler(CommandHandler("admin", admin))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CommandHandler("users", users))
app.add_handler(CommandHandler("hot", hot))
app.add_handler(CommandHandler("activar", activar))
app.add_handler(CommandHandler("desactivar", desactivar))
app.add_handler(CommandHandler("mensaje", mensaje))

app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("DeepTalk ADMIN VERSION está corriendo...")

app.run_polling()
