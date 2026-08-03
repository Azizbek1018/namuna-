# -*- coding: utf-8 -*-
"""
CAFE AROMA — Telegram Mini App backend
========================================
Bitta faylda: Aiogram 3 (bot) + FastAPI (WebApp uchun API va statik fayllarni
uzatish). Ikkisi bir vaqtda asyncio.gather() orqali ishga tushiriladi.

ISHGA TUSHIRISH:
    1) python -m venv venv && source venv/bin/activate   (Windows: venv\\Scripts\\activate)
    2) pip install -r requirements.txt
    3) Quyidagi CONFIG bo'limini to'ldiring (BOT_TOKEN, ADMIN_CHAT_ID, WEBAPP_URL)
    4) python bot.py

ESLATMA:
    Telegram Mini App faqat HTTPS manzilda ishlaydi. Lokal test uchun
    ngrok / cloudflared kabi tunnel ishlatib, WEBAPP_URL ni shu HTTPS
    manzilga tenglashtiring va @BotFather orqali botning Menu Button /
    Web App tugmasiga ham xuddi shu URL ni bering.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import List, Optional

import uvicorn
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

# ============================================================
#                         CONFIG
# ============================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "1234567890:PUT_YOUR_BOT_TOKEN_HERE")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "000000000"))  # Admin Telegram Chat ID
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-https-domain.com")  # index.html joylashgan HTTPS manzil
CAFE_NAME = os.getenv("CAFE_NAME", "Cafe Aroma")

BASE_DIR = Path(__file__).resolve().parent
TABLES_FILE = BASE_DIR / "tables_state.json"
TOTAL_TABLES = 8  # kamida 6 ta, shart bo'yicha 8 ta stol qildik

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("cafe-aroma")

# ============================================================
#              STOLLAR HOLATINI SAQLASH (JSON fayl)
# ============================================================
_lock = asyncio.Lock()


def load_tables() -> dict:
    if TABLES_FILE.exists():
        try:
            with open(TABLES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for i in range(1, TOTAL_TABLES + 1):
                data.setdefault(str(i), "available")
            return data
        except Exception as exc:  # noqa: BLE001
            logger.warning("tables_state.json o'qishda xatolik: %s", exc)
    return {str(i): "available" for i in range(1, TOTAL_TABLES + 1)}


def save_tables(data: dict) -> None:
    with open(TABLES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


tables_state: dict = load_tables()

# ============================================================
#                     AIOGRAM BOT QISMI
# ============================================================
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


def _webapp_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="☕️ Buyurtma berish", web_app=WebAppInfo(url=WEBAPP_URL))]
        ]
    )


@dp.message(CommandStart())
async def start_handler(message: types.Message) -> None:
    text = (
        f"Xush kelibsiz! ☕️\n\n"
        f"<b>{CAFE_NAME}</b> rasmiy Telegram botiga xush kelibsiz!\n\n"
        f"Bu yerdan siz:\n"
        f"🪑 Stol bron qilishingiz\n"
        f"🍔 Menyudan taom tanlashingiz\n"
        f"📍 Yetkazib berish manzilini belgilashingiz mumkin.\n\n"
        f"Boshlash uchun pastdagi tugmani bosing 👇"
    )
    await message.answer(text, reply_markup=_webapp_keyboard())


@dp.message(F.text)
async def fallback_handler(message: types.Message) -> None:
    await message.answer(
        "Buyurtma berish uchun quyidagi tugmani bosing 👇",
        reply_markup=_webapp_keyboard(),
    )


# ============================================================
#                        FASTAPI QISMI
# ============================================================
app = FastAPI(title=f"{CAFE_NAME} Mini App API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class OrderItem(BaseModel):
    id: int
    name: str
    price: float = Field(gt=0)
    qty: int = Field(gt=0, le=50)


class OrderRequest(BaseModel):
    table: int
    name: str
    phone: str
    items: List[OrderItem]
    lat: Optional[float] = None
    lng: Optional[float] = None
    address_note: Optional[str] = ""
    total: float
    tg_user_id: Optional[int] = None
    tg_username: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        v = v.strip().replace(" ", "")
        if not v.startswith("+998") or len(v) != 13 or not v[1:].isdigit():
            raise ValueError("Telefon raqam +998XXXXXXXXX formatida bo'lishi kerak")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Ism-familiya juda qisqa")
        return v

    @field_validator("items")
    @classmethod
    def validate_items(cls, v: List[OrderItem]) -> List[OrderItem]:
        if not v:
            raise ValueError("Savatcha bo'sh — kamida 1 ta mahsulot tanlang")
        return v

    @field_validator("table")
    @classmethod
    def validate_table(cls, v: int) -> int:
        if v < 1 or v > TOTAL_TABLES:
            raise ValueError("Noto'g'ri stol raqami")
        return v


@app.get("/api/tables")
async def get_tables():
    """Frontend real vaqt rejimida bu endpointni poll qilib turadi."""
    return {"total": TOTAL_TABLES, "tables": tables_state}


@app.post("/api/order")
async def create_order(order: OrderRequest):
    table_key = str(order.table)

    async with _lock:
        if table_key not in tables_state:
            raise HTTPException(status_code=400, detail="Noto'g'ri stol raqami")
        if tables_state[table_key] == "reserved":
            raise HTTPException(status_code=409, detail="Afsuski, bu stol allaqachon band qilindi")

        # Antispam: minimal summa tekshiruvi
        calculated_total = sum(i.price * i.qty for i in order.items)
        if abs(calculated_total - order.total) > 1:
            raise HTTPException(status_code=400, detail="Savatcha summasi mos kelmadi, sahifani yangilang")

        tables_state[table_key] = "reserved"
        save_tables(tables_state)

    items_text = "\n".join(
        f"  • {item.name} × {item.qty} — {item.price * item.qty:,.0f} so'm".replace(",", " ")
        for item in order.items
    )

    if order.lat is not None and order.lng is not None:
        location_link = f"https://maps.google.com/?q={order.lat},{order.lng}"
    else:
        location_link = "❗️ Belgilanmagan"

    username_part = f"@{order.tg_username}" if order.tg_username else "—"

    admin_text = (
        "🆕 <b>YANGI BUYURTMA!</b>\n"
        "――――――――――――――――\n"
        f"🪑 <b>Stol:</b> {order.table}-stol\n"
        f"👤 <b>Ism:</b> {order.name}\n"
        f"📞 <b>Tel:</b> {order.phone}\n"
        f"🔗 <b>Telegram:</b> {username_part} (ID: {order.tg_user_id or '—'})\n\n"
        f"🧾 <b>Buyurtma:</b>\n{items_text}\n\n"
        f"💰 <b>Jami summa:</b> {order.total:,.0f} so'm".replace(",", " ") + "\n\n"
        f"📍 <b>Yetkazish manzili:</b> {location_link}\n"
        f"📝 <b>Izoh:</b> {order.address_note or '—'}"
    )

    try:
        await bot.send_message(ADMIN_CHAT_ID, admin_text)
        if order.lat is not None and order.lng is not None:
            await bot.send_location(ADMIN_CHAT_ID, latitude=order.lat, longitude=order.lng)
    except Exception as exc:  # noqa: BLE001
        logger.error("Adminga xabar yuborishda xatolik: %s", exc)

    return {"ok": True, "message": "✅ Buyurtmangiz qabul qilindi! Tez orada siz bilan bog'lanamiz."}


@app.post("/api/tables/{table_id}/free")
async def free_table(table_id: int):
    """Admin uchun: stolni qayta bo'sh holatga o'tkazish (ixtiyoriy yordamchi endpoint)."""
    table_key = str(table_id)
    async with _lock:
        if table_key not in tables_state:
            raise HTTPException(status_code=404, detail="Stol topilmadi")
        tables_state[table_key] = "available"
        save_tables(tables_state)
    return {"ok": True}


# ---- Statik fayllarni (index.html, css, js) uzatish ----
app.mount("/static", StaticFiles(directory=str(BASE_DIR)), name="static")


@app.get("/")
async def index_page():
    return FileResponse(BASE_DIR / "index.html")


# ============================================================
#             BOT VA API NI BIRGALIKDA ISHGA TUSHIRISH
# ============================================================
async def start_bot_polling() -> None:
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Aiogram bot polling rejimida ishga tushdi ✅")
    await dp.start_polling(bot)


async def start_api() -> None:
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)), log_level="info")
    server = uvicorn.Server(config)
    logger.info("FastAPI server http://0.0.0.0:8000 da ishga tushdi ✅")
    await server.serve()


async def main() -> None:
    await asyncio.gather(start_bot_polling(), start_api())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
