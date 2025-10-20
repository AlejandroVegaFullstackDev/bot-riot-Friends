\
import os
import json
import logging
import time
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
SYNC_ON_START = os.getenv("SYNC_ON_START", "1") == "1"
SYNC_COOLDOWN_MIN = int(os.getenv("SYNC_COOLDOWN_MIN", "3"))
_LAST_SYNC_FILE = ".last_command_sync"
CONFIG_PATH = "data/config.json"

# ---- Intents ----
intents = discord.Intents.default()
intents.members = True           # necesario para eventos de roles y /user-info
intents.message_content = True   # necesario para leer mensajes en automations

# ---- Bot ----
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.config = {}
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fp:
                self.config = json.load(fp)
        except Exception as e:
            logging.warning("[Config] No se pudo cargar %s: %s", CONFIG_PATH, e)

    async def setup_hook(self):
        # Cargar cogs
        for ext in (
            "cogs.utility",
            "cogs.admin",
            "cogs.fun",
            "cogs.poll",
            "cogs.automations",
            "cogs.tempvoice",
            "cogs.setup",
            "cogs.tickets",
            "cogs.selfroles",
            "cogs.moderation",
            "cogs.syncfix",
            "cogs.ai",
            "cogs.iconos",
            "cogs.music_slash",
            "cogs.publish_icons_panel",
            "cogs.personalvoice",
        ):
            try:
                await self.load_extension(ext)
                print(f"[OK] Cargado {ext}")
            except Exception as e:
                print(f"[WARN] No se pudo cargar {ext}: {e}")

        # Sincronizar slash commands (solo guild, con cooldown)
        try:
            if not SYNC_ON_START:
                print("[INFO] SYNC_ON_START=0 → no se sincroniza en el arranque.")
                return

            now = time.time()
            last = 0.0
            if os.path.exists(_LAST_SYNC_FILE):
                try:
                    with open(_LAST_SYNC_FILE, "r", encoding="utf-8") as fp:
                        last = float(fp.read().strip() or "0")
                except Exception:
                    last = 0.0

            if now - last < SYNC_COOLDOWN_MIN * 60:
                print(f"[INFO] Saltando sync (cooldown {SYNC_COOLDOWN_MIN} min).")
                return

            if GUILD_ID and GUILD_ID.isdigit():
                guild = discord.Object(id=int(GUILD_ID))
                await self.tree.sync(guild=guild)
                print(f"[OK] Comandos sincronizados con el servidor {GUILD_ID}.")
            else:
                await self.tree.sync()
                print("[OK] Comandos globales sincronizados (puede tardar en aparecer).")

            with open(_LAST_SYNC_FILE, "w", encoding="utf-8") as fp:
                fp.write(str(now))
        except Exception as e:
            print(f"[ERROR] Falló la sincronización de comandos: {e}")

bot = MyBot()

@bot.event
async def on_ready():
    print(f"Conectado como {bot.user} (id: {bot.user.id})")

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Falta DISCORD_TOKEN en .env")
    bot.run(TOKEN)
