import os
import requests
import mercadopago

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
FREE_MESSAGE_LIMIT = int(os.getenv("FREE_MESSAGE_LIMIT", "20"))
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID")
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")

if not BOT_TOKEN:
    raise ValueError("Falta BOT_TOKEN")

if not GROQ_API_KEY:
    raise ValueError("Falta GROQ_API_KEY")

if not SUPABASE_URL:
    raise ValueError("Falta SUPABASE_URL")

if not SUPABASE_SERVICE_ROLE_KEY:
    raise ValueError("Falta SUPABASE_SERVICE_ROLE_KEY")

if not ADMIN_TELEGRAM_ID:
    raise ValueError("Falta ADMIN_TELEGRAM_ID")

if not MP_ACCESS_TOKEN:
    raise ValueError("Falta MP_ACCESS_TOKEN")

groq_client = Groq(api_key=GROQ_API_KEY)

sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

SUPABASE_HEADERS = {
    "apikey": SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

SYSTEM_PROMPT = """
You are DeepTalk.

A private conversational AI designed for emotional clarity, reflection and psychologically intelligent conversation.

Your purpose is to help users:
- process emotions
- think more clearly
- organize thoughts
- reflect calmly
- feel heard without judgment
- understand emotional patterns
- reduce mental chaos

Tone:
- human
- calm
- emotionally intelligent
- conversational
- concise
- warm
- natural
- direct when necessary

DeepTalk should feel:
- psychologically insightful
- emotionally engaging
- reflective
- intelligent
- modern

Do NOT:
- pretend to be a licensed therapist
- diagnose mental disorders
- promise healing
- encourage self-harm
- encourage violence
- encourage illegal activity
- sexualize minors
- participate in sexual roleplay involving minors

If the conversation includes:
- suicide
- self-harm
- abuse
- minors
- sexual situations involving minors
- violence

then:
- stay calm
- avoid escalation
- encourage seeking real human/professional help when necessary
- never continue inappropriate sexual content

Privacy:
If asked about privacy, explain clearly:
- conversations may be stored for continuity and service functionality
- users should avoid sharing extremely sensitive personal information

Response style:
- most replies should be SHORT
- usually under 120 words
- maximum 2 short paragraphs
- ask at most ONE question
- sometimes simply reflect back insightfully
- sometimes challenge the user's thinking gently
- sometimes be direct

DeepTalk is not therapy.
DeepTalk helps people think more clearly.
"""

def sb_url(table):
    return f"{SUPABASE_URL}/rest/v1/{table}"

def is_admin(user_id):
    return str(user_id) == str(ADMIN_TELEGRAM_ID)

def supabase_get_user(telegram_id):

    response = requests.get(
        sb_url("pp_users"),
        headers=SUPABASE_HEADERS,
        params={
            "telegram_id": f"eq.{telegram_id}",
            "select": "*"
        },
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
        "language": "en"
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
        params={
            "telegram_id": f"eq.{user.id}"
        },
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

            formatted.append({
                "role": msg["role"],
                "content": msg["content"],
            })

    return formatted

def increment_free_messages(telegram_id):

    user = supabase_get_user(str(telegram_id))

    if not user:
        return 0

    used = int(user.get("free_messages_used") or 0) + 1

    response = requests.patch(
        sb_url("pp_users"),
        headers=SUPABASE_HEADERS,
        params={
            "telegram_id": f"eq.{telegram_id}"
        },
        json={
            "free_messages_used": used
        },
    )

    if response.status_code >= 400:
        print("ERROR INCREMENT:", response.text)

    return used

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    create_or_update_user(user)

    text = """
Welcome to DeepTalk.

A private AI space to think more clearly, vent, and understand yourself better.

You can talk about:
• overthinking
• relationships
• anxiety
• loneliness
• attachment
• emotional confusion
• difficult decisions
• habits
• motivation

Select your language:

🇺🇸 English → type EN
🇲🇽 Español → escribe ES

Example:
“Why do I overthink everything?”
“Why can’t I let this person go?”
“Me siento perdido.”
“No puedo dejar de pensar.”
"""

    await update.message.reply_text(text)


async def premium(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    preference_data = {
        "items": [
            {
                "title": "DeepTalk Plus",
                "quantity": 1,
                "currency_id": "USD",
                "unit_price": 4.99
            }
        ],
        "external_reference": str(user.id)
    }

    preference_response = sdk.preference().create(preference_data)

    payment_link = preference_response["response"]["init_point"]

    text = f"""
DeepTalk Plus

Private emotional AI access.

Includes:
• unlimited conversations
• emotional memory
• continuity between sessions
• deeper reflection
• emotionally intelligent responses
• 24/7 access

Monthly access:
$4.99 USD

Activate here:

{payment_link}
"""

    await update.message.reply_text(text)

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = """
Commands:

/start
/premium
/ayuda
"""

    await update.message.reply_text(text)

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("No autorizado.")
        return

    text = """
Panel Admin DeepTalk

/stats
/activar TELEGRAM_ID
/desactivar TELEGRAM_ID
"""

    await update.message.reply_text(text)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
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
    total_messages = len(messages)

    text = f"""
DeepTalk Stats

Users: {total_users}
Premium: {premium_users}
Messages: {total_messages}
"""

    await update.message.reply_text(text)

async def activar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("Usa /activar TELEGRAM_ID")
        return

    telegram_id = context.args[0]

    requests.patch(
        sb_url("pp_users"),
        headers=SUPABASE_HEADERS,
        params={
            "telegram_id": f"eq.{telegram_id}"
        },
        json={
            "is_premium": True
        },
    )

    await update.message.reply_text(f"Premium activado: {telegram_id}")

async def desactivar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("Usa /desactivar TELEGRAM_ID")
        return

    telegram_id = context.args[0]

    requests.patch(
        sb_url("pp_users"),
        headers=SUPABASE_HEADERS,
        params={
            "telegram_id": f"eq.{telegram_id}"
        },
        json={
            "is_premium": False
        },
    )

    await update.message.reply_text(f"Premium desactivado: {telegram_id}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    telegram_id = str(user.id)

    username = user.username

    user_message = update.message.text

    create_or_update_user(user)

    normalized = user_message.upper().strip()

    if normalized == "EN":

        requests.patch(
            sb_url("pp_users"),
            headers=SUPABASE_HEADERS,
            params={
                "telegram_id": f"eq.{telegram_id}"
            },
            json={
                "language": "en"
            },
        )

        requests.delete(
            sb_url("pp_messages"),
            headers=SUPABASE_HEADERS,
            params={
                "telegram_id": f"eq.{telegram_id}"
            },
        )

        await update.message.reply_text(
"""
Language set to English.

You can now start talking naturally.
"""
        )

        return

    if normalized == "ES":

        requests.patch(
            sb_url("pp_users"),
            headers=SUPABASE_HEADERS,
            params={
                "telegram_id": f"eq.{telegram_id}"
            },
            json={
                "language": "es"
            },
        )

        requests.delete(
            sb_url("pp_messages"),
            headers=SUPABASE_HEADERS,
            params={
                "telegram_id": f"eq.{telegram_id}"
            },
        )

        await update.message.reply_text(
"""
Idioma cambiado a español.

Ya puedes hablar normalmente.
"""
        )

        return

    db_user = supabase_get_user(telegram_id)

    if not db_user:
        await update.message.reply_text("Error creating user.")
        return

    language = db_user.get("language", "en")

    is_premium = bool(db_user.get("is_premium", False))

    free_used = int(db_user.get("free_messages_used") or 0)

    if not is_premium and free_used >= FREE_MESSAGE_LIMIT:

        await update.message.reply_text(
"""
You reached the free limit.

Upgrade to DeepTalk Plus:

/premium
"""
        )

        return

    save_message(
        telegram_id,
        username,
        "user",
        user_message
    )

    try:

        recent_messages = get_recent_messages(telegram_id)

        language_instruction = ""

        if language == "es":
            language_instruction = "Respond ONLY in Spanish."

        if language == "en":
            language_instruction = "Respond ONLY in English."

        messages = [{
            "role": "system",
            "content": SYSTEM_PROMPT + "\n" + language_instruction
        }]

        messages.extend(recent_messages)

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.45,
            max_tokens=220,
        )

        reply = response.choices[0].message.content

        save_message(
            telegram_id,
            username,
            "assistant",
            reply
        )

        if not is_premium:
            increment_free_messages(telegram_id)

        await update.message.reply_text(reply)

    except Exception as e:

        print("ERROR IA:", e)

        await update.message.reply_text(
            "There was a problem processing your message."
        )

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("premium", premium))
app.add_handler(CommandHandler("ayuda", ayuda))
app.add_handler(CommandHandler("admin", admin))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CommandHandler("activar", activar))
app.add_handler(CommandHandler("desactivar", desactivar))

app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    )
)

print("DeepTalk GLOBAL VERSION running...")

app.run_polling()
