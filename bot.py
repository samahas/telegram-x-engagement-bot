import sqlite3
import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# فعال‌سازی سیستم لاگ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# 🔴 توکن اختصاصی خودت را این‌جا بگذار
TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"

# تنظیمات پروکسی برای عبور از فیلترینگ ایران
PROXY_URL = "http://127.0.0.1:10809" 

def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            twitter_id TEXT,
            last_tweet_link TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS debts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            debtor_id INTEGER,
            creditor_id INTEGER,
            action_type TEXT,
            status TEXT DEFAULT 'pending'
        )
    ''')
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"سلام {user.first_name} عزیز! به ربات Xengage خوش آمدی.\n\n"
        "برای اینکه بتوانی در گروه حمایت شرکت کنی، باید آیدی توییتر خودت را ثبت کنی.\n"
        "لطفاً آیدی توییترت را بدون @ ارسال کن."
    )
    await update.message.reply_text(welcome_text)

async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفاً آیدی توییتر (X) خودت را بدون علامت @ ارسال کن:")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id
    telegram_username = update.effective_user.username
    chat_type = update.effective_chat.type

    # ۱. پردازش پیام‌ها در گروه (شکار لینک‌ها)
    if chat_type in ["group", "supergroup"]:
        if "twitter.com" in text.lower() or "x.com" in text.lower():
            url_match = re.search(r'(https?://[^\s]+)', text)
            if not url_match:
                return
            tweet_link = url_match.group(0)

            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute('SELECT twitter_id FROM users WHERE user_id = ?', (user_id,))
            user_data = cursor.fetchone()

            if not user_data:
                await update.message.delete()
                warning_msg = await update.message.reply_text(f"❌ کاربر @{telegram_username}، شما ابتدا باید در پی‌وی ربات (@XengageRobot) ثبت‌نام کنید!")
                context.job_queue.run_once(lambda ctx: warning_msg.delete(), 10)
                conn.close()
                return

            twitter_handle = user_data[0]
            cursor.execute('UPDATE users SET last_tweet_link = ? WHERE user_id = ?', (tweet_link, user_id))
            conn.commit()
            conn.close()

            await update.message.delete()

            # دکمه‌ها همراه با فالو
            keyboard = [
                [
                    InlineKeyboardButton("👥 Followed", callback_data=f"follow_{user_id}"),
                    InlineKeyboardButton("❤️ Liked", callback_data=f"like_{user_id}"),
                    InlineKeyboardButton("🔁 Retweeted", callback_data=f"rt_{user_id}"),
                    InlineKeyboardButton("💬 Commented", callback_data=f"comment_{user_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            group_post_text = (
                f"🚀 **New Support Request!**\n\n"
                f"👤 **User:** @{telegram_username}\n"
                f"🐦 **X (Twitter):** @{twitter_handle}\n\n"
                f"🔗 **Link:** {tweet_link}\n\n"
                f"👇 Please support and click the buttons below:"
            )
            await context.bot.send_message(chat_id=update.effective_chat.id, text=group_post_text, reply_markup=reply_markup, parse_mode="Markdown")
            return

    # ۲. پردازش ثبت‌نام در پی‌وی (PV)
    if chat_type == "private":
        twitter_id = text[1:] if text.startswith('@') else text

        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (user_id, username, twitter_id)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET twitter_id = excluded.twitter_id, username = excluded.username
        ''', (user_id, telegram_username, twitter_id))
        conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ موفقیت‌آمیز بود!\nآیدی توییتر شما با موفقیت ثبت شد: @{twitter_id}")

# پردازش کلیک روی دکمه‌ها
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() # حذف حالت در حال لود دکمه
    
    clicker_id = query.from_user.id
    clicker_username = query.from_user.username
    
    # استخراج اطلاعات از callback_data (مثال: follow_123456)
    data_parts = query.data.split('_')
    action = data_parts[0]
    creator_id = int(data_parts[1])

    # اگر کاربر خواست دکمه پست خودش را بزند، ربات مچش را می‌گیرد!
    if clicker_id == creator_id:
        return

    # بررسی اینکه آیا فرد حمایت‌کننده خودش ثبت‌نام کرده یا نه
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT twitter_id, last_tweet_link FROM users WHERE user_id = ?', (clicker_id,))
    clicker_data = cursor.fetchone()

    if not clicker_data:
        # اگر ثبت نام نکرده بود، پی‌ام موقت به او نشان بده
        return

    clicker_twitter = clicker_data[0]
    clicker_last_link = clicker_data[1] if clicker_data[1] else "لینکی ثبت نشده است"

    # ثبت در جدول بدهی‌ها (پست‌گذار حالا به حمایت‌کننده بدهکار است)
    cursor.execute('''
        INSERT INTO debts (debtor_id, creditor_id, action_type)
        VALUES (?, ?, ?)
    ''', (creator_id, clicker_id, action))
    conn.commit()
    conn.close()

    # ترجمه اکشن به متن فارسی برای ارسال به پی‌وی
    action_fa = {"follow": "فالو", "like": "لایک", "rt": "ریتوییت", "comment": "کامنت"}[action]

    # ارسال پیام خصوصی به صاحب پست (Creator)
    alert_text = (
        f"📣 **حمایت جدید دریافت شد!**\n\n"
        f"👤 کاربر @{clicker_username} (آیدی توییتر: @{clicker_twitter}) پست شما را **{action_fa}** کرد.\n\n"
        f"تعهد شما: حالا نوبت شماست که او را حمایت کنید!\n"
        f"🔗 آخرین لینک این کاربر: {clicker_last_link}"
    )
    
    try:
        await context.bot.send_message(chat_id=creator_id, text=alert_text, parse_mode="Markdown")
    except Exception as e:
        # اگر صاحب پست ربات را بلاک کرده باشد یا استارت نزده باشد
        logging.error(f"Could not send PV message to {creator_id}: {e}")

def main():
    init_db()
    
    application = (
        Application.builder()
        .token(TOKEN)
        .proxy(PROXY_URL)
        .get_updates_proxy(PROXY_URL)
        .build()
    )
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_buttons)) # هندلر دکمه‌ها
    
    print("ربات Xengage روشن شد و منتظر پیام‌هاست...")
    application.run_polling()

if __name__ == '__main__':
    main()
