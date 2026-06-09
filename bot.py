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
        "لطفاً دستور /register را بفرست یا آیدی توییترت را بدون @ ارسال کن."
    )
    await update.message.reply_text(welcome_text)

async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفاً آیدی توییتر (X) خودت را بدون علامت @ ارسال کن:")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id
    telegram_username = update.effective_user.username
    chat_type = update.effective_chat.type

    # ۱. اگر پیام در گروه فرستاده شده و حاوی لینک توییتر است
    if chat_type in ["group", "supergroup"]:
        if "twitter.com" in text.lower() or "x.com" in text.lower():
            # استخراج لینک توییتر با استفاده از Regex
            url_match = re.search(r'(https?://[^\s]+)', text)
            if not url_match:
                return
            tweet_link = url_match.group(0)

            # چک کردن اینکه کاربر ثبت نام کرده یا نه
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute('SELECT twitter_id FROM users WHERE user_id = ?', (user_id,))
            user_data = cursor.fetchone()

            if not user_data:
                # کاربر ثبت نام نکرده -> پاک کردن پیام و اخطار
                await update.message.delete()
                warning_msg = await update.message.reply_text(f"❌ کاربر @{telegram_username}، شما ابتدا باید در پی‌وی ربات (@XengageRobot) ثبت‌نام کنید!")
                # حذف خودکار پیام اخطار بعد از ۱۰ ثانیه برای خلوت ماندن گروه
                context.job_queue.run_once(lambda ctx: warning_msg.delete(), 10)
                conn.close()
                return

            twitter_handle = user_data[0]
            
            # بروزرسانی آخرین لینک کاربر در دیتابیس
            cursor.execute('UPDATE users SET last_tweet_link = ? WHERE user_id = ?', (tweet_link, user_id))
            conn.commit()
            conn.close()

            # پاک کردن پیام اصلی کاربر برای ارسال پیام شکیل ربات
            await update.message.delete()

            # ساخت دکمه‌های شیشه‌ای حمایتی
            keyboard = [
                [
                    InlineKeyboardButton("❤️ Likeed", callback_data=f"like_{user_id}"),
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

    # ۲. اگر پیام در چت خصوصی (PV) فرستاده شده (برای ثبت نام)
    if chat_type == "private":
        if text.startswith('@'):
            twitter_id = text[1:]
        else:
            twitter_id = text

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
    
    print("ربات Xengage روشن شد و منتظر پیام‌هاست...")
    application.run_polling()

if __name__ == '__main__':
    main()
