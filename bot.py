# 🧸💗 Love Teddy Music Bot (Python) — clean embeds + YouTube bridge + ephemeral
# คำสั่ง: /play /panel /nowplaying /queue /skip /stop /pause /resume /loop /shuffle /volume /remove /leave
# รัน: pip install -r requirements.txt แล้ว python bot.py (ต้องมี FFmpeg)
# ไฟล์ image.png (โลโก้เท็ดดี้) วางข้าง bot.py ได้เลย ถ้าไม่มีบอทก็รันได้ปกติ

import asyncio
import os
import random
import re
import threading
from concurrent.futures import ThreadPoolExecutor

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from yt_dlp import YoutubeDL

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "")
SEARCH_SOURCE = os.getenv("SEARCH_SOURCE", "scsearch")  # ytsearch | scsearch
SPOTIFY_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
YT_API_KEY = os.getenv("YOUTUBE_API_KEY", "")  # ใส่ก็ได้ ไม่ใส่ก็ได้ (เอาไว้ค้น/อ่านชื่อคลิป YouTube ให้แม่น)
YT_COOKIES = os.getenv("YOUTUBE_COOKIES", "")  # เนื้อไฟล์ cookies.txt (ออปชัน เสี่ยงโดน Google แบนแอคเคาต์ อ่านคำเตือนใน .env.example)

if not TOKEN:
    print("❌ ไม่เจอ DISCORD_TOKEN — ก็อป .env.example เป็น .env ก่อน")
    raise SystemExit(1)

# ---------- theme ----------
PINK = 0xFF9EBB
PINK_DARK = 0xFF6FA5
TEDDY = "🧸"
HEART = "💗"
RIBBON = "🎀"
PANEL_TITLE = f"{TEDDY}{HEART} Love Teddy DJ {HEART}{TEDDY}"
FOOTER = f"{RIBBON} Love Teddy"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BRAND_PATH = os.path.join(BASE_DIR, "image.png")

YOUTUBE_RE = re.compile(r"youtube\.com|youtu\.be|music\.youtube\.com", re.I)
SPOTIFY_RE = re.compile(r"open\.spotify\.com", re.I)
URL_RE = re.compile(r"^https?://", re.I)

YDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "retries": 3,
    "socket_timeout": 15,
    # ลอง client หลายตัว เวลา YouTube บล็อกตัวใดตัวหนึ่ง
    "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
}

# ถ้าใส่ YOUTUBE_COOKIES มา เขียนลงไฟล์ temp ให้ yt-dlp ใช้ (โดนล้างทุกครั้งที่รีบอท แต่เขียนใหม่จาก env ทุกรอบ)
import tempfile
COOKIE_PATH = os.path.join(tempfile.gettempdir(), "ytcookies.txt")
if YT_COOKIES.strip():
    try:
        with open(COOKIE_PATH, "w", encoding="utf-8") as f:
            f.write(YT_COOKIES)
        YDL_OPTS["cookiefile"] = COOKIE_PATH
        print("🍪 ใช้ YouTube cookies (โหมดเสียงจริง)")
    except Exception as e:
        print("[cookies]", e)
FFMPEG_BEFORE = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin"
FFMPEG_OPTS = "-vn"

intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)
pool = ThreadPoolExecutor(max_workers=4)

# guild_id -> {"queue": [], "current": None, "text": None, "loop": "off", "volume": 80}
queues: dict[int, dict] = {}


def get_state(guild_id: int) -> dict:
    st = queues.get(guild_id)
    if not st:
        st = {"queue": [], "current": None, "text": None, "loop": "off", "volume": 80}
        queues[guild_id] = st
    return st


def fmt_dur(sec) -> str:
    try:
        s = int(sec or 0)
        return f"{s // 60}:{s % 60:02d}"
    except Exception:
        return "—"


def loop_label(mode: str) -> str:
    return {"off": "ปิด", "track": "🔂 เพลงนี้", "queue": "🔁 ทั้งคิว"}.get(mode, mode)


def brand_file() -> discord.File | None:
    """แนบ image.png ถ้ามี (ไม่มีก็ข้าม ไม่พัง)"""
    try:
        if os.path.isfile(BRAND_PATH):
            return discord.File(BRAND_PATH, filename="image.png")
    except Exception:
        pass
    return None


def has_brand() -> bool:
    return os.path.isfile(BRAND_PATH)


# ---------- embeds แบบคลีน ----------
def song_embed(track: dict, st: dict) -> discord.Embed:
    """embed สาธารณะอันเดียวในห้อง: รูปเพลง + ชื่อเพลง + คิวถัดไป ไม่รก"""
    nxt = st["queue"][0] if st.get("queue") else None
    e = discord.Embed(title=f"🎵 {track['title']}"[:256], description=f"{track.get('author', '')} • {fmt_dur(track.get('duration'))} • ขอโดย {track.get('by_mention', '—')}"[:4000], color=PINK)
    if track.get("thumbnail"):
        e.set_image(url=track["thumbnail"])
    if has_brand():
        e.set_thumbnail(url="attachment://image.png")
    if nxt:
        e.add_field(name="⏭️ ถัดไป", value=f"{nxt['title']}"[:300], inline=False)
    else:
        seed = track.get("author") or ""
        e.add_field(name="⏭️ ถัดไป", value=f"ว่าง — กด ▶️ ต่อแนวนี้ (แนว {seed}) หรือ ➕ ขอเพลงได้เลย"[:300], inline=False)
    e.set_footer(text=FOOTER)
    return e


def queued_ephemeral(track: dict, pos: int, bridge: bool) -> discord.Embed:
    desc = f"**{track['title']}**\nคิวที่ #{pos} — เพลงจะขึ้นในห้องให้ทุกคนเห็นเอง"
    if bridge:
        desc += "\n🔗 ลิงก์ YouTube เล่นตรงไม่ได้บนโฮสต์ฟรี ต่อเสียงให้ผ่าน SoundCloud แล้ว"
    e = discord.Embed(title=f"{HEART} รับเพลงแล้ว", description=desc[:4000], color=PINK_DARK)
    return e


def queue_embed(st: dict) -> discord.Embed:
    e = discord.Embed(title=f"{TEDDY} คิวเพลง {HEART}", color=PINK)
    if st.get("current"):
        c = st["current"]
        e.add_field(name="▶️ กำลังเล่น", value=f"**{c['title']}** ({fmt_dur(c.get('duration'))})", inline=False)
    if st["queue"]:
        lines = [f"`{i}.` {t['title']}" for i, t in enumerate(st["queue"][:15], 1)]
        e.add_field(name=f"📋 ต่อคิว ({len(st['queue'])})", value="\n".join(lines)[:4000], inline=False)
    else:
        e.add_field(name="📋 ต่อคิว", value="ว่างแล้ว กด ➕ ขอเพลงได้เลย", inline=False)
    e.set_footer(text=FOOTER)
    return e


def panel_embed(st: dict) -> discord.Embed:
    cur = f"**{st['current']['title']}**" if st.get("current") else "ยังไม่มีเพลง — กด ➕ ขอเพลงได้เลย"
    e = discord.Embed(title=PANEL_TITLE, description=f"🎧 ตอนนี้: {cur}", color=PINK)
    e.add_field(name="📋 คิว", value=f"{len(st['queue'])} เพลง", inline=True)
    e.add_field(name="🔁 ลูป", value=loop_label(st.get("loop", "off")), inline=True)
    e.add_field(name="🔊 เสียง", value=f"{st.get('volume', 80)}%", inline=True)
    e.set_footer(text=FOOTER)
    return e


def error_embed(msg: str) -> discord.Embed:
    return discord.Embed(title=f"{TEDDY} อุ๊บส์", description=msg, color=0xFF5555)


# ---------- YouTube bridge (แก้ปัญหาโดนบล็อก) ----------
def yt_id_from_url(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/|shorts/|live/|embed/)([A-Za-z0-9_-]{6,})", url)
    return m.group(1) if m else None


async def youtube_meta(video_id: str) -> tuple[str | None, str | None, str | None]:
    """คืน (title, author, thumbnail) ของคลิป YouTube โดยไม่ต้องแตะเสียง
    ลำดับ: YouTube Data API (ถ้ามีคีย์) -> oEmbed (ฟรี ไม่ต้องมีคีย์)"""
    # 1) Official API
    if YT_API_KEY:
        try:
            import aiohttp
            url = "https://www.googleapis.com/youtube/v3/videos"
            params = {"id": video_id, "key": YT_API_KEY, "part": "snippet"}
            async with aiohttp.ClientSession() as s:
                async with s.get(url, params=params, timeout=10) as r:
                    if r.status == 200:
                        data = await r.json()
                        items = data.get("items") or []
                        if items:
                            sn = items[0].get("snippet", {})
                            thumbs = (sn.get("thumbnails") or {})
                            thumb = (thumbs.get("maxres") or thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url")
                            return sn.get("title"), sn.get("channelTitle"), thumb
        except Exception as e:
            print("[yt-api]", e)
    # 2) oEmbed ฟรี
    try:
        import aiohttp
        url = "https://www.youtube.com/oembed"
        params = {"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"}
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params=params, timeout=10) as r:
                if r.status == 200:
                    data = await r.json()
                    return data.get("title"), data.get("author_name"), f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    except Exception as e:
        print("[oembed]", e)
    return None, None, None


# ---------- extract ----------

def spotify_to_search(query: str) -> str:
    if not (SPOTIFY_ID and SPOTIFY_SECRET):
        return query
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials
        m = re.search(r"track/([A-Za-z0-9]+)", query)
        if not m:
            return query
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(SPOTIFY_ID, SPOTIFY_SECRET))
        t = sp.track(f"spotify:track:{m.group(1)}")
        return f"{t['name']} {' '.join(a['name'] for a in t['artists'])}"
    except Exception as e:
        print("[spotify]", e)
        return query


def extract_blocking(query: str) -> dict:
    err1 = None
    try:
        with YoutubeDL(dict(YDL_OPTS)) as ydl:
            info = ydl.extract_info(query, download=False)
            if isinstance(info, dict) and info.get("entries"):
                info = info["entries"][0]
            return info
    except Exception as e:
        err1 = e
        # ฟอร์แมต bestaudio ไม่มี (เจอบ่อยกับคลิป YouTube บางคลิป) -> ลอง best อะไรก็ได้ที่มีเสียง
        if "Requested format is not available" not in str(e):
            raise
    opts2 = dict(YDL_OPTS)
    opts2["format"] = "best[acodec!=none]/best"
    opts2["extractor_args"] = {"youtube": {"player_client": ["web"]}}
    with YoutubeDL(opts2) as ydl:
        info = ydl.extract_info(query, download=False)
        if isinstance(info, dict) and info.get("entries"):
            info = info["entries"][0]
        return info


async def extract(query: str) -> dict:
    return await asyncio.get_running_loop().run_in_executor(pool, extract_blocking, query)


def make_source(audio_url: str, volume: int):
    base = discord.FFmpegPCMAudio(audio_url, before_options=FFMPEG_BEFORE, options=FFMPEG_OPTS)
    return discord.PCMVolumeTransformer(base, volume=max(0, min(150, volume)) / 100)


def apply_volume(guild: discord.Guild, volume: int):
    vc = guild.voice_client
    if vc and isinstance(vc.source, discord.PCMVolumeTransformer):
        vc.source.volume = max(0, min(150, volume)) / 100


async def play_next(guild: discord.Guild, error=None):
    if error:
        print("[player]", error)
    st = get_state(guild.id)
    vc = guild.voice_client
    if not vc or not vc.is_connected():
        st["current"] = None
        return
    prev = st.get("current")
    if prev:
        if st.get("loop") == "track":
            st["queue"].insert(0, prev)
        elif st.get("loop") == "queue":
            st["queue"].append(prev)
    if not st["queue"]:
        st["current"] = None
        return
    track = st["queue"].pop(0)
    st["current"] = track
    try:
        vc.play(make_source(track["audio_url"], st.get("volume", 80)),
                after=lambda e: asyncio.run_coroutine_threadsafe(play_next(guild, e), bot.loop))
    except Exception as e:
        print("[voice]", e)
        return
    # ส่ง embed สาธารณะอันเดียวในห้อง + ปุ่ม วน/ข้าม/ต่อแนวนี้/ขอเพลง
    if st["text"]:
        try:
            f = brand_file()
            if f:
                await st["text"].send(embed=song_embed(track, st), view=MiniView(), file=f)
            else:
                await st["text"].send(embed=song_embed(track, st), view=MiniView())
        except Exception as e:
            print("[send]", e)


async def ensure_voice(member: discord.Member):
    if not member.voice or not member.voice.channel:
        return None, "เข้าห้องเสียงก่อน แล้วค่อยสั่ง"
    vc = member.guild.voice_client
    if vc and vc.channel != member.voice.channel:
        try:
            await vc.move_to(member.voice.channel)
        except Exception:
            return None, "บอทอยู่อีกห้องนึงแล้ว"
    if not vc:
        try:
            vc = await member.voice.channel.connect()
        except Exception:
            return None, "เข้าห้องเสียงไม่ได้ เช็คสิทธิ์ Connect/Speak ของบอท"
    return vc, None


async def enqueue(guild: discord.Guild, user, query: str) -> tuple[dict | None, bool, str | None]:
    """คืน (track, youtube_bridge, error)"""
    q = query.strip()
    bridge = False
    has_cookies = bool(YT_COOKIES.strip())
    try:
        if YOUTUBE_RE.search(q):
            if has_cookies:
                # มีคุกกี้: ลองเสียง YouTube จริงก่อน พังเมื่อไหร่ค่อย fallback ผ่าน source หลัก
                try:
                    info = await extract(q)
                    if not info.get("url"):
                        raise ValueError("no audio")
                except Exception as e:
                    print("[yt-direct fail, fallback bridge]", str(e)[:200])
                    info = None
                if info is None:
                    vid = yt_id_from_url(q)
                    yt_title, yt_author, yt_thumb = (await youtube_meta(vid)) if vid else (None, None, None)
                    if not yt_title:
                        return None, False, "YouTube บล็อกอยู่ ลองชื่อเพลงเฉยๆ หรือลิงก์ SoundCloud/Spotify แทน"
                    bridge = True
                    info = await extract(f"{SEARCH_SOURCE}1:{yt_title} {yt_author or ''}".strip())
                    info["title"] = yt_title
                    info["uploader"] = yt_author or info.get("uploader", "")
                    info["thumbnail"] = yt_thumb or info.get("thumbnail", "")
            else:
                # ไม่มีคุกกี้: YouTube เล่นเสียงตรงโดนบล็อกบนโฮสต์ฟรี -> อ่านชื่อคลิปแล้วต่อเสียงผ่าน source หลักแทน
                vid = yt_id_from_url(q)
                yt_title, yt_author, yt_thumb = (await youtube_meta(vid)) if vid else (None, None, None)
                if not yt_title:
                    return None, False, "อ่านลิงก์ YouTube ไม่ได้ ลองชื่อเพลงเฉยๆ หรือลิงก์ SoundCloud/Spotify แทน"
                bridge = True
                info = await extract(f"{SEARCH_SOURCE}1:{yt_title} {yt_author or ''}".strip())
                info["title"] = yt_title
                info["uploader"] = yt_author or info.get("uploader", "")
                info["thumbnail"] = yt_thumb or info.get("thumbnail", "")
        else:
            if SPOTIFY_RE.search(q):
                q = spotify_to_search(q)
            if not URL_RE.match(q):
                q = f"{SEARCH_SOURCE}1:{q}"
            info = await extract(q)
    except Exception as e:
        msg = str(e)
        if "confirm you are not a bot" in msg or "Sign in to confirm" in msg or "403" in msg:
            return None, False, "YouTube บล็อก IP โฮสต์นี้ ลองชื่อเพลงเฉยๆ หรือลิงก์ SoundCloud/Spotify แทน"
        return None, False, f"หาเพลงไม่เจอ: {msg[:300]}"
    if not info.get("url"):
        return None, False, "ดึงเสียงไม่ได้ ลองลิงก์อื่น"
    track = {
        "title": str(info.get("title", "Unknown"))[:100],
        "audio_url": info["url"],
        "webpage": info.get("webpage_url", ""),
        "thumbnail": info.get("thumbnail", ""),
        "duration": info.get("duration", 0),
        "author": info.get("uploader") or info.get("artist") or "—",
        "by": str(user),
        "by_mention": user.mention if hasattr(user, "mention") else str(user),
    }
    st = get_state(guild.id)
    st["queue"].append(track)
    return track, bridge, None


# ---------- ปุ่ม + กล่องขอเพลง ----------

class SongModal(discord.ui.Modal, title=f"{TEDDY} ขอเพลง {HEART}"):
    song = discord.ui.TextInput(label="ชื่อเพลง / ลิงก์", placeholder="พิมพ์ชื่อเพลงหรือแปะลิงก์ Spotify", max_length=200)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice:
            return await interaction.followup.send("เข้าห้องเสียงก่อนน้า", ephemeral=True)
        vc, err = await ensure_voice(member)
        if err:
            return await interaction.followup.send(err, ephemeral=True)
        st = get_state(interaction.guild.id)
        st["text"] = interaction.channel
        track, bridge, err = await enqueue(interaction.guild, member, self.song.value)
        if err:
            return await interaction.followup.send(embed=error_embed(err), ephemeral=True)
        pos = len(st["queue"])
        await interaction.followup.send(embed=queued_ephemeral(track, pos, bridge), ephemeral=True)
        if not vc.is_playing() and not vc.is_paused() and st["current"] is None and len(st["queue"]) == 1:
            await play_next(interaction.guild)


class MiniView(discord.ui.View):
    """ปุ่มใต้ embed เพลง (สาธารณะ): วนเพลงนี้ / ข้าม / ต่อแนวนี้ / ขอเพลง"""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="ซ้ำเพลงนี้", emoji="🔂", style=discord.ButtonStyle.primary, custom_id="mini:repeat")
    async def repeat(self, interaction: discord.Interaction, _b: discord.ui.Button):
        st = get_state(interaction.guild.id)
        st["loop"] = "off" if st.get("loop") == "track" else "track"
        msg = "🔂 จะวนเพลงนี้อีกรอบแล้ว" if st["loop"] == "track" else "ปิดวนแล้ว"
        await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(label="ข้าม", emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="mini:skip")
    async def skip(self, interaction: discord.Interaction, _b: discord.ui.Button):
        vc = interaction.guild.voice_client
        if not vc or not vc.is_playing():
            return await interaction.response.send_message("ไม่มีเพลงให้ข้าม", ephemeral=True)
        vc.stop()  # เพลงต่อไป + embed ใหม่จะขึ้นในห้องเอง
        await interaction.response.send_message("⏭️ ข้ามแล้ว", ephemeral=True)

    @discord.ui.button(label="ต่อแนวนี้", emoji="▶️", style=discord.ButtonStyle.success, custom_id="mini:auto")
    async def auto(self, interaction: discord.Interaction, _b: discord.ui.Button):
        st = get_state(interaction.guild.id)
        cur = st.get("current")
        if not cur:
            return await interaction.response.send_message("ยังไม่มีเพลงเล่นอยู่", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        seed = cur.get("author") or cur["title"]
        track, _bridge, err = await enqueue(interaction.guild, interaction.user, seed)
        if err:
            return await interaction.followup.send(embed=error_embed(err), ephemeral=True)
        await interaction.followup.send(f"▶️ ต่อแนวนี้ให้แล้ว: **{track['title']}**", ephemeral=True)

    @discord.ui.button(label="ขอเพลง", emoji="➕", style=discord.ButtonStyle.secondary, custom_id="mini:add")
    async def add(self, interaction: discord.Interaction, _b: discord.ui.Button):
        await interaction.response.send_modal(SongModal())


class MusicView(discord.ui.View):
    """แผงใหญ่สำหรับ /panel"""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="ขอเพลง", emoji="➕", style=discord.ButtonStyle.primary, custom_id="teddy:add")
    async def add(self, interaction: discord.Interaction, _b: discord.ui.Button):
        await interaction.response.send_modal(SongModal())

    @discord.ui.button(label="พัก/ต่อ", emoji="⏸️", style=discord.ButtonStyle.secondary, custom_id="teddy:pause")
    async def pause(self, interaction: discord.Interaction, _b: discord.ui.Button):
        vc = interaction.guild.voice_client
        if not vc or (not vc.is_playing() and not vc.is_paused()):
            return await interaction.response.send_message("ไม่มีเพลงเล่นอยู่", ephemeral=True)
        if vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ พักก่อน", ephemeral=True)
        else:
            vc.resume()
            await interaction.response.send_message("▶️ ต่อแล้ว", ephemeral=True)

    @discord.ui.button(label="ข้าม", emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="teddy:skip")
    async def skip(self, interaction: discord.Interaction, _b: discord.ui.Button):
        vc = interaction.guild.voice_client
        if not vc or not vc.is_playing():
            return await interaction.response.send_message("ไม่มีเพลงให้ข้าม", ephemeral=True)
        vc.stop()
        await interaction.response.send_message("⏭️ ข้ามแล้ว", ephemeral=True)

    @discord.ui.button(label="หยุด", emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="teddy:stop")
    async def stop(self, interaction: discord.Interaction, _b: discord.ui.Button):
        st = get_state(interaction.guild.id)
        st["queue"].clear()
        st["current"] = None
        st["loop"] = "off"
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
        await interaction.response.send_message("⏹️ หยุด + ล้างคิวแล้ว", ephemeral=True)

    @discord.ui.button(label="ลูป", emoji="🔁", style=discord.ButtonStyle.secondary, custom_id="teddy:loop", row=1)
    async def loop(self, interaction: discord.Interaction, _b: discord.ui.Button):
        st = get_state(interaction.guild.id)
        st["loop"] = {"off": "track", "track": "queue", "queue": "off"}[st.get("loop", "off")]
        await interaction.response.send_message(f"🔁 ลูป: **{loop_label(st['loop'])}**", ephemeral=True)

    @discord.ui.button(label="สลับคิว", emoji="🔀", style=discord.ButtonStyle.secondary, custom_id="teddy:shuffle", row=1)
    async def shuffle(self, interaction: discord.Interaction, _b: discord.ui.Button):
        st = get_state(interaction.guild.id)
        if len(st["queue"]) < 2:
            return await interaction.response.send_message("คิวน้อยไป สลับไม่ได้", ephemeral=True)
        random.shuffle(st["queue"])
        await interaction.response.send_message(f"🔀 สลับคิวแล้ว ({len(st['queue'])} เพลง)", ephemeral=True)

    @discord.ui.button(label="คิว", emoji="📋", style=discord.ButtonStyle.secondary, custom_id="teddy:queue", row=1)
    async def showq(self, interaction: discord.Interaction, _b: discord.ui.Button):
        await interaction.response.send_message(embed=queue_embed(get_state(interaction.guild.id)), ephemeral=True)

    @discord.ui.button(label="-", emoji="🔉", style=discord.ButtonStyle.secondary, custom_id="teddy:vold", row=1)
    async def vold(self, interaction: discord.Interaction, _b: discord.ui.Button):
        st = get_state(interaction.guild.id)
        st["volume"] = max(0, st.get("volume", 80) - 10)
        apply_volume(interaction.guild, st["volume"])
        await interaction.response.send_message(f"🔉 เสียง {st['volume']}%", ephemeral=True)

    @discord.ui.button(label="+", emoji="🔊", style=discord.ButtonStyle.secondary, custom_id="teddy:volu", row=1)
    async def volu(self, interaction: discord.Interaction, _b: discord.ui.Button):
        st = get_state(interaction.guild.id)
        st["volume"] = min(150, st.get("volume", 80) + 10)
        apply_volume(interaction.guild, st["volume"])
        await interaction.response.send_message(f"🔊 เสียง {st['volume']}%", ephemeral=True)


# ---------- Slash commands (ตอบกลับแบบล่องหนทั้งหมด ยกเว้น embed เพลงในห้อง) ----------

@bot.tree.command(name="play", description=f"{TEDDY} เปิดเพลง (ชื่อ/ลิงก์ YT, Spotify, SoundCloud)")
@app_commands.describe(query="ชื่อเพลงหรือลิงก์เพลง")
async def play(interaction: discord.Interaction, query: str):
    await interaction.response.defer(ephemeral=True, thinking=True)
    member = interaction.user
    if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
        return await interaction.followup.send(embed=error_embed("เข้าห้องเสียงก่อน แล้วค่อยสั่ง"), ephemeral=True)
    vc, err = await ensure_voice(member)
    if err:
        return await interaction.followup.send(embed=error_embed(err), ephemeral=True)
    st = get_state(interaction.guild.id)
    st["text"] = interaction.channel
    first = st["current"] is None and not st["queue"] and not vc.is_playing()
    track, bridge, err = await enqueue(interaction.guild, member, query)
    if err:
        return await interaction.followup.send(embed=error_embed(err), ephemeral=True)
    await interaction.followup.send(embed=queued_ephemeral(track, len(st["queue"]), bridge), ephemeral=True)
    if first:
        await play_next(interaction.guild)


@bot.tree.command(name="panel", description=f"{TEDDY} แผงควบคุมเพลง Love Teddy")
async def panel(interaction: discord.Interaction):
    await interaction.response.send_message(embed=panel_embed(get_state(interaction.guild.id)), view=MusicView())


@bot.tree.command(name="nowplaying", description="เพลงที่เล่นอยู่")
async def nowplaying(interaction: discord.Interaction):
    st = get_state(interaction.guild.id)
    if not st.get("current"):
        return await interaction.response.send_message(embed=error_embed("ยังไม่ได้เล่นอะไรอยู่"), ephemeral=True)
    await interaction.response.send_message(embed=song_embed(st["current"], st), ephemeral=True)


@bot.tree.command(name="queue", description="ดูคิวเพลง")
async def queue(interaction: discord.Interaction):
    await interaction.response.send_message(embed=queue_embed(get_state(interaction.guild.id)), ephemeral=True)


@bot.tree.command(name="skip", description="ข้ามเพลง")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc or not vc.is_playing():
        return await interaction.response.send_message("ไม่มีเพลงเล่นอยู่", ephemeral=True)
    vc.stop()
    await interaction.response.send_message("⏭️ ข้ามแล้ว", ephemeral=True)


@bot.tree.command(name="stop", description="หยุด + ล้างคิว")
async def stop(interaction: discord.Interaction):
    st = get_state(interaction.guild.id)
    st["queue"].clear()
    st["current"] = None
    vc = interaction.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
    await interaction.response.send_message("⏹️ หยุด + ล้างคิวแล้ว", ephemeral=True)


@bot.tree.command(name="pause", description="พักเพลง")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        return await interaction.response.send_message("⏸️ พักก่อน", ephemeral=True)
    await interaction.response.send_message("ไม่มีอะไรให้พัก", ephemeral=True)


@bot.tree.command(name="resume", description="เล่นต่อ")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        return await interaction.response.send_message("▶️ ต่อแล้ว", ephemeral=True)
    await interaction.response.send_message("ไม่มีอะไรพักอยู่", ephemeral=True)


@bot.tree.command(name="loop", description="ตั้งลูปเพลง")
@app_commands.describe(mode="off = ปิด / track = เพลงเดียว / queue = ทั้งคิว")
@app_commands.choices(mode=[app_commands.Choice(name="ปิด", value="off"), app_commands.Choice(name="เพลงเดียว", value="track"), app_commands.Choice(name="ทั้งคิว", value="queue")])
async def loop(interaction: discord.Interaction, mode: str):
    get_state(interaction.guild.id)["loop"] = mode
    await interaction.response.send_message(f"🔁 ลูป: **{loop_label(mode)}**", ephemeral=True)


@bot.tree.command(name="shuffle", description="สลับคิวแบบสุ่ม")
async def shuffle(interaction: discord.Interaction):
    st = get_state(interaction.guild.id)
    if len(st["queue"]) < 2:
        return await interaction.response.send_message("คิวน้อยไป", ephemeral=True)
    random.shuffle(st["queue"])
    await interaction.response.send_message(embed=queue_embed(st), ephemeral=True)


@bot.tree.command(name="volume", description="ปรับเสียง 0-150")
@app_commands.describe(level="0-150 (ปกติ 80)")
async def volume(interaction: discord.Interaction, level: int):
    level = max(0, min(150, level))
    get_state(interaction.guild.id)["volume"] = level
    apply_volume(interaction.guild, level)
    await interaction.response.send_message(f"🔊 เสียง **{level}%**", ephemeral=True)


@bot.tree.command(name="remove", description="ลบเพลงออกจากคิว")
@app_commands.describe(index="เลขคิวที่เห็นใน /queue (เริ่มที่ 1)")
async def remove(interaction: discord.Interaction, index: int):
    st = get_state(interaction.guild.id)
    if index < 1 or index > len(st["queue"]):
        return await interaction.response.send_message("เลขคิวไม่ถูก", ephemeral=True)
    t = st["queue"].pop(index - 1)
    await interaction.response.send_message(f"🗑️ ลบ **{t['title']}** แล้ว", ephemeral=True)


@bot.tree.command(name="leave", description="ให้บอทออกห้องเสียง")
async def leave(interaction: discord.Interaction):
    st = get_state(interaction.guild.id)
    st["queue"].clear()
    st["current"] = None
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect()
        return await interaction.response.send_message(f"👋 บ๊ายบาย {TEDDY}{HEART}", ephemeral=True)
    await interaction.response.send_message("บอทไม่ได้อยู่ในห้อง", ephemeral=True)


@bot.event
async def on_ready():
    bot.add_view(MusicView())
    bot.add_view(MiniView())
    try:
        await bot.tree.sync()
    except Exception as e:
        print("[sync]", e)
    print(f"✅ {bot.user} | Love Teddy พร้อม {HEART} (source: {SEARCH_SOURCE}, yt-api: {'on' if YT_API_KEY else 'off'})")


def start_health_server():
    port = int(os.getenv("PORT", "0") or 0)
    if not port:
        return
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Teddy is running")
        def log_message(self, *a):
            pass

    threading.Thread(target=lambda: HTTPServer(("0.0.0.0", port), H).serve_forever(), daemon=True).start()


if __name__ == "__main__":
    start_health_server()
    bot.run(TOKEN)
