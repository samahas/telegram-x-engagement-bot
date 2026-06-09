import sqlite3
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# فعال‌سازی سیستم لاگ برای دیدن ارورهای احتمالی
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# 🔴 توکن اختصاصی خودت را این‌جا بگذار
TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"

# راه‌اندازی دیتابیس
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

# دستور /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"سلام {user.first_name} عزیز! به ربات Xengage خوش آمدی.\n\n"
        "برای اینکه بتوانی در گروه حمایت شرکت کنی، باید آیدی توییتر خودت را ثبت کنی.\n"
        "لطفاً دستور /register را بفرست یا بنویس ابتدا آیدی توییترت چیست."
    )
    await update.message.reply_text(welcome_text)

# دستور ثبت‌نام /register
async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لطفاً آیدی توییتر (X) خودت را بدون علامت @ ارسال کن:")

# پردازش پیام‌های متنی (برای گرفتن آیدی توییتر)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id
    telegram_username = update.effective_user.username

    # تمیز کردن آیدی توییتر در صورتی که کاربر با @ فرستاده باشد
    if text.startswith('@'):
        twitter_id = text[1:]
    else:
        twitter_id = text

    # ذخیره در دیتابیس
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # درج یا آپدیت اطلاعات کاربر
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
    
    application = Application.builder().token(TOKEN).build()
    
    # هندلرها (دستورات)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register_command))
    
    # هندلر پیام‌های متنی عادی (برای ثبت آیدی)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("ربات Xengage روشن شد و منتظر پیام‌هاست...")
    application.run_polling()

if __name__ == '__main__':
    main()
