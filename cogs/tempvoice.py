\
import os
import json
import asyncio
from datetime import datetime, timedelta
import discord
from discord.ext import commands
from discord import app_commands

DATA_PATH = "data/tempvoice.json"
CONFIG_PATH = "data/config.json"

def load_cfg():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def load_state():
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"channels": {}, "counters": {}}
    except Exception:
        return {"channels": {}, "counters": {}}

def save_state(state):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def env_list(name, default=None):
    default = default or []
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return [int(x) for x in json.loads(raw)]
    except Exception:
        return default

def env_int(name, default=0):
    try:
        return int(os.getenv(name) or default)
    except Exception:
        return default

CFG = load_cfg()
TEMP_HUB_IDS = set(CFG.get("tempvoice_hub_ids", []) or env_list("TEMPVOICE_HUB_IDS"))
NAME_TEMPLATE = CFG.get("tempvoice_name_template") or os.getenv("TEMPVOICE_NAME_TEMPLATE") or "[ 🎙 ] Room {index}"
DEFAULT_LIMIT = int(CFG.get("tempvoice_default_limit", env_int("TEMPVOICE_DEFAULT_LIMIT", 0)))
KEEPALIVE_MIN = int(CFG.get("tempvoice_keepalive_min", env_int("TEMPVOICE_KEEPALIVE_MIN", 1)))
OWNERSHIP_LOCK_MIN = int(CFG.get("tempvoice_ownership_lock_min", env_int("TEMPVOICE_OWNERSHIP_LOCK_MIN", 10)))
PERSONAL_HUB_ID = int(CFG.get("tempvoice_personal_hub_id", 0))
PERSONAL_NAME_TEMPLATE = CFG.get("tempvoice_personal_name_template", "[ 👤 ] {username}")
PERSONAL_DEFAULT_LIMIT = int(CFG.get("tempvoice_personal_default_limit", 0))
BOOSTER_ROLE_ID = int(CFG.get("booster_role_id") or os.getenv("BOOSTER_ROLE_ID") or 0)

class TempVoice(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.state = load_state()
        self.cleanup_tasks = {}  # channel_id -> task

    # ---------- helpers ----------
    def is_temp(self, channel: discord.VoiceChannel) -> bool:
        return str(channel.id) in self.state["channels"]

    def get_owner_id(self, channel_id: int) -> int | None:
        info = self.state["channels"].get(str(channel_id))
        return info.get("owner_id") if info else None

    def set_owner(self, channel_id: int, owner_id: int | None):
        if str(channel_id) in self.state["channels"]:
            self.state["channels"][str(channel_id)]["owner_id"] = owner_id
            if owner_id is None:
                self.state["channels"][str(channel_id)]["owner_left_at"] = datetime.utcnow().isoformat()
            else:
                self.state["channels"][str(channel_id)].pop("owner_left_at", None)
            save_state(self.state)

    def ensure_counter(self, hub_id: int) -> int:
        key = str(hub_id)
        self.state["counters"].setdefault(key, 0)
        self.state["counters"][key] += 1
        save_state(self.state)
        return self.state["counters"][key]

    def prune_and_count_duo(self, guild: discord.Guild, hub_id: int) -> int:
        """Elimina entradas obsoletas del estado y devuelve cuántos canales DUO siguen activos para este hub."""
        changed = False
        count = 0
        for cid, info in list(self.state["channels"].items()):
            if info.get("hub_id") != hub_id:
                continue
            if info.get("is_personal"):
                continue
            ch = guild.get_channel(int(cid))
            if isinstance(ch, discord.VoiceChannel):
                count += 1
            else:
                self.state["channels"].pop(cid, None)
                changed = True
        if changed:
            save_state(self.state)
        return count

    def next_duo_index(self, guild: discord.Guild, hub_id: int) -> int:
        """El siguiente índice DUO es (#activos + 1). Si no hay activos, empieza en 1."""
        activos = self.prune_and_count_duo(guild, hub_id)
        return activos + 1

    def require_owner_or_mod(self, interaction: discord.Interaction) -> tuple[discord.VoiceChannel, bool]:
        """Returns (channel, is_owner_or_mod). Raises and responds if invalid."""
        if not interaction.user.voice or not interaction.user.voice.channel:
            raise app_commands.AppCommandError("Debes estar en un canal de voz temporal.")
        ch = interaction.user.voice.channel
        if not isinstance(ch, discord.VoiceChannel) or not self.is_temp(ch):
            raise app_commands.AppCommandError("Este comando solo funciona en canales temporales.")
        owner_id = self.get_owner_id(ch.id)
        is_mod = interaction.user.guild_permissions.manage_channels
        is_owner = owner_id == interaction.user.id
        return ch, (is_owner or is_mod)

    # ---------- events ----------
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # Join-to-create
        if after and after.channel and after.channel.id in TEMP_HUB_IDS:
            hub = after.channel
            is_personal = (PERSONAL_HUB_ID and hub.id == PERSONAL_HUB_ID)

            if is_personal:
                name = PERSONAL_NAME_TEMPLATE.format(index=1, username=member.display_name)
            else:
                idx = self.next_duo_index(hub.guild, hub.id)
                name = NAME_TEMPLATE.format(index=idx, username=member.display_name)

            overwrites = hub.overwrites
            category = hub.category
            bitrate = getattr(hub, "bitrate", 64000)
            user_limit = (PERSONAL_DEFAULT_LIMIT if is_personal else (DEFAULT_LIMIT if DEFAULT_LIMIT > 0 else 0))

            try:
                new_channel = await hub.guild.create_voice_channel(
                    name=name,
                    overwrites=overwrites,
                    category=category,
                    bitrate=bitrate,
                    user_limit=user_limit
                )
                await member.move_to(new_channel, reason="Join-to-create")
                self.state["channels"][str(new_channel.id)] = {
                    "owner_id": member.id,
                    "hub_id": hub.id,
                    "created_at": datetime.utcnow().isoformat(),
                    "is_personal": is_personal
                }
                save_state(self.state)
            except discord.Forbidden:
                pass

        # Limpiezas y propiedad
        # Si salió de un canal temporal, revisar propietario y auto-borrado.
        if before and before.channel and isinstance(before.channel, discord.VoiceChannel) and self.is_temp(before.channel):
            ch = before.channel
            owner_id = self.get_owner_id(ch.id)
            # Si el dueño salió...
            if owner_id == member.id:
                info = self.state["channels"].get(str(ch.id), {})
                if not info.get("is_personal"):  # en personales NO limpiamos el owner
                    self.set_owner(ch.id, None)

            # Programar borrado si queda vacío
            if KEEPALIVE_MIN >= 0 and len([m for m in ch.members if not m.bot]) == 0:
                info = self.state["channels"].get(str(ch.id), {})
                if info.get("is_personal"):
                    owner_id = info.get("owner_id")
                    if owner_id and BOOSTER_ROLE_ID:
                        owner = ch.guild.get_member(owner_id)
                        if owner and any(r.id == BOOSTER_ROLE_ID for r in owner.roles):
                            # Es personal y el dueño es Booster → NO borrar
                            return
                # cancelar si ya había tarea
                t = self.cleanup_tasks.pop(ch.id, None)
                if t: t.cancel()
                async def _cleanup():
                    await asyncio.sleep(KEEPALIVE_MIN * 60 if KEEPALIVE_MIN > 0 else 0)
                    # Rechequear vacío
                    if ch and len([m for m in ch.members if not m.bot]) == 0:
                        # eliminar estado y canal
                        self.state["channels"].pop(str(ch.id), None)
                        save_state(self.state)
                        try:
                            await ch.delete(reason="Temp voice vacío")
                        except discord.Forbidden:
                            pass
                self.cleanup_tasks[ch.id] = asyncio.create_task(_cleanup())

        # Si entró a un canal temporal, cancelar borrado
        if after and after.channel and isinstance(after.channel, discord.VoiceChannel) and self.is_temp(after.channel):
            t = self.cleanup_tasks.pop(after.channel.id, None)
            if t: t.cancel()

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if not BOOSTER_ROLE_ID:
            return
        b_roles = {r.id for r in before.roles}
        a_roles = {r.id for r in after.roles}
        lost = (BOOSTER_ROLE_ID in b_roles) and (BOOSTER_ROLE_ID not in a_roles)
        if not lost:
            return
        for cid, info in list(self.state["channels"].items()):
            if info.get("is_personal") and info.get("owner_id") == after.id:
                ch = after.guild.get_channel(int(cid))
                if isinstance(ch, discord.VoiceChannel) and len([m for m in ch.members if not m.bot]) == 0:
                    try:
                        await ch.delete(reason="Personal sin Booster (auto-clean)")
                    except discord.Forbidden:
                        pass
                    self.state["channels"].pop(cid, None)
                    save_state(self.state)

    # ---------- commands ----------
    group = app_commands.Group(name="voice", description="Administra tu canal temporal")

    @group.command(name="rename", description="Renombra tu canal temporal.")
    async def voice_rename(self, interaction: discord.Interaction, nombre: str):
        try:
            ch, ok = self.require_owner_or_mod(interaction)
        except app_commands.AppCommandError as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        if not ok:
            return await interaction.response.send_message("Solo el propietario o un moderador puede renombrar.", ephemeral=True)
        await ch.edit(name=nombre)
        await interaction.response.send_message(f"Nombre cambiado a **{nombre}**.", ephemeral=True)

    @group.command(name="limit", description="Cambia el límite de usuarios.")
    async def voice_limit(self, interaction: discord.Interaction, limite: app_commands.Range[int, 0, 99]):
        try:
            ch, ok = self.require_owner_or_mod(interaction)
        except app_commands.AppCommandError as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        if not ok:
            return await interaction.response.send_message("Solo el propietario o un moderador puede cambiar el límite.", ephemeral=True)
        await ch.edit(user_limit=limite)
        await interaction.response.send_message(f"Límite cambiado a **{limite}**.", ephemeral=True)

    @group.command(name="lock", description="Bloquea el canal (nadie nuevo puede entrar).")
    async def voice_lock(self, interaction: discord.Interaction):
        try:
            ch, ok = self.require_owner_or_mod(interaction)
        except app_commands.AppCommandError as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        if not ok:
            return await interaction.response.send_message("Solo el propietario o un moderador puede bloquear.", ephemeral=True)
        overwrites = ch.overwrites
        overwrites[interaction.guild.default_role] = discord.PermissionOverwrite(connect=False)
        await ch.edit(overwrites=overwrites)
        await interaction.response.send_message("🔒 Canal bloqueado.", ephemeral=True)

    @group.command(name="unlock", description="Desbloquea el canal.")
    async def voice_unlock(self, interaction: discord.Interaction):
        try:
            ch, ok = self.require_owner_or_mod(interaction)
        except app_commands.AppCommandError as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        if not ok:
            return await interaction.response.send_message("Solo el propietario o un moderador puede desbloquear.", ephemeral=True)
        overwrites = ch.overwrites
        # None elimina el overwrite explícito
        overwrites[interaction.guild.default_role] = discord.PermissionOverwrite(connect=None)
        await ch.edit(overwrites=overwrites)
        await interaction.response.send_message("🔓 Canal desbloqueado.", ephemeral=True)

    @group.command(name="hide", description="Oculta el canal para los demás.")
    async def voice_hide(self, interaction: discord.Interaction):
        try:
            ch, ok = self.require_owner_or_mod(interaction)
        except app_commands.AppCommandError as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        if not ok:
            return await interaction.response.send_message("Solo el propietario o un moderador puede ocultar.", ephemeral=True)
        overwrites = ch.overwrites
        overwrites[interaction.guild.default_role] = discord.PermissionOverwrite(view_channel=False, connect=False)
        await ch.edit(overwrites=overwrites)
        await interaction.response.send_message("🙈 Canal oculto.", ephemeral=True)

    @group.command(name="reveal", description="Revela el canal (visible nuevamente).")
    async def voice_reveal(self, interaction: discord.Interaction):
        try:
            ch, ok = self.require_owner_or_mod(interaction)
        except app_commands.AppCommandError as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        if not ok:
            return await interaction.response.send_message("Solo el propietario o un moderador puede revelar.", ephemeral=True)
        overwrites = ch.overwrites
        overwrites[interaction.guild.default_role] = discord.PermissionOverwrite(view_channel=None, connect=None)
        await ch.edit(overwrites=overwrites)
        await interaction.response.send_message("👀 Canal visible.", ephemeral=True)

    @group.command(name="kick", description="Expulsa a un miembro del canal de voz.")
    async def voice_kick(self, interaction: discord.Interaction, miembro: discord.Member):
        try:
            ch, ok = self.require_owner_or_mod(interaction)
        except app_commands.AppCommandError as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        if not ok:
            return await interaction.response.send_message("Solo el propietario o un moderador puede expulsar.", ephemeral=True)
        if miembro.voice and miembro.voice.channel == ch:
            try:
                await miembro.move_to(None, reason="Kick de canal temporal")
                await interaction.response.send_message(f"👢 {miembro.mention} expulsado.", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("Me faltan permisos para mover usuarios.", ephemeral=True)
        else:
            await interaction.response.send_message("Ese usuario no está en tu canal.", ephemeral=True)

    @group.command(name="ban", description="Bloquea a un miembro para que no pueda unirse.")
    async def voice_ban(self, interaction: discord.Interaction, miembro: discord.Member):
        try:
            ch, ok = self.require_owner_or_mod(interaction)
        except app_commands.AppCommandError as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        if not ok:
            return await interaction.response.send_message("Solo el propietario o un moderador puede banear.", ephemeral=True)
        overwrites = ch.overwrites
        overwrites[miembro] = discord.PermissionOverwrite(connect=False, view_channel=False)
        await ch.edit(overwrites=overwrites)
        try:
            if miembro.voice and miembro.voice.channel == ch:
                await miembro.move_to(None, reason="Ban de canal temporal")
        except discord.Forbidden:
            pass
        await interaction.response.send_message(f"🚫 {miembro.mention} baneado del canal.", ephemeral=True)

    @group.command(name="unban", description="Quita el bloqueo a un miembro.")
    async def voice_unban(self, interaction: discord.Interaction, miembro: discord.Member):
        try:
            ch, ok = self.require_owner_or_mod(interaction)
        except app_commands.AppCommandError as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        if not ok:
            return await interaction.response.send_message("Solo el propietario o un moderador puede quitar el ban.", ephemeral=True)
        overwrites = ch.overwrites
        if miembro in overwrites:
            del overwrites[miembro]
        await ch.edit(overwrites=overwrites)
        await interaction.response.send_message(f"✅ {miembro.mention} desbaneado.", ephemeral=True)

    @group.command(name="transfer", description="Transfiere la propiedad a otro miembro.")
    async def voice_transfer(self, interaction: discord.Interaction, miembro: discord.Member):
        try:
            ch, ok = self.require_owner_or_mod(interaction)
        except app_commands.AppCommandError as e:
            return await interaction.response.send_message(str(e), ephemeral=True)
        if not ok:
            return await interaction.response.send_message("Solo el propietario o un moderador puede transferir.", ephemeral=True)
        if not (miembro.voice and miembro.voice.channel == ch):
            return await interaction.response.send_message("El nuevo propietario debe estar en el canal.", ephemeral=True)
        self.set_owner(ch.id, miembro.id)
        await interaction.response.send_message(f"👑 {miembro.mention} es ahora el propietario.", ephemeral=True)

    @group.command(name="owner", description="Muestra el propietario del canal.")
    async def voice_owner(self, interaction: discord.Interaction):
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("Debes estar en un canal temporal.", ephemeral=True)
        ch = interaction.user.voice.channel
        if not self.is_temp(ch):
            return await interaction.response.send_message("Este no es un canal temporal.", ephemeral=True)
        owner_id = self.get_owner_id(ch.id)
        if owner_id:
            member = ch.guild.get_member(owner_id)
            return await interaction.response.send_message(f"Propietario: **{member}**", ephemeral=True)
        await interaction.response.send_message("Este canal no tiene propietario asignado.", ephemeral=True)

    @group.command(name="claim", description="Reclama el canal si no hay propietario.")
    async def voice_claim(self, interaction: discord.Interaction):
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message("Debes estar en un canal temporal.", ephemeral=True)
        ch = interaction.user.voice.channel
        if not self.is_temp(ch):
            return await interaction.response.send_message("Este no es un canal temporal.", ephemeral=True)
        info = self.state["channels"].get(str(ch.id), {})
        owner_id = info.get("owner_id")
        if owner_id:
            return await interaction.response.send_message("Este canal ya tiene propietario.", ephemeral=True)
        # respetar candado
        left_at = info.get("owner_left_at")
        if left_at:
            try:
                ts = datetime.fromisoformat(left_at)
                if datetime.utcnow() < ts + timedelta(minutes=OWNERSHIP_LOCK_MIN):
                    return await interaction.response.send_message("Aún está en período de candado. Intenta más tarde.", ephemeral=True)
            except Exception:
                pass
        self.set_owner(ch.id, interaction.user.id)
        await interaction.response.send_message("Has reclamado la propiedad del canal. 👑", ephemeral=True)

    @group.command(name="clean", description="Borra canales temporales vacíos (admin).")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def voice_clean(self, interaction: discord.Interaction):
        deleted = 0
        for cid, info in list(self.state["channels"].items()):
            ch = interaction.guild.get_channel(int(cid))
            if isinstance(ch, discord.VoiceChannel) and len([m for m in ch.members if not m.bot]) == 0:
                try:
                    await ch.delete(reason="Clean de temporales")
                    deleted += 1
                except discord.Forbidden:
                    pass
                self.state["channels"].pop(cid, None)
        save_state(self.state)
        await interaction.response.send_message(f"Eliminados **{deleted}** canales vacíos.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(TempVoice(bot))
