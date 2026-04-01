import asyncio
import json
import logging
import feedparser
import re
import time
import html
from threading import Thread
from flask import Flask
from telegram import Bot
from telegram.error import TimedOut, NetworkError

# ===== НАСТРОЙКИ =====
TOKEN = "8592760077:AAF91JKp2G1PJSAwAChTZz3GII40DSwQrjo"
CHANNEL_ID = "@Newskins_cs2"
CONFIG_FILE = "config.json"

PROMO_TEXT = """PGL Major Bucharest just ended. In celebration, organizers are distributing souvenir skins to active players.

Claim your CS2 skins here: [LINK]"""

PROMO_IMAGES = [
    "https://i.ibb.co/BHfSKy5q/image.png",
    "https://i.ibb.co/gbv3q4jw/image.png",
    "https://i.ibb.co/6csDgZjT/image.png",
    "https://i.ibb.co/MkvBhw7b/image.png",
    "https://i.ibb.co/fVR3v5Zn/image.png",
    "https://i.ibb.co/VcWqm5nL/image.png",
    "https://i.ibb.co/KpSqYJ5y/image.png",
    "https://i.ibb.co/zhDGVvcj/image.png"
]

RSS_INTERVAL = 1800
PROMO_INTERVAL = 16200
# =========================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

promo_index = 0

# Flask приложение для Render
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "Bot is running!"

# ===== ВСЕ ФУНКЦИИ БОТА (те же самые) =====
def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
            if "feeds" not in config:
                config["feeds"] = []
            if "last_posts" not in config:
                config["last_posts"] = {}
            return config
    except:
        default_config = {
            "feeds": [
                "https://www.hltv.org/rss/news",
                "https://blog.counter-strike.net/index.php/feed/",
                "https://www.reddit.com/r/GlobalOffensive/.rss",
                "https://www.reddit.com/r/CSGO/.rss"
            ],
            "last_posts": {}
        }
        save_config(default_config)
        return default_config

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

def extract_image(entry):
    if hasattr(entry, 'media_content') and entry.media_content:
        for media in entry.media_content:
            if 'url' in media:
                return media['url']
    if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
        if len(entry.media_thumbnail) > 0 and 'url' in entry.media_thumbnail[0]:
            return entry.media_thumbnail[0]['url']
    summary = entry.get('summary', '')
    img_match = re.search(r'<img[^>]+src="([^">]+)"', summary)
    if img_match:
        return img_match.group(1)
    return None

def clean_text(text):
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    text = re.sub(r'&#32;', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'submitted by.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[\s*link\s*\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'source:.*?(?=\n|$)', '', text, flags=re.IGNORECASE)
    return text.strip()

def format_post(entry):
    title = clean_text(entry.get("title", "CS2 News"))
    summary = entry.get("summary", "")
    if hasattr(entry, 'content') and entry.content:
        content = entry.content[0].value if isinstance(entry.content, list) else entry.content
        summary = str(content)
    summary = clean_text(summary)
    if len(summary) > 600:
        summary = summary[:600] + "..."
    if summary and len(summary) > 10:
        message = f"**{title}**\n\n{summary}"
    else:
        message = f"**{title}**"
    return message, extract_image(entry)

async def send_with_retry(bot, chat_id, text, image_url=None, retries=3):
    for i in range(retries):
        try:
            if image_url:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=image_url,
                    caption=text,
                    parse_mode="Markdown"
                )
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="Markdown"
                )
            return True
        except (TimedOut, NetworkError) as e:
            logger.error(f"Attempt {i+1} failed: {e}")
            if i < retries - 1:
                await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Send error: {e}")
            return False
    return False

async def check_rss():
    bot = Bot(token=TOKEN)
    config = load_config()
    
    if not config["feeds"]:
        return
    
    for feed_url in config["feeds"]:
        try:
            feed = feedparser.parse(feed_url)
            last_id = config["last_posts"].get(feed_url, "")
            
            if feed.entries:
                newest = feed.entries[0]
                entry_id = newest.get("id") or newest.get("link")
                
                if entry_id and entry_id != last_id:
                    message, image_url = format_post(newest)
                    success = await send_with_retry(bot, CHANNEL_ID, message, image_url)
                    if success:
                        logger.info(f"RSS posted: {newest.get('title', 'No title')[:50]}")
                        config["last_posts"][feed_url] = entry_id
                        save_config(config)
                        return
        except Exception as e:
            logger.error(f"RSS error {feed_url}: {e}")

async def send_promo():
    global promo_index
    bot = Bot(token=TOKEN)
    
    image_url = PROMO_IMAGES[promo_index % len(PROMO_IMAGES)]
    promo_index += 1
    
    success = await send_with_retry(bot, CHANNEL_ID, PROMO_TEXT, image_url)
    if success:
        logger.info(f"Promo posted (image {promo_index}/{len(PROMO_IMAGES)})")
    else:
        logger.error("Promo failed")

async def worker():
    last_rss = 0
    last_promo = 0
    
    while True:
        now = time.time()
        
        if now - last_rss >= RSS_INTERVAL:
            await check_rss()
            last_rss = now
        
        if now - last_promo >= PROMO_INTERVAL:
            await send_promo()
            last_promo = now
        
        await asyncio.sleep(60)

def run_bot():
    asyncio.run(worker())

# ===== ЗАПУСК =====
if __name__ == "__main__":
    # Запускаем бота в отдельном потоке
    bot_thread = Thread(target=run_bot)
    bot_thread.start()
    # Запускаем Flask сервер
    app_flask.run(host="0.0.0.0", port=8080)
