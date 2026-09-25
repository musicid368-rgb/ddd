# 🧸💗 Love Teddy Music Bot (Python)
# ธีมชมพู + embed + ปุ่มกดทั้งหมด
# คำสั่ง: /play /panel /nowplaying /queue /skip /stop /pause /resume /loop /shuffle /volume /remove /leave
# รัน: pip install -r requirements.txt แล้ว python bot.py (ต้องมี FFmpeg)

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

if not TOKEN:
    print("❌ ไม่เจอ DISCORD_TOKEN — ก็อป .env.example เป็น .env ก่อน")
    raise SystemExit(1)

# ---------- Love Teddy theme ----------
PINK = 0xFF9EBB
PINK_DARK = 0xFF6FA5
TEDDY = "🧸"
HEART = "💗"
RIBBON = "🎀"
PANEL_TITLE = f"{TEDDY}{HEART} Love Teddy DJ {HEART}{TEDDY}"
FOOTER = f"{RIBBON} Love Teddy • ขอเพลงได้เลย {HEART}"

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
}
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
    return {"off": "ปิด", "track": "🔂 เพลงเดียว", "queue": "🔁 ทั้งคิว"}.get(mode, mode)


def np_embed(track: dict, st: dict) -> discord.Embed:
    e = discord.Embed(title=f"{TEDDY}{HEART} กำลังเล่น", description=f"**{track['title']}**", color=PINK)
    if track.get("webpage"):
        e.url = track["webpage"]
    e.add_field(name="🎤 ศิลปิน/ช่อง", value=str(track.get("author", "—"))[:50], inline=True)
    e.add_field(name="⏱️ ยาว", value=fmt_dur(track.get("duration")), inline=True)
    e.add_field(name="🔁 ลูป", value=loop_label(st.get("loop", "off")), inline=True)
    e.add_field(name=f"{HEART} ขอโดย", value=track.get("by_mention", track.get("by", "—")), inline=True)
    e.add_field(name="🔊 เสียง", value=f"{st.get('volume', 80)}%", inline=True)
    if track.get("thumbnail"):
        e.set_thumbnail(url=track["thumbnail"])
    e.set_footer(text=FOOTER)
    return e


def queued_embed(track: dict, pos: int) -> discord.Embed:
    e = discord.Embed(title=f"{RIBBON} เพิ่มลงคิวแล้ว", description=f"**{track['title']}**", color=PINK_DARK)
    e.add_field(name="คิวที่", value=f"#{pos}", inline=True)
    e.add_field(name="⏱️ ยาว", value=fmt_dur(track.get("duration")), inline=True)
    e.add_field(name=f"{HEART} ขอโดย", value=track.get("by_mention", "—"), inline=True)
    if track.get("thumbnail"):
        e.set_thumbnail(url=track["thumbnail"])
    e.set_footer(text=FOOTER)
    return e


def queue_embed(st: dict) -> discord.Embed:
    e = discord.Embed(title=f"{TEDDY} คิวเพลง {HEART}", color=PINK)
    if st.get("current"):
        c = st["current"]
        e.add_field(name="▶️ กำลังเล่น", value=f"**{c['title']}** ({fmt_dur(c.get('duration'))})", inline=False)
    if st["queue"]:
        lines = [f"`{i}.` {t['title']} ({fmt_dur(t.get('duration'))})" for i, t in enumerate(st["queue"][:15], 1)]
        e.add_field(name=f"📋 ต่อคิว ({len(st['queue'])})", value="\n".join(lines)[:4000], inline=False)
    else:
        e.add_field(name="📋 ต่อคิว", value="ว่างแล้ว เติมเพลงด้วย /play หรือปุ่ม ➕ ได้เลย", inline=False)
    e.add_field(name="🔁 ลูป", value=loop_label(st.get("loop", "off")), inline=True)
    e.add_field(name="🔊 เสียง", value=f"{st.get('volume', 80)}%", inline=True)
    e.set_footer(text=FOOTER)
    return e


def panel_embed(st: dict) -> discord.Embed:
    cur = f"**{st['current']['title']}**" if st.get("current") else "ยังไม่มีเพลง — กด ➕ ขอเพลงได้เลย"
    e = discord.Embed(title=PANEL_TITLE, description=f"{HEART} ห้องเพลงตีมเท็ดดี้ กดปุ่มเอาได้ทุกอย่าง\n\n🎧 ตอนนี้: {cur}", color=PINK)
    e.add_field(name="📋 คิว", value=f"{len(st['queue'])} เพลง", inline=True)
    e.add_field(name="🔁 ลูป", value=loop_label(st.get("loop", "off")), inline=True)
    e.add_field(name="🔊 เสียง", value=f"{st.get('volume', 80)}%", inline=True)
    e.add_field(
        name=f"{RIBBON} วิธีใช้",
        value="➕ ขอเพลง = พิมพ์ชื่อเพลงในกล่อง\n⏸️ พัก/เล่นต่อ • ⏭️ ข้าม • ⏹️ หยุดล้างคิว\n🔁 วนลูป • 🔀 สลับคิว • 📋 ดูคิว",
        inline=False,
    )
    e.set_footer(text=FOOTER + " • กด /panel ใหม่ถ้าปุ่มกดไม่ติดหลังรีบอท")
    return e


def error_embed(msg: str) -> discord.Embed:
    return discord.Embed(title=f"{TEDDY} อุ๊บส์", description=msg, color=0xFF5555)


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
    q = query.strip()
    if SPOTIFY_RE.search(q):
        q = spotify_to_search(q)
    if not URL_RE.match(q):
        q = f"{SEARCH_SOURCE}1:{q}"
    with YoutubeDL(dict(YDL_OPTS)) as ydl:
        info = ydl.extract_info(q, download=False)
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
    if not vc:
        st["current"] = None
        return
    # จัดการ loop ก่อนดึงเพลงใหม่
    prev = st.get("current")
    if prev:
        if st.get("loop") == "track":
            st["queue"].insert(0, prev)
        elif st.get("loop") == "queue":
            st["queue"].append(prev)
    if not st["queue"]:
        st["current"] = None
        if st["text"]:
            try:
                await st["text"].send(embed=discord.Embed(title=f"{TEDDY} คิวหมดแล้ว", description=f"เติมเพลงด้วย /play หรือปุ่ม ➕ ได้เลย {HEART}", color=PINK))
            except Exception:
                pass
        return
    track = st["queue"].pop(0)
    st["current"] = track
    try:
        vc.play(make_source(track["audio_url"], st.get("volume", 80)),
                after=lambda e: asyncio.run_coroutine_threadsafe(play_next(guild, e), bot.loop))
    except Exception as e:
        print("[ffmpeg]", e)
        if st["text"]:
            await st["text"].send(embed=error_embed(f"เปิดไม่ได้ (ลืมลง FFmpeg?): {e}"))
        return
    if st["text"]:
        try:
            await st["text"].send(embed=np_embed(track, st), view=MusicView())
        except Exception:
            pass


async def ensure_voice(member: discord.Member):
    if not member.voice or not member.voice.channel:
        return None, "❌ เข้าห้องเสียงก่อน แล้วค่อยสั่ง"
    vc = member.guild.voice_client
    if vc and vc.channel != member.voice.channel:
        try:
            await vc.move_to(member.voice.channel)
        except Exception:
            return None, "❌ บอทอยู่อีกห้องนึงแล้ว"
    if not vc:
        try:
            vc = await member.voice.channel.connect()
        except Exception as e:
            return None, f"❌ เข้าห้องเสียงไม่ได้: {e}"
    return vc, None


async def enqueue(guild: discord.Guild, user: discord.User | discord.Member, query: str) -> tuple[dict | None, str | None]:
    try:
        info = await extract(query)
    except Exception as e:
        msg = str(e)
        if "confirm you are not a bot" in msg or "Sign in to confirm" in msg or "403" in msg:
            return None, "❌ YouTube บล็อก IP โฮสต์นี้\n✅ ลองชื่อเพลงเฉยๆ / ลิงก์ SoundCloud / Spotify แทน"
        return None, f"⚠️ หาเพลงไม่เจอ: {msg[:300]}"
    if not info.get("url"):
        return None, "⚠️ ดึงเสียงไม่ได้ ลองลิงก์อื่น"
    track = {
        "title": info.get("title", "Unknown")[:100],
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
    return track, None


# ---------- ปุ่ม + กล่องขอเพลง ----------

class SongModal(discord.ui.Modal, title=f"{TEDDY} ขอเพลง {HEART}"):
    song = discord.ui.TextInput(label="ชื่อเพลง / ลิงก์", placeholder="เช่นicula... พิมพ์ชื่อเพลงหรือแปะลิงก์ Spotify", max_length=200)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=False)
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice:
            return await interaction.followup.send("❌ เข้าห้องเสียงก่อนน้า", ephemeral=True)
        vc, err = await ensure_voice(member)
        if err:
            return await interaction.followup.send(err, ephemeral=True)
        st = get_state(interaction.guild.id)
        st["text"] = interaction.channel
        track, err = await enqueue(interaction.guild, member, self.song.value)
        if err:
            return await interaction.followup.send(embed=error_embed(err))
        pos = len(st["queue"])
        await interaction.followup.send(embed=queued_embed(track, pos), view=MusicView())
        if not vc.is_playing() and not vc.is_paused() and st["current"] is None and len(st["queue"]) == 1:
            await play_next(interaction.guild)


class MusicView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # ปุ่มไม่หมดอายุ (แต่รีบอทต้องกด /panel ใหม่)

    @discord.ui.button(label="ขอเพลง", emoji="➕", style=discord.ButtonStyle.primary, custom_id="teddy:add")
    async def add(self, interaction: discord.Interaction, _btn: discord.ui.Button):
        await interaction.response.send_modal(SongModal())

    @discord.ui.button(label="พัก/ต่อ", emoji="⏸️", style=discord.ButtonStyle.secondary, custom_id="teddy:pause")
    async def pause(self, interaction: discord.Interaction, _btn: discord.ui.Button):
        vc = interaction.guild.voice_client
        if not vc or (not vc.is_playing() and not vc.is_paused()):
            return await interaction.response.send_message("❌ ไม่มีเพลงเล่นอยู่", ephemeral=True)
        if vc.is_playing():
            vc.pause()
            await interaction.response.send_message(f"⏸️ พักก่อน {TEDDY}", ephemeral=False)
        else:
            vc.resume()
            await interaction.response.send_message(f"▶️ ต่อแล้ว {HEART}", ephemeral=False)

    @discord.ui.button(label="ข้าม", emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="teddy:skip")
    async def skip(self, interaction: discord.Interaction, _btn: discord.ui.Button):
        vc = interaction.guild.voice_client
        if not vc or not vc.is_playing():
            return await interaction.response.send_message("❌ ไม่มีเพลงให้ข้าม", ephemeral=True)
        vc.stop()
        await interaction.response.send_message(f"⏭️ ข้ามแล้ว {HEART}")

    @discord.ui.button(label="หยุด", emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="teddy:stop")
    async def stop(self, interaction: discord.Interaction, _btn: discord.ui.Button):
        st = get_state(interaction.guild.id)
        st["queue"].clear()
        st["current"] = None
        st["loop"] = "off"
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
        await interaction.response.send_message(f"⏹️ หยุด + ล้างคิวแล้ว {TEDDY}")

    @discord.ui.button(label="ลูป", emoji="🔁", style=discord.ButtonStyle.secondary, custom_id="teddy:loop", row=1)
    async def loop(self, interaction: discord.Interaction, _btn: discord.ui.Button):
        st = get_state(interaction.guild.id)
        nxt = {"off": "track", "track": "queue", "queue": "off"}[st.get("loop", "off")]
        st["loop"] = nxt
        await interaction.response.send_message(f"🔁 ลูป: **{loop_label(nxt)}** {HEART}")

    @discord.ui.button(label="สลับคิว", emoji="🔀", style=discord.ButtonStyle.secondary, custom_id="teddy:shuffle", row=1)
    async def shuffle(self, interaction: discord.Interaction, _btn: discord.ui.Button):
        st = get_state(interaction.guild.id)
        if len(st["queue"]) < 2:
            return await interaction.response.send_message("❌ คิวน้อยไป สลับไม่ได้", ephemeral=True)
        random.shuffle(st["queue"])
        await interaction.response.send_message(f"🔀 สลับคิวแล้ว ({len(st['queue'])} เพลง) {TEDDY}")

    @discord.ui.button(label="คิว", emoji="📋", style=discord.ButtonStyle.secondary, custom_id="teddy:queue", row=1)
    async def showq(self, interaction: discord.Interaction, _btn: discord.ui.Button):
        await interaction.response.send_message(embed=queue_embed(get_state(interaction.guild.id)), ephemeral=True)

    @discord.ui.button(label="-", emoji="🔉", style=discord.ButtonStyle.secondary, custom_id="teddy:vold", row=1)
    async def vold(self, interaction: discord.Interaction, _btn: discord.ui.Button):
        st = get_state(interaction.guild.id)
        st["volume"] = max(0, st.get("volume", 80) - 10)
        apply_volume(interaction.guild, st["volume"])
        await interaction.response.send_message(f"🔉 เสียง {st['volume']}%", ephemeral=True)

    @discord.ui.button(label="+", emoji="🔊", style=discord.ButtonStyle.secondary, custom_id="teddy:volu", row=1)
    async def volu(self, interaction: discord.Interaction, _btn: discord.ui.Button):
        st = get_state(interaction.guild.id)
        st["volume"] = min(150, st.get("volume", 80) + 10)
        apply_volume(interaction.guild, st["volume"])
        await interaction.response.send_message(f"🔊 เสียง {st['volume']}%", ephemeral=True)


# ---------- Slash commands (embed ทั้งหมด) ----------

@bot.tree.command(name="play", description=f"{TEDDY} เปิดเพลง (ชื่อ/ลิงก์ YT, Spotify, SoundCloud)")
@app_commands.describe(query="ชื่อเพลงหรือลิงก์เพลง")
async def play(interaction: discord.Interaction, query: str):
    await interaction.response.defer(thinking=True)
    member = interaction.user
    if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
        return await interaction.followup.send(embed=error_embed("เข้าห้องเสียงก่อน แล้วค่อยสั่ง"))
    if YOUTUBE_RE.search(query):
        await interaction.followup.send(f"⚠️ {TEDDY} YouTube บนของฟรีโดนบล็อกบ่อย ถ้าโหลดนานลองชื่อเพลงเฉยๆ / ลิงก์ SoundCloud แทน\n⏳ กำลังโหลด...")
    vc, err = await ensure_voice(member)
    if err:
        return await interaction.followup.send(embed=error_embed(err))
    st = get_state(interaction.guild.id)
    st["text"] = interaction.channel
    first = st["current"] is None and not st["queue"] and not vc.is_playing()
    track, err = await enqueue(interaction.guild, member, query)
    if err:
        return await interaction.followup.send(embed=error_embed(err))
    if first:
        await interaction.followup.send(embed=queued_embed(track, 1), view=MusicView())
        await play_next(interaction.guild)
    else:
        await interaction.followup.send(embed=queued_embed(track, len(st["queue"])), view=MusicView())


@bot.tree.command(name="panel", description=f"{TEDDY} แผงควบคุมเพลง Love Teddy")
async def panel(interaction: discord.Interaction):
    st = get_state(interaction.guild.id)
    await interaction.response.send_message(embed=panel_embed(st), view=MusicView())


@bot.tree.command(name="nowplaying", description="เพลงที่เล่นอยู่ (embed)")
async def nowplaying(interaction: discord.Interaction):
    st = get_state(interaction.guild.id)
    if not st.get("current"):
        return await interaction.response.send_message(embed=error_embed("ยังไม่ได้เล่นอะไรอยู่"), ephemeral=True)
    await interaction.response.send_message(embed=np_embed(st["current"], st), view=MusicView())


@bot.tree.command(name="queue", description="ดูคิวเพลง (embed)")
async def queue(interaction: discord.Interaction):
    await interaction.response.send_message(embed=queue_embed(get_state(interaction.guild.id)))


@bot.tree.command(name="skip", description="ข้ามเพลง")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc or not vc.is_playing():
        return await interaction.response.send_message("❌ ไม่มีเพลงเล่นอยู่", ephemeral=True)
    vc.stop()
    await interaction.response.send_message(f"⏭️ ข้ามแล้ว {HEART}")


@bot.tree.command(name="stop", description="หยุด + ล้างคิว")
async def stop(interaction: discord.Interaction):
    st = get_state(interaction.guild.id)
    st["queue"].clear()
    st["current"] = None
    vc = interaction.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
    await interaction.response.send_message(f"⏹️ หยุด + ล้างคิวแล้ว {TEDDY}")


@bot.tree.command(name="pause", description="พักเพลง")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        return await interaction.response.send_message(f"⏸️ พักก่อน {TEDDY}")
    await interaction.response.send_message("❌ ไม่มีอะไรให้พัก", ephemeral=True)


@bot.tree.command(name="resume", description="เล่นต่อ")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        return await interaction.response.send_message(f"▶️ ต่อแล้ว {HEART}")
    await interaction.response.send_message("❌ ไม่มีอะไรพักอยู่", ephemeral=True)


@bot.tree.command(name="loop", description="ตั้งลูปเพลง")
@app_commands.describe(mode="off = ปิด / track = เพลงเดียว / queue = ทั้งคิว")
@app_commands.choices(mode=[app_commands.Choice(name="ปิด", value="off"), app_commands.Choice(name="เพลงเดียว", value="track"), app_commands.Choice(name="ทั้งคิว", value="queue")])
async def loop(interaction: discord.Interaction, mode: str):
    get_state(interaction.guild.id)["loop"] = mode
    await interaction.response.send_message(f"🔁 ลูป: **{loop_label(mode)}** {HEART}")


@bot.tree.command(name="shuffle", description="สลับคิวแบบสุ่ม")
async def shuffle(interaction: discord.Interaction):
    st = get_state(interaction.guild.id)
    if len(st["queue"]) < 2:
        return await interaction.response.send_message("❌ คิวน้อยไป", ephemeral=True)
    random.shuffle(st["queue"])
    await interaction.response.send_message(embed=queue_embed(st))


@bot.tree.command(name="volume", description="ปรับเสียง 0-150")
@app_commands.describe(level="0-150 (ปกติ 80)")
async def volume(interaction: discord.Interaction, level: int):
    level = max(0, min(150, level))
    get_state(interaction.guild.id)["volume"] = level
    apply_volume(interaction.guild, level)
    await interaction.response.send_message(f"🔊 เสียง **{level}%** {HEART}")


@bot.tree.command(name="remove", description="ลบเพลงออกจากคิว")
@app_commands.describe(index="เลขคิวที่เห็นใน /queue (เริ่มที่ 1)")
async def remove(interaction: discord.Interaction, index: int):
    st = get_state(interaction.guild.id)
    if index < 1 or index > len(st["queue"]):
        return await interaction.response.send_message("❌ เลขคิวไม่ถูก", ephemeral=True)
    t = st["queue"].pop(index - 1)
    await interaction.response.send_message(f"🗑️ ลบ **{t['title']}** แล้ว")


@bot.tree.command(name="leave", description="ให้บอทออกห้องเสียง")
async def leave(interaction: discord.Interaction):
    st = get_state(interaction.guild.id)
    st["queue"].clear()
    st["current"] = None
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect()
        return await interaction.response.send_message(f"👋 บ๊ายบาย {TEDDY}{HEART}")
    await interaction.response.send_message("❌ บอทไม่ได้อยู่ในห้อง", ephemeral=True)


@bot.event
async def on_ready():
    bot.add_view(MusicView())  # ให้ปุ่มเก่ายังพอใช้ได้หลังรีบอท
    try:
        await bot.tree.sync()
    except Exception as e:
        print("[sync]", e)
    print(f"✅ {bot.user} | Love Teddy พร้อม {HEART} (source: {SEARCH_SOURCE})")


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
