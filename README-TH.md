# Discord Music Bot (Python) — สำหรับเซิร์ฟ Roblox / Valo / ดนตรี

คำสั่ง: `/play` `/skip` `/stop` `/pause` `/resume` `/queue` `/nowplaying` `/leave`

## 1) สร้างบอทเอาโทเคน (5 นาที)
1. https://discord.com/developers/applications > New Application > ตั้งชื่อ
2. เมนู Bot > Add Bot > Reset Token > ก็อปโทเคนไว้
3. เปิด Privileged Gateway Intents: SERVER MEMBERS + MESSAGE CONTENT (กันเหนียว)
4. เมนู OAuth2 > URL Generator > Scopes: `bot`, `applications.commands` > Permissions: Connect, Speak, Send Messages, Read Message History > เปิดลิงก์เชิญบอทเข้าเซิร์ฟ

## 2) รันในคอม (เทส)
```powershell
# ติดตั้ง FFmpeg ก่อน (รอบเดียว)
winget install Gyan.FFmpeg
# แล้วเปิด terminal ใหม่
pip install -r requirements.txt
copy .env.example .env
# เปิด .env ใส่ DISCORD_TOKEN
python bot.py
```

## 3) Deploy ฟรี 24/7 — ความจริง
| ที่ | ฟรีจริง 24/7? | เหมาะกับบอทเพลง? |
|---|---|---|
| เปิดคอมตัวเองทิ้งไว้ | ✅ ฟรี แต่ค่าไฟ + เน็ต | ✅ ดีสุดสำหรับเริ่ม YouTube ไม่โดนบล็อก IP ร่วม |
| Oracle Cloud Always Free | ✅ ฟรีถาวร (ต้องยืนยันบัตร, สมัครยาก) | ✅ ดีสุดแบบเซิร์ฟเวอร์จริง |
| Render Free / Replit Free | ❌ หลับหลัง 15 นาทีไม่มีคนเรียก + IP ร่วมโดน YouTube แบนบ่อย | ⚠️ เทสได้ รันจริงเพลงหลุด |
| Railway | ได้ $5 trial หลังจากนั้นจ่าย | ⚠️ ดีกว่า Render แต่ไม่ฟรีถาวร |

แนะนำ: เริ่มรันบนคอมก่อน ถ้าจะ 24/7 จริงค่อยย้ายไป Oracle VPS (Ubuntu + `apt install ffmpeg python3` แล้ว `python bot.py` ผ่าน tmux/systemd)

บน Render/Railway: ตั้ง Start Command เป็น `python bot.py`, ใส่ Env `DISCORD_TOKEN`, `SEARCH_SOURCE=scsearch`
