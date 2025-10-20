import asyncio
import json
from collections import defaultdict
from pathlib import Path

import discord
from discord.ext import commands

STORE_PATH = Path("data/personal_channels.json")


def load_store():
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if STORE_PATH.exists():
        try:
            return json.loads(STORE_PATH.read_text("utf-8"))
        except Exception:
            pass
    return {"by_owner": {}, "by_channel": {}}


def save_store(store):
    STORE_PATH.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")


class PersonalVoice(commands.Cog):
    """Salas personales persistentes (una por usuario, visibles para todos)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cfg = bot.config
        self.store = load_store()
        self._locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    # ------------------------------ store helpers ------------------------------
    def _get_owned_id(self, user_id: int) -> int | None:
        cid = self.store["by_owner"].get(str(user_id))
        return int(cid) if cid else None

    def get_owned_channel(self, guild: discord.Guild, user_id: int) -> discord.VoiceChannel | None:
        cid = self._get_owned_id(user_id)
        if cid is None:
            return None
        channel = guild.get_channel(cid)
        if isinstance(channel, discord.VoiceChannel):
            return channel
        # limpiar referencias rotas
        self.store["by_owner"].pop(str(user_id), None)
        self.store["by_channel"].pop(str(cid), None)
        save_store(self.store)
        return None

    def register(self, owner_id: int, channel_id: int):
        self.store["by_owner"][str(owner_id)] = channel_id
        self.store["by_channel"][str(channel_id)] = owner_id
        save_store(self.store)

    def unregister_by_channel(self, channel_id: int):
        owner = self.store["by_channel"].pop(str(channel_id), None)
        if owner is not None:
            self.store["by_owner"].pop(str(owner), None)
        save_store(self.store)

    # ------------------------------ utilidades ------------------------------
    def _hub_and_category(self, guild: discord.Guild):
        try:
            hub_id = int(self.cfg["tempvoice_personal_hub_id"])
        except Exception:
            return None, None
        hub = guild.get_channel(hub_id)
        category = hub.category if isinstance(hub, discord.VoiceChannel) else None
        return hub, category

    def _default_overwrites(self, guild: discord.Guild, member: discord.Member):
        return {
            guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=True),
            member: discord.PermissionOverwrite(
                manage_channels=True,
                manage_permissions=True,
                move_members=True,
                mute_members=True,
                deafen_members=True,
                view_channel=True,
                connect=True,
                speak=True,
                stream=True,
                use_voice_activation=True,
            ),
        }

    def _find_existing_personal(self, member: discord.Member) -> discord.VoiceChannel | None:
        _, category = self._hub_and_category(member.guild)
        if not category:
            return None
        for channel in category.channels:
            if not isinstance(channel, discord.VoiceChannel):
                continue
            ow = channel.overwrites_for(member)
            if ow.manage_channels is True:
                return channel
        return None

    async def _create_or_get_personal(self, member: discord.Member) -> discord.VoiceChannel:
        guild = member.guild
        lock = self._locks[member.id]
        async with lock:
            owned = self.get_owned_channel(guild, member.id)
            if owned:
                return owned

            existing = self._find_existing_personal(member)
            if existing:
                self.register(member.id, existing.id)
                return existing

            hub, category = self._hub_and_category(guild)
            name_tpl = self.cfg.get("tempvoice_personal_name_template", "Canal de {username}")
            name = name_tpl.format(username=member.display_name)
            limit = int(self.cfg.get("tempvoice_personal_default_limit", 0))
            overwrites = self._default_overwrites(guild, member)

            channel = await guild.create_voice_channel(
                name=name,
                category=category,
                user_limit=limit if limit > 0 else 0,
                overwrites=overwrites,
                reason=f"Canal personal de {member} (auto)",
            )
            self.register(member.id, channel.id)
            return channel

    # ------------------------------ eventos ------------------------------
    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            _, category = self._hub_and_category(guild)
            if not category:
                continue
            for channel in category.channels:
                if not isinstance(channel, discord.VoiceChannel):
                    continue
                for target, ow in channel.overwrites.items():
                    if isinstance(target, discord.Member) and ow.manage_channels is True:
                        self.store["by_owner"][str(target.id)] = channel.id
                        self.store["by_channel"][str(channel.id)] = target.id
                        break
        save_store(self.store)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        try:
            hub_id = int(self.cfg["tempvoice_personal_hub_id"])
        except Exception:
            return
        if after and after.channel and after.channel.id == hub_id:
            channel = await self._create_or_get_personal(member)
            try:
                await member.move_to(channel)
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if isinstance(channel, discord.VoiceChannel):
            self.unregister_by_channel(channel.id)

async def setup(bot: commands.Bot):
    await bot.add_cog(PersonalVoice(bot))
