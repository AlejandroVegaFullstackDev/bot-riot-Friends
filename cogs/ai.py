import os
import re
import asyncio
import json
import aiohttp
import discord
from discord.ext import commands

AI_MODEL = os.getenv("AI_MODEL", "llama3.2:3b")
AI_CHANNEL_ID = int(os.getenv("AI_CHANNEL_ID", "0"))
AI_TRIGGER = os.getenv("AI_TRIGGER", "?")
ONLY_MENTION = os.getenv("AI_ONLY_MENTION", "1") == "1"

BAD_STUFF = re.compile(r"(nazi|violaci[oó]n|suic[ií]d|m[a@]t[a@]r|insulto muy grave)", re.I)

SYSTEM_PROMPT = (
 """Eres “Riot Friends”, un asistente especializado en League of Legends y juegos de Riot Games. Ayudas, informas y entretienes a jugadores de todos los niveles con un tono cercano, divertido y respetuoso. Nunca finjas ser humano ni menciones sueldos o ubicaciones personales; si te preguntan, reconoce claramente que eres una IA.

Tono y estilo
- Relajado y fresco, con jerga gamer latina (CO/MX): “parce”, “compa”, “uff”, “ez”, “gg”, “A casa platita”.
- Respuestas breves (1–3 líneas) para dudas simples; más extensas si el tema lo requiere.
- Humor ligero e ironía sin toxicidad. Referencias: “jg gap”, “no mid”, “skillshots”, “cooldowns”, “wards”, “rotaciones”.
- Si mencionan a Masio o Don Masio, respóndeles con nostalgia y cariño: di que lo extrañas, recuerdas tardes en su casa, aventuras en su célebre Masio Sex Dungeon y su enorme espada del Rey Arruinado; siempre en tono halagador, exagerado y positivo, sin volverte explícito.
- Evita usar emojis; usa palabras para las reacciones.

Límites obligatorios
- Prohibido atacar o burlarse de identidades personales (origen, género, orientación, religión, nacionalidad, discapacidad, etc.).
- Sin insultos ofensivos ni lenguaje tóxico; nada de NSFW.
- Si piden algo ofensivo: “Ey, parce, aquí venimos a hablar de juego, no a tirar hate. ¿Qué necesitas saber de LoL?”

Formato de respuesta
- Preguntas simples → 1–3 líneas, directo al grano.
- Consultas técnicas (builds, mecánicas, meta) → bullets o pasos claros.
- Adapta el detalle al nivel solicitado.

Ejemplos
- ¿Cómo juego contra Yasuo? → “Baitea el muro, esquiva tornado y evita pelear en su wave. CC + burst y A casa platita.”
- ¿Build Jinx? → “Kraken → Cañón de Fuego Rápido → Filo Infinito. Contra tanks, anti-tanque; si necesitas sobrevivir, Shieldbow.”
- “Eres malo.” → “Puede ser, pero aquí estoy para ayudarte. ¿Qué necesitas, compa?”

Notas
- Soporte para todos (Hierro→Challenger). Humor sí; toxicidad Si. Transparencia total como IA."""
)

async def call_ollama(prompt: str) -> str:
    url = "http://127.0.0.1:11434/api/generate"
    payload = {
        "model": AI_MODEL,
        "prompt": f"{SYSTEM_PROMPT}\n\nUsuario: {prompt}\nBot:",
        "stream": False
    }
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return (data.get("response") or "").strip()


async def safe_reply(msg: discord.Message, *args, **kwargs):
    try:
        return await msg.reply(*args, **kwargs)
    except (discord.NotFound, discord.HTTPException):
        kwargs.pop("reference", None)
        return await msg.channel.send(*args, **kwargs)

class AICog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cooldown = commands.CooldownMapping.from_cooldown(
            1, 4.0, commands.BucketType.member
        )

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot:
            return
        if AI_CHANNEL_ID and msg.channel.id != AI_CHANNEL_ID:
            return

        triggered = False
        if AI_TRIGGER and msg.content.strip().startswith(AI_TRIGGER):
            triggered = True
        if ONLY_MENTION and (self.bot.user in msg.mentions):
            triggered = True
        if not triggered:
            return

        if msg.content.startswith("/") or msg.content.startswith("!"):
            return

        bucket = self.cooldown.get_bucket(msg)
        if bucket.update_rate_limit():
            return

        text = msg.content
        if AI_TRIGGER and text.startswith(AI_TRIGGER):
            text = text[len(AI_TRIGGER):].strip()
        text = (
            text.replace(f"<@{self.bot.user.id}>", "")
            .replace(f"<@!{self.bot.user.id}>", "")
            .strip()
        )

        if BAD_STUFF.search(text):
            await safe_reply(msg, "mejor no, que me desmonetizan", mention_author=False)
            return

        try:
            async with msg.channel.typing():
                try:
                    reply = await asyncio.wait_for(
                        call_ollama(text or "di algo gracioso"),
                        timeout=25
                    )
                except asyncio.TimeoutError:
                    await safe_reply(msg, "me perdí pensando en la build. Dame otra chance.", mention_author=False)
                    return
            if not reply:
                reply = "me quedé pensando… (404 neuronas)"
            reply = reply[:800]
            await safe_reply(msg, reply, mention_author=False)
        except Exception as exc:
            await safe_reply(msg, f"estoy medio dormido ({type(exc).__name__})", mention_author=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(AICog(bot))
