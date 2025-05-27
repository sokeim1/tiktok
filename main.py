import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
import yt_dlp
import os
import subprocess
import time
import math
import json
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, BigInteger, String, DateTime

TOKEN = "7699986600:AAELF29njMFijCV-uUIBGYLIaaIV7N4_XNg"
API_URL = "http://localhost:8081"  # URL локального сервера

FFMPEG_PATH = r"D:\я\ffmpeg-7.1.1-essentials_build\bin\ffmpeg.exe"
FFPROBE_PATH = r"D:\я\ffmpeg-7.1.1-essentials_build\bin\ffprobe.exe"
CHANNEL_ID = -1002546049004  # ID вашего канала
CHANNEL_USERNAME = "funny_dynasty"  # без @

DATABASE_URL = "postgresql+asyncpg://postgres:PYXyhYpTHvwuXEOYvHbTjIfNySkDHhYs@ballast.proxy.rlwy.net:55888/railway"
engine = create_async_engine(DATABASE_URL, echo=False)
Base = declarative_base()
SessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class User(Base):
    __tablename__ = "users"
    user_id = Column(BigInteger, primary_key=True)
    platform = Column(String(32), default=None)
    registered_at = Column(DateTime, default=datetime.datetime.utcnow)

bot = Bot(TOKEN, api_url=API_URL)  # Используем локальный сервер
dp = Dispatcher()

# Сохраняем состояние выбора платформы для пользователя
user_quality = {}

PROXY_URL = 'http://167.99.124.118:80'

WELCOME_TEXT = (
    "<b>🎬 Добро пожаловать в Video Downloader Бот!</b>\n\n"
    "Выберите платформу, с которой хотите скачать видео:\n\n"
    "<i>Поддерживаются TikTok и Instagram. Просто выберите платформу и отправьте ссылку на видео.</i>"
)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 МБ

async def check_subscription(user_id):
    try:
        member = await bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        print(f"SUB CHECK ERROR: {e}")
        return False

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    is_sub = await check_subscription(message.from_user.id)
    if is_sub:
        builder = InlineKeyboardBuilder()
        builder.button(text="🎵 TikTok", callback_data="platform_tiktok")
        builder.button(text="📸 Instagram", callback_data="platform_instagram")
        builder.adjust(2)
        await message.answer(WELCOME_TEXT, reply_markup=builder.as_markup(), parse_mode="HTML")
        return
    # Если не подписан — отправляем красивое сообщение
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME}")],
            [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")],
        ]
    )
    await message.answer(
        "<b>🚫 Доступ ограничен!</b>\n\n"
        "Чтобы пользоваться ботом, подпишитесь на наш канал:\n"
        f"<a href='https://t.me/{CHANNEL_USERNAME}'>@{CHANNEL_USERNAME}</a>\n\n"
        "После подписки нажмите <b>Проверить подписку</b>!",
        reply_markup=kb,
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("platform_"))
async def choose_platform(callback: types.CallbackQuery):
    platform = callback.data.replace("platform_", "")
    await set_user_platform(callback.from_user.id, platform)
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад", callback_data="back_to_menu")
    if platform == "tiktok":
        await callback.message.edit_text(
            "<b>🎵 TikTok</b>\n\n<i>Пришлите ссылку на TikTok-видео, и я скачаю его для вас в максимальном качестве!</i>",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    else:
        await callback.message.edit_text(
            "<b>📸 Instagram</b>\n\n<i>Пришлите ссылку на Instagram-видео, и я скачаю его для вас в максимальном качестве!</i>",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )

@dp.message()
async def download_video(message: types.Message):
    print(f"download_video: user_id={message.from_user.id}, text={message.text}, platform={await get_user_platform(message.from_user.id)}")
    platform = await get_user_platform(message.from_user.id)
    url = message.text.strip()
    if not platform:
        await start_cmd(message)
        return
    if platform == "tiktok":
        if not url.startswith("http") or "tiktok.com" not in url:
            await message.answer("Пожалуйста, отправьте корректную ссылку на TikTok-видео.")
            return
    elif platform == "instagram":
        if not url.startswith("http") or "instagram.com" not in url:
            await message.answer("Пожалуйста, отправьте корректную ссылку на Instagram-видео.")
            return
    else:
        await message.answer("Неизвестная платформа. Пожалуйста, выберите снова.")
        await start_cmd(message)
        return
    # Сохраняем ссылку по user_id
    user_quality[message.from_user.id] = url
    builder = InlineKeyboardBuilder()
    builder.button(text="Нормальное", callback_data="quality_normal")
    builder.button(text="Очень хорошее", callback_data="quality_best")
    builder.adjust(2)
    await message.answer("<b>Выберите качество видео:</b>", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("quality_"))
async def choose_quality(callback: types.CallbackQuery):
    quality = callback.data.replace("quality_", "")
    url = user_quality.get(callback.from_user.id)
    user_quality[callback.from_user.id] = quality
    platform = await get_user_platform(callback.from_user.id)
    await callback.message.delete()
    await process_download(callback.message, platform, url, quality)

async def process_download(message, platform, url, quality):
    progress_message = await message.answer("<b>⬇️ Скачивание:</b> <b>0%</b>\n⬜️⬜️⬜️⬜️⬜️⬜️⬜️⬜️⬜️⬜️", parse_mode="HTML")
    if platform == "tiktok" or platform == "instagram":
        ydl_format = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
    else:
        ydl_format = 'best'
    def progress_hook_factory(progress_message):
        last_percent = {'value': -1}
        async def update_progress(percent):
            bar_count = int(percent // 10)
            bar = '🟩' * bar_count + '⬜️' * (10 - bar_count)
            text = f"<b>⬇️ Скачивание:</b> <b>{percent:.0f}%</b>\n{bar}"
            try:
                await progress_message.edit_text(text, parse_mode='HTML')
            except Exception:
                pass
        async def finish_progress():
            for percent in range(last_percent['value']+1, 101, 20):
                bar_count = int(percent // 10)
                bar = '🟩' * bar_count + '⬜️' * (10 - bar_count)
                text = f"<b>⬇️ Скачивание:</b> <b>{percent}%</b>\n{bar}"
                try:
                    await progress_message.edit_text(text, parse_mode='HTML')
                except Exception:
                    pass
                await asyncio.sleep(0.1)
            try:
                await progress_message.edit_text("<b>✅ Скачивание завершено! Обработка видео…</b>", parse_mode='HTML')
            except Exception:
                pass
            await asyncio.sleep(0.5)
            try:
                await progress_message.delete()
            except Exception:
                pass
        def progress_hook(d):
            print('progress_hook:', d)  # DEBUG print
            if d['status'] == 'downloading':
                percent = d.get('downloaded_bytes', 0) / max(d.get('total_bytes', d.get('total_bytes_estimate', 1)), 1) * 100 if d.get('total_bytes') or d.get('total_bytes_estimate') else 0
                percent = min(max(percent, 0), 99)
                if int(percent) != last_percent['value']:
                    last_percent['value'] = int(percent)
                    loop = asyncio.get_running_loop()
                    loop.create_task(update_progress(percent))
            elif d['status'] == 'finished':
                loop = asyncio.get_running_loop()
                loop.create_task(finish_progress())
        return progress_hook
    ydl_opts = {
        'outtmpl': 'video.%(ext)s',
        'format': ydl_format,
        'quiet': True,
        'merge_output_format': 'mp4',
        'ffmpeg_location': FFMPEG_PATH,
        'progress_hooks': [progress_hook_factory(progress_message)],
    }
    # Добавляем cookies для Instagram
    if platform == "instagram":
        ydl_opts['cookiefile'] = 'insta_cookies.txt'
    if PROXY_URL:
        ydl_opts['proxy'] = PROXY_URL
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
    except Exception as e:
        print(f"YT-DLP ERROR: {e}")
        try:
            await progress_message.edit_text(f"<b>❌ Ошибка при скачивании:</b> <code>{str(e)}</code>", parse_mode="HTML")
        except Exception as err:
            print(f"TG SEND ERROR: {err}")
        return
    base, ext = os.path.splitext(filename)
    need_convert = not is_compatible_mp4(filename)
    if need_convert:
        width, height, _ = get_video_metadata(filename)
        fixed_name = base + '_fixed.mp4'
        if quality == 'normal':
            scale_arg = '-2:720' if max(width, height) > 720 else 'iw:ih'
            crf = '28'
        else:
            scale_arg = 'iw:ih'
            crf = '20'
        subprocess.run([
            FFMPEG_PATH, '-i', filename,
            '-vf', f'scale={scale_arg}',
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', crf,
            '-c:a', 'aac', '-movflags', '+faststart', '-y', fixed_name
        ])
        os.remove(filename)
        filename = fixed_name
    file_size = os.path.getsize(filename)
    # Если файл больше 50 МБ, пробуем сжать до 720p crf=28
    if file_size > MAX_FILE_SIZE:
        width, height, _ = get_video_metadata(filename)
        fixed_name = base + '_compressed.mp4'
        subprocess.run([
            FFMPEG_PATH, '-i', filename,
            '-vf', 'scale=-2:720',
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '28',
            '-c:a', 'aac', '-movflags', '+faststart', '-y', fixed_name
        ])
        os.remove(filename)
        filename = fixed_name
        file_size = os.path.getsize(filename)
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад", callback_data="back_to_menu")
    if file_size <= MAX_FILE_SIZE:
        width, height, duration = get_video_metadata(filename)
        thumbnail_path = base + '_thumb.jpg'
        subprocess.run([
            FFMPEG_PATH, '-i', filename, '-ss', '00:00:01.000', '-vframes', '1', '-vf', 'scale=320:320:force_original_aspect_ratio=decrease', '-q:v', '2', thumbnail_path
        ])
        video_file = FSInputFile(filename)
        thumb_file = FSInputFile(thumbnail_path)
        await message.answer_video(
            video_file,
            caption="Ваше видео готово! 🎉",
            thumbnail=thumb_file,
            width=width,
            height=height,
            duration=int(duration),
            supports_streaming=True,
            reply_markup=builder.as_markup()
        )
        os.remove(filename)
        os.remove(thumbnail_path)
    else:
        await message.answer("<i>Файл больше 50 МБ даже после сжатия. К сожалению, Telegram API не позволяет отправлять такие файлы напрямую через бота.</i>", parse_mode="HTML")
        os.remove(filename)

# Обработка кнопки назад
@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    await start_cmd(callback.message)

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    is_sub = await check_subscription(callback.from_user.id)
    if is_sub:
        await callback.message.delete()
        # Показываем меню выбора платформы
        builder = InlineKeyboardBuilder()
        builder.button(text="🎵 TikTok", callback_data="platform_tiktok")
        builder.button(text="📸 Instagram", callback_data="platform_instagram")
        builder.adjust(2)
        await callback.message.answer(WELCOME_TEXT, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        await callback.answer("Вы еще не подписались!", show_alert=True)

def get_video_metadata(filename):
    result = subprocess.run([
        FFPROBE_PATH,
        '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,duration',
        '-of', 'json', filename
    ], capture_output=True, text=True)
    info = json.loads(result.stdout)
    stream = info['streams'][0]
    width = int(stream.get('width', 0))
    height = int(stream.get('height', 0))
    duration = float(stream.get('duration', 0))
    return width, height, duration

def is_compatible_mp4(filename):
    # Проверяем кодеки и разрешение через ffprobe
    result = subprocess.run([
        FFPROBE_PATH,
        '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=codec_name,width,height',
        '-of', 'json', filename
    ], capture_output=True, text=True)
    info = json.loads(result.stdout)
    vstream = info['streams'][0]
    vcodec = vstream.get('codec_name', '')
    width = int(vstream.get('width', 0))
    height = int(vstream.get('height', 0))
    a_ok = False
    try:
        result = subprocess.run([
            FFPROBE_PATH,
            '-v', 'error', '-select_streams', 'a:0',
            '-show_entries', 'stream=codec_name',
            '-of', 'json', filename
        ], capture_output=True, text=True)
        ainfo = json.loads(result.stdout)
        acodec = ainfo['streams'][0].get('codec_name', '')
        a_ok = acodec in ('aac', 'mp3')
    except Exception:
        pass
    return vcodec == 'h264' and a_ok and max(width, height) <= 720

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def set_user_platform(user_id: int, platform: str):
    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        if user:
            user.platform = platform
        else:
            user = User(user_id=user_id, platform=platform)
            session.add(user)
        await session.commit()

async def get_user_platform(user_id: int):
    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        return user.platform if user else None

async def main():
    print('Бот запускается...')
    try:
        await init_db()
        await dp.start_polling(bot)
    except Exception as e:
        print('Ошибка при запуске polling:', e)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"GLOBAL ERROR: {e}") 