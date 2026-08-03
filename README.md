# Cafe Aroma — Telegram Mini App

## Fayllar
- `bot.py` — Aiogram 3 (bot) + FastAPI (API va statik fayl serveri), bitta faylda.
- `index.html` — Mini App frontend (Telegram WebApp SDK + Leaflet.js).
- `requirements.txt` — Python kutubxonalari.
- `tables_state.json` — stollar holati avtomatik yaratiladi va saqlanadi (bot birinchi marta ishga tushganda).

## O'rnatish

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Sozlash

`bot.py` faylidagi CONFIG bo'limini muhit o'zgaruvchilari orqali yoki to'g'ridan-to'g'ri to'ldiring:

```bash
export BOT_TOKEN="123456:ABC-DEF..."        # @BotFather dan olingan token
export ADMIN_CHAT_ID="123456789"            # Buyurtmalar tushadigan admin Chat ID
export WEBAPP_URL="https://your-domain.com" # index.html joylashgan HTTPS manzil
```

> **Muhim:** Telegram Mini App faqat **HTTPS** manzilda ishlaydi.
> Lokal test uchun `ngrok http 8000` yoki `cloudflared tunnel --url http://localhost:8000`
> ishlatib, chiqqan HTTPS manzilni `WEBAPP_URL` ga va @BotFather → Bot Settings →
> Menu Button / Web App sozlamalariga kiriting.

Admin Chat ID ni bilish uchun @userinfobot yoki @RawDataBot ga yozing.

## Ishga tushirish

```bash
python bot.py
```

Bu bir vaqtning o'zida:
1. Aiogram botni **polling** rejimida ishga tushiradi (`/start` buyrug'i WebApp tugmasini yuboradi).
2. FastAPI serverni `http://0.0.0.0:8000` da ishga tushiradi va `index.html` ni shu orqali uzatadi.

## Ishlash tartibi

1. Foydalanuvchi botga `/start` yozadi → WebApp tugmasi chiqadi.
2. Mini App ochiladi: stol tanlaydi, menyudan mahsulot qo'shadi, ism/telefon kiritadi, xaritadan manzil belgilaydi.
3. "Tasdiqlash" tugmasi bosilganda frontend `/api/order` ga POST so'rov yuboradi.
4. Backend ma'lumotlarni tekshiradi (validation), stolni "band" qiladi va to'liq ma'lumotni
   `ADMIN_CHAT_ID` ga Telegram xabari + lokatsiya sifatida yuboradi.
5. `/api/tables` endpointi orqali frontend har 4 soniyada stollar holatini yangilab turadi
   (real vaqt effekti).

## Ixtiyoriy: stolni qayta bo'shatish

Admin panelga ulash uchun tayyor endpoint mavjud:

```
POST /api/tables/{table_id}/free
```
