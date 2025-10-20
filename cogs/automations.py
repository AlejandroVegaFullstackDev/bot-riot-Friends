\
import os
import json
import re
import discord

CONFIG_PATH = "data/config.json"

def load_cfg():
    try:
        import json
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}
from discord.ext import commands

def get_int_id(name: str, default=None):
    val = os.getenv(name)
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default

def get_list_ids(name: str):
    val = os.getenv(name)
    if not val:
        return []
    try:
        data = json.loads(val)
        return [int(x) for x in data]
    except Exception:
        return []

CFG = load_cfg()
BAD_BEHAVIOR_ROLE_ID = CFG.get("bad_behavior_role_id") or get_int_id("BAD_BEHAVIOR_ROLE_ID", 0)
PROTECTED_ROLE_IDS = set(CFG.get("protected_role_ids", []) or get_list_ids("PROTECTED_ROLE_IDS"))
PRESENTATIONS_CHANNEL_ID = CFG.get("presentations_channel_id") or get_int_id("PRESENTATIONS_CHANNEL_ID", 0)
BOOSTER_ROLE_ID = CFG.get("booster_role_id") or get_int_id("BOOSTER_ROLE_ID", 0)
BOOST_PERK_ROLE_IDS = set(CFG.get("boost_perk_role_ids", []) or get_list_ids("BOOST_PERK_ROLE_IDS"))
STAFF_CHANNEL_ID = CFG.get("staff_channel_id") or get_int_id("STAFF_CHANNEL_ID", 0)
GENERAL_CHANNEL_ID = CFG.get("general_channel_id") or get_int_id("GENERAL_CHANNEL_ID", 0)

# Emojis list
try:
    PRESENTATION_REACT_EMOJIS = CFG.get("presentation_react_emojis") or json.loads(os.getenv("PRESENTATION_REACT_EMOJIS") or '["❤️","❌"]')
except Exception:
    PRESENTATION_REACT_EMOJIS = ["❤️","❌"]

TRIGGER_PHRASES = {"down", "server en decadencia"}

class Automations(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _safe_add_reaction(self, message: discord.Message, em: str) -> bool:
        try:
            await message.add_reaction(em)
            return True
        except Exception:
            try:
                pe = discord.PartialEmoji.from_str(em)
                await message.add_reaction(pe)
                return True
            except Exception:
                return False

    # --- Handler "Down" y Presentaciones ---
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        content = message.content.strip().lower()

        # Handler "Down"
        if content in TRIGGER_PHRASES and BAD_BEHAVIOR_ROLE_ID:
            author: discord.Member = message.author  # type: ignore
            author_role_ids = {r.id for r in author.roles}
            # Si NO tiene ninguno de los roles protegidos → aplicar rol de mal comportamiento
            if PROTECTED_ROLE_IDS and author_role_ids.isdisjoint(PROTECTED_ROLE_IDS):
                role = message.guild.get_role(BAD_BEHAVIOR_ROLE_ID)
                if role and role not in author.roles:
                    try:
                        await author.add_roles(role, reason="Handler Down: palabra prohibida.")
                    except discord.Forbidden:
                        await message.channel.send("No tengo permisos para asignar roles.", delete_after=10)

        if PRESENTATIONS_CHANNEL_ID:
            channel_id = message.channel.id
            try:
                if isinstance(message.channel, discord.Thread) and message.channel.parent:
                    channel_id = message.channel.parent.id
            except Exception:
                pass

            if channel_id == PRESENTATIONS_CHANNEL_ID:
                for em in PRESENTATION_REACT_EMOJIS:
                    await self._safe_add_reaction(message, em)

        try:
            await self.bot.process_commands(message)
        except Exception:
            pass

    # --- Boost Add / Loss ---
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.guild != after.guild:
            return

        b_roles = {r.id for r in before.roles}
        a_roles = {r.id for r in after.roles}

        if BOOSTER_ROLE_ID:
            lost = BOOSTER_ROLE_ID in b_roles and BOOSTER_ROLE_ID not in a_roles
            gained = BOOSTER_ROLE_ID not in b_roles and BOOSTER_ROLE_ID in a_roles

            # Boost perdido → quitar perks + avisar staff
            if lost:
                to_remove = [after.guild.get_role(rid) for rid in BOOST_PERK_ROLE_IDS]
                to_remove = [r for r in to_remove if r and r in after.roles]
                if to_remove:
                    try:
                        await after.remove_roles(*to_remove, reason="Perdió Nitro Boost")
                    except discord.Forbidden:
                        pass
                if STAFF_CHANNEL_ID:
                    ch = after.guild.get_channel(STAFF_CHANNEL_ID)
                    if isinstance(ch, discord.TextChannel):
                        await ch.send(f"⚠️ {after.mention} perdió el rol de **Server Booster**. Se retiraron perks.")

            # Boost ganado → mensaje en general con beneficios
            if gained and GENERAL_CHANNEL_ID:
                ch = after.guild.get_channel(GENERAL_CHANNEL_ID)
                if isinstance(ch, discord.TextChannel):
                    embed = discord.Embed(
                        title="¡Gracias por tu Boost! 💜",
                        description=(
                            "Estos son algunos beneficios:\n"
                            "• Rol especial y color personalizado\n"
                            "• Acceso a canales y stickers exclusivos\n"
                            "• Mayores límites de subida en el servidor\n"
                            "• Prioridad en solicitudes y soporte\n"
                        )
                    )
                    embed.set_footer(text="Configura el texto desde el código si deseas.")
                    await ch.send(content=after.mention, embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Automations(bot))
