\
import json
import re
import os
from typing import List, Optional
import discord
from discord.ext import commands
from discord import app_commands

CONFIG_PATH = "data/config.json"

def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception:
        return {}

def save_config(cfg):
    os.makedirs("data", exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def parse_role_list(guild: discord.Guild, text: str) -> List[int]:
    """
    Acepta menciones <@&id>, IDs o nombres separados por coma/espacio.
    """
    if not text:
        return []
    ids = set()
    # menciones <@&id>
    for m in re.findall(r"<@&(\d+)>", text):
        ids.add(int(m))
    # ids puros
    for m in re.findall(r"\b\d{15,20}\b", text):
        ids.add(int(m))
    # nombres (separados por coma)
    names = [t.strip() for t in re.split(r"[,\n]", text) if t.strip()]
    for name in names:
        role = discord.utils.find(lambda r: r.name.lower() == name.lower(), guild.roles)
        if role:
            ids.add(role.id)
    return list(ids)

def parse_channel_list(guild: discord.Guild, text: str) -> List[int]:
    if not text:
        return []
    ids = set()
    for m in re.findall(r"<#(\d+)>", text):
        ids.add(int(m))
    for m in re.findall(r"\b\d{15,20}\b", text):
        ids.add(int(m))
    names = [t.strip() for t in re.split(r"[,\n]", text) if t.strip()]
    for name in names:
        ch = discord.utils.find(lambda c: isinstance(c, discord.VoiceChannel) and c.name.lower() == name.lower(), guild.channels)
        if ch:
            ids.add(ch.id)
    return list(ids)

class Setup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="setup", description="Configura el bot con menciones/nombres en lugar de IDs")

    @group.command(name="automations", description="Configura roles y canales para automatizaciones")
    @app_commands.describe(
        bad_behavior_role="Rol para 'mal comportamiento' (mención o deja vacío)",
        protected_roles="Roles protegidos (menciones, IDs o nombres separados por coma)",
        presentations_channel="Canal #presentaciones",
        presentation_react_emojis="Emojis separados por coma (❤️,❌ o <:custom:123>)",
        booster_role="Rol de Server Booster",
        boost_perk_roles="Roles de beneficios a retirar (menciones/IDs/nombres separados por coma)",
        staff_channel="Canal staff para avisos de pérdida de boost",
        general_channel="Canal general para bienvenida de boost"
    )
    async def setup_automations(
        self,
        interaction: discord.Interaction,
        bad_behavior_role: Optional[discord.Role] = None,
        protected_roles: Optional[str] = None,
        presentations_channel: Optional[discord.TextChannel] = None,
        presentation_react_emojis: Optional[str] = None,
        booster_role: Optional[discord.Role] = None,
        boost_perk_roles: Optional[str] = None,
        staff_channel: Optional[discord.TextChannel] = None,
        general_channel: Optional[discord.TextChannel] = None
    ):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("Requiere permiso **Manage Server**.", ephemeral=True)
        cfg = load_config()
        g = interaction.guild

        if bad_behavior_role:
            cfg["bad_behavior_role_id"] = bad_behavior_role.id
        if protected_roles:
            cfg["protected_role_ids"] = parse_role_list(g, protected_roles)
        if presentations_channel:
            cfg["presentations_channel_id"] = presentations_channel.id
        if presentation_react_emojis:
            # parse por coma y strip
            cfg["presentation_react_emojis"] = [e.strip() for e in presentation_react_emojis.split(",") if e.strip()]
        if booster_role:
            cfg["booster_role_id"] = booster_role.id
        if boost_perk_roles:
            cfg["boost_perk_role_ids"] = parse_role_list(g, boost_perk_roles)
        if staff_channel:
            cfg["staff_channel_id"] = staff_channel.id
        if general_channel:
            cfg["general_channel_id"] = general_channel.id

        save_config(cfg)
        await interaction.response.send_message("✅ Configuración guardada.", ephemeral=True)

    @group.command(name="tempvoice", description="Configura hubs y opciones de canales de voz temporales")
    @app_commands.describe(
        hub_channels="Menciona canales de voz hub o pon IDs/nombres separados por coma",
        name_template="Plantilla del nombre (usa {index} y/o {username})",
        default_limit="Límite por defecto (0 = ilimitado)",
        keepalive_min="Minutos antes de borrar si queda vacío (0 = inmediato)",
        lock_min="Minutos de candado para reclamar propiedad"
    )
    async def setup_tempvoice(
        self,
        interaction: discord.Interaction,
        hub_channels: str,
        name_template: Optional[str] = None,
        default_limit: Optional[int] = None,
        keepalive_min: Optional[int] = None,
        lock_min: Optional[int] = None
    ):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("Requiere permiso **Manage Channels**.", ephemeral=True)
        cfg = load_config()
        g = interaction.guild
        cfg["tempvoice_hub_ids"] = parse_channel_list(g, hub_channels)
        if name_template:
            cfg["tempvoice_name_template"] = name_template
        if default_limit is not None:
            cfg["tempvoice_default_limit"] = int(default_limit)
        if keepalive_min is not None:
            cfg["tempvoice_keepalive_min"] = int(keepalive_min)
        if lock_min is not None:
            cfg["tempvoice_ownership_lock_min"] = int(lock_min)
        save_config(cfg)
        await interaction.response.send_message("✅ TempVoice configurado.", ephemeral=True)

    @group.command(name="show", description="Muestra la configuración actual")
    async def setup_show(self, interaction: discord.Interaction):
        cfg = load_config()
        if not cfg:
            return await interaction.response.send_message("No hay configuración guardada.", ephemeral=True)
        pretty = json.dumps(cfg, indent=2, ensure_ascii=False)
        await interaction.response.send_message(f"```json\n{pretty}\n```", ephemeral=True)

    @group.command(name="export-env", description="Genera un .env sugerido a partir de la configuración")
    async def export_env(self, interaction: discord.Interaction):
        cfg = load_config()
        gid = interaction.guild_id
        def arr(key, default=[]):
            return cfg.get(key, default)
        def get(key, default="000000000000000000"):
            return cfg.get(key, default)
        emojis = cfg.get("presentation_react_emojis", ["❤️","❌"])

        env_txt = f"""DISCORD_TOKEN=RELLENA_AQUI
GUILD_ID={gid}

BAD_BEHAVIOR_ROLE_ID={get("bad_behavior_role_id")}
PROTECTED_ROLE_IDS={arr("protected_role_ids", [])}

PRESENTATIONS_CHANNEL_ID={get("presentations_channel_id")}
PRESENTATION_REACT_EMOJIS={json.dumps(emojis, ensure_ascii=False)}

BOOSTER_ROLE_ID={get("booster_role_id")}
BOOST_PERK_ROLE_IDS={arr("boost_perk_role_ids", [])}
STAFF_CHANNEL_ID={get("staff_channel_id")}
GENERAL_CHANNEL_ID={get("general_channel_id")}

TEMPVOICE_HUB_IDS={arr("tempvoice_hub_ids", [])}
TEMPVOICE_NAME_TEMPLATE="{cfg.get("tempvoice_name_template", "[ 🎙 ] Duo {index}")}"
TEMPVOICE_DEFAULT_LIMIT={cfg.get("tempvoice_default_limit", 2)}
TEMPVOICE_KEEPALIVE_MIN={cfg.get("tempvoice_keepalive_min", 1)}
TEMPVOICE_OWNERSHIP_LOCK_MIN={cfg.get("tempvoice_ownership_lock_min", 10)}
"""
        file = discord.File(fp=discord.utils.MISSING, filename="env_sugerido.env")
        # Enviar como archivo
        await interaction.response.send_message(content="Aquí tienes el `.env` sugerido:", ephemeral=True)
        await interaction.followup.send(file=discord.File(fp=bytes(env_txt, "utf-8"), filename="env_sugerido.env"), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Setup(bot))
