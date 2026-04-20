#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, CallbackContext
from pptx import Presentation

# ---------- الإعدادات ----------
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("الرجاء تعيين BOT_TOKEN كمتغير بيئة")

# إعداد التسجيل
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# قاموس مؤقت لحفظ ملفات المستخدمين
user_files = {}

# ---------- دوال معالجة PPTX ----------
def crop_pptx_from_bottom(file_bytes: bytes, crop_percent: int) -> BytesIO:
    """قص نسبة مئوية من أسفل الشرائح"""
    prs = Presentation(BytesIO(file_bytes))
    original_width = prs.slide_width
    original_height = prs.slide_height

    # حساب الارتفاع الجديد بعد القص
    new_height = int(original_height * (1 - crop_percent / 100.0))

    # تطبيق الأبعاد الجديدة
    prs.slide_width = original_width
    prs.slide_height = new_height

    # حفظ في الذاكرة
    output = BytesIO()
    prs.save(output)
    output.seek(0)
    return output

# ---------- أوامر البوت ----------
def start(update: Update, context: CallbackContext):
    """رسالة الترحيب"""
    update.message.reply_text(
        "🎬 أهلاً بك في بوت قص شرائح البوربوينت!\n\n"
        "📤 أرسل لي ملف PPTX لتبدأ.\n"
        "✂️ بعدها ستختار نسبة القص من الأسفل (1% - 80%)."
    )

def handle_document(update: Update, context: CallbackContext):
    """استقبال الملف من المستخدم"""
    user_id = update.effective_user.id
    document = update.message.document

    # التحقق من الامتداد
    if not document.file_name.lower().endswith(".pptx"):
        update.message.reply_text("❌ الملف يجب أن يكون بصيغة .pptx فقط.")
        return

    # تنزيل الملف
    file = context.bot.get_file(document.file_id)
    file_bytes = file.download_as_bytearray()
    user_files[user_id] = bytes(file_bytes)

    # إنشاء أزرار اختيار النسبة
    keyboard = [
        [
            InlineKeyboardButton("10%", callback_data="crop_10"),
            InlineKeyboardButton("20%", callback_data="crop_20"),
            InlineKeyboardButton("30%", callback_data="crop_30"),
        ],
        [
            InlineKeyboardButton("40%", callback_data="crop_40"),
            InlineKeyboardButton("50%", callback_data="crop_50"),
            InlineKeyboardButton("60%", callback_data="crop_60"),
        ],
        [
            InlineKeyboardButton("70%", callback_data="crop_70"),
            InlineKeyboardButton("80%", callback_data="crop_80"),
        ],
        [InlineKeyboardButton("✏️ إدخال نسبة يدوية", callback_data="manual_crop")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text(
        f"✅ تم استلام الملف: `{document.file_name}`\n\n"
        "🔽 اختر نسبة القص من الأسفل:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

def button_callback(update: Update, context: CallbackContext):
    """معالجة ضغطات الأزرار"""
    query = update.callback_query
    query.answer()
    user_id = update.effective_user.id
    data = query.data

    if user_id not in user_files:
        query.edit_message_text("⚠️ لم يتم العثور على ملف. أرسل ملف PPTX أولاً.")
        return

    if data == "manual_crop":
        query.edit_message_text(
            "📝 الرجاء إرسال النسبة المطلوبة (رقم بين 1 و 80) في رسالة نصية:"
        )
        context.user_data["awaiting_crop_value"] = True
        return

    # معالجة النسبة المحددة مسبقاً
    percent = int(data.split("_")[1])
    process_crop(update, context, user_id, percent, is_manual=False)

def handle_text(update: Update, context: CallbackContext):
    """استقبال النسبة اليدوية من المستخدم"""
    user_id = update.effective_user.id

    # التحقق مما إذا كنا في انتظار إدخال النسبة
    if not context.user_data.get("awaiting_crop_value"):
        return

    text = update.message.text.strip()
    try:
        percent = int(text)
        if percent < 1 or percent > 80:
            update.message.reply_text("❌ النسبة يجب أن تكون بين 1 و 80. حاول مجدداً:")
            return
    except ValueError:
        update.message.reply_text("❌ الرجاء إرسال رقم صحيح بين 1 و 80:")
        return

    # إلغاء حالة الانتظار
    context.user_data["awaiting_crop_value"] = False
    process_crop(update, context, user_id, percent, is_manual=True)

def process_crop(update: Update, context: CallbackContext, user_id: int, percent: int, is_manual: bool):
    """تنفيذ عملية القص وإرسال الملف الناتج"""
    file_bytes = user_files.get(user_id)
    if not file_bytes:
        if is_manual:
            update.message.reply_text("⚠️ انتهت صلاحية الملف. أرسل PPTX مجدداً.")
        else:
            update.callback_query.edit_message_text("⚠️ انتهت صلاحية الملف. أرسل PPTX مجدداً.")
        return

    # إعلام المستخدم ببدء المعالجة
    if is_manual:
        msg = update.message.reply_text("⏳ جاري معالجة الملف...")
    else:
        msg = update.callback_query.edit_message_text("⏳ جاري معالجة الملف...")

    try:
        # معالجة الملف
        output_stream = crop_pptx_from_bottom(file_bytes, percent)

        # إرسال الملف المعدل
        context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=output_stream,
            filename=f"cropped_{percent}percent.pptx",
            caption=f"✅ تم قص {percent}% من أسفل الشرائح بنجاح!"
        )
        msg.delete()
    except Exception as e:
        logger.error(f"خطأ أثناء معالجة الملف: {e}")
        error_text = f"❌ حدث خطأ أثناء المعالجة: {str(e)}"
        if is_manual:
            msg.edit_text(error_text)
        else:
            msg.edit_text(error_text)
    finally:
        # حذف الملف المؤقت
        user_files.pop(user_id, None)

def error_handler(update: Update, context: CallbackContext):
    """تسجيل الأخطاء"""
    logger.error(msg="استثناء غير معالج:", exc_info=context.error)

# ---------- الدالة الرئيسية ----------
def main():
    """تشغيل البوت"""
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # تسجيل المعالجات
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.document, handle_document))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
    dp.add_handler(CallbackQueryHandler(button_callback))
    dp.add_error_handler(error_handler)

    # بدء الاستماع
    logger.info("🤖 بوت قص البوربوينت يعمل الآن...")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
