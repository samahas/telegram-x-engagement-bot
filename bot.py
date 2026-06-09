import sqlite3
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# توکن ربات تلگرام خود را اینجا بگذارید
TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"

# تابع راه‌اندازی دیتابیس
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # جدول کاربران و آیدی توییترشان
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            twitter_id TEXT,
            last_tweet_link TEXT
        )
    ''')
    
    # جدول بدهی‌ها و طلب‌های حمایتی
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
    print("دیتابیس با موفقیت راه‌اندازی شد.")

# دستور /start در تلگرام
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام! به ربات حمایت توییتر خوش آمدید. به زودی سیستم ثبت‌نام فعال می‌شود.")

def main():
    # ساخت دیتابیس
    init_db()
    
    # راه‌اندازی ربات تلگرام
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    
    print("ربات روشن شد...")
    application.run_polling()

if __name__ == '__main__':
    main()
