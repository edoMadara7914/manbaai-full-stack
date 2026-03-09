# ManbaAI Replit Starter

Bu loyiha Replit uchun tayyorlangan Telegram bot starteri.

## Nimalar bor
- `/start` → obuna tekshiruvi → til tanlash
- private + public qidiruv
- javob 2 bo'limda: shaxsiy va ommaviy
- har bo'limda: qisqa javob, batafsil, manba
- fayl upload: PDF, DOCX, TXT, rasm, ovoz, matn
- public moderatsiya
- user o'z fayl nomini o'zgartira oladi
- admin istalgan fayl nomini o'zgartira oladi
- tariflar: Free / Basic / Premium
- Stars / Click / Admin orqali tarif olish uchun starter oqimlar
- referral: 5 user = 7 kun Basic
- admin dashboard va export

## Muhim eslatma
Bu production-ready skeleton. U sintaksis va asosiy oqimlar bo'yicha tekshirilgan, lekin siz tokenlar, Click linklari va admin IDlarni o'zingiz to'ldirasiz.

## O'rnatish
1. Replit projectga fayllarni yuklang.
2. `.env.example` dan `.env` qiling.
3. Terminalda:

```bash
pip install -r requirements.txt
python main.py
```

## To'lovlar
- Telegram Stars uchun `provider_token` bo'sh qoldiriladi va `currency="XTR"` ishlatiladi.
- Click linklari `.env` orqali beriladi.

## OpenAI
Loyiha OpenAI Responses API, Embeddings va Audio Transcriptions bilan ishlaydi. Official docs:
- Responses API: https://developers.openai.com/api/reference/resources/responses
- Speech-to-text: https://developers.openai.com/api/docs/guides/speech-to-text
