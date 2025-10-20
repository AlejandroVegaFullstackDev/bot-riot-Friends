import os
import discord
from discord import app_commands
from discord.ext import commands

MOD_COLOR = 0x5865F2
ALERT_COLOR = 0xED4245

ADMIN_ROLE_IDS = {831254885747392572}
MOD_ROLE_IDS = {1262586573090979841}


def _is_admin(member: discord.Member) -> bool:
    return bool(
        member.guild_permissions.administrator
        or any(role.id in ADMIN_ROLE_IDS for role in member.roles)
    )


def _is_mod_or_admin(member: discord.Member) -> bool:
    return _is_admin(member) or any(role.id in MOD_ROLE_IDS for role in member.roles)


async def _reply_ephemeral(interaction: discord.Interaction, message: str):
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


class Moderation(commands.Cog):
    """Comandos de moderación controlados por roles Admin/Mod."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="mod", description="Comandos de moderación rápida")

    # ------------------- shared logic -------------------
    async def _clear_impl(self, interaction: discord.Interaction, cantidad: int, motivo: str, moderator: discord.Member):
        channel = interaction.channel
        guild = interaction.guild
        if not guild or not isinstance(channel, discord.TextChannel):
            return await interaction.followup.send("❌ Este comando solo funciona en canales de texto.", ephemeral=True)

        me = guild.me
        if not channel.permissions_for(me).manage_messages:
            return await interaction.followup.send("❌ No tengo permiso **Manage Messages** en este canal.", ephemeral=True)

        remaining = cantidad
        deleted_total = 0
        while remaining > 0:
            to_delete = min(remaining, 100)
            deleted = await channel.purge(limit=to_delete, reason=f"{moderator} | {motivo}", bulk=True)
            if not deleted:
                break
            deleted_total += len(deleted)
            remaining -= to_delete

        embed = discord.Embed(
            title="Limpieza de mensajes",
            description=f"Se eliminaron **{deleted_total}** mensajes.",
            color=MOD_COLOR,
        )
        embed.add_field(name="Moderador", value=moderator.mention, inline=True)
        embed.add_field(name="Motivo", value=motivo or "—", inline=False)
        embed.set_footer(text=f"Canal: #{channel.name}")
        await channel.send(embed=embed)

        await interaction.followup.send(f"Listo: borrados **{deleted_total}** mensajes.", ephemeral=True)

    async def _kick_impl(self, interaction: discord.Interaction, objetivo: discord.Member, motivo: str, moderator: discord.Member):
        guild = interaction.guild
        channel = interaction.channel
        if not guild or not isinstance(channel, discord.TextChannel):
            return await interaction.followup.send("❌ Ocurrió un problema con el canal.", ephemeral=True)

        me = guild.me
        if not me.guild_permissions.kick_members:
            return await interaction.followup.send("❌ No tengo permiso **Kick Members**.", ephemeral=True)

        if moderator != guild.owner and objetivo.top_role >= moderator.top_role:
            return await interaction.followup.send("❌ No puedes expulsar a alguien con un rol mayor o igual al tuyo.", ephemeral=True)

        try:
            try:
                await objetivo.send(f"Has sido expulsado de **{guild.name}**.\nMotivo: {motivo or '—'}")
            except Exception:
                pass

            await guild.kick(objetivo, reason=f"{moderator} | {motivo}")

            embed = discord.Embed(title="Usuario expulsado", color=ALERT_COLOR)
            embed.add_field(name="Usuario", value=f"{objetivo.mention} (`{objetivo.id}`)", inline=False)
            embed.add_field(name="Moderador", value=moderator.mention, inline=True)
            embed.add_field(name="Motivo", value=motivo or "—", inline=False)
            await channel.send(embed=embed)

            await interaction.followup.send("Expulsado.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ No tengo permisos o jerarquía para expulsar a ese usuario.", ephemeral=True)

    async def _ban_impl(self, interaction: discord.Interaction, objetivo: discord.Member, motivo: str, moderator: discord.Member):
        guild = interaction.guild
        channel = interaction.channel
        if not guild or not isinstance(channel, discord.TextChannel):
            return await interaction.followup.send("❌ Ocurrió un problema con el canal.", ephemeral=True)

        me = guild.me
        if not me.guild_permissions.ban_members:
            return await interaction.followup.send("❌ No tengo permiso **Ban Members**.", ephemeral=True)

        if moderator != guild.owner and objetivo.top_role >= moderator.top_role:
            return await interaction.followup.send("❌ No puedes banear a alguien con un rol mayor o igual al tuyo.", ephemeral=True)

        try:
            try:
                await objetivo.send(f"Has sido baneado de **{guild.name}**.\nMotivo: {motivo or '—'}")
            except Exception:
                pass

            await guild.ban(objetivo, reason=f"{moderator} | {motivo}")

            embed = discord.Embed(title="Usuario baneado", color=ALERT_COLOR)
            embed.add_field(name="Usuario", value=f"{objetivo.mention} (`{objetivo.id}`)", inline=False)
            embed.add_field(name="Moderador", value=moderator.mention, inline=True)
            embed.add_field(name="Motivo", value=motivo or "—", inline=False)
            await channel.send(embed=embed)

            await interaction.followup.send("Baneado.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ No tengo permisos o jerarquía para banear a ese usuario.", ephemeral=True)

    # ------------------- slash group -------------------
    @group.command(name="clear", description="Borra N mensajes de este canal (máx 1000).")
    @app_commands.describe(
        cantidad="Número de mensajes a borrar (1–1000)",
        motivo="Motivo (se mostrará en el cartel del canal)"
    )
    @app_commands.default_permissions(manage_messages=True)
    async def group_clear(
        self,
        interaction: discord.Interaction,
        cantidad: app_commands.Range[int, 1, 1000],
        motivo: str
    ):
        moderator = interaction.user
        if not isinstance(moderator, discord.Member) or not _is_mod_or_admin(moderator):
            return await _reply_ephemeral(interaction, "Solo Mods/Admins pueden usar este comando.")

        await interaction.response.defer(ephemeral=True)
        await self._clear_impl(interaction, cantidad, motivo, moderator)

    @group.command(name="kick", description="Expulsa a un usuario con motivo.")
    @app_commands.describe(usuario="Miembro a expulsar", motivo="Motivo (se mostrará en el cartel del canal)")
    @app_commands.default_permissions(administrator=True)
    async def group_kick(self, interaction: discord.Interaction, usuario: discord.Member, motivo: str):
        moderator = interaction.user
        if not isinstance(moderator, discord.Member) or not _is_admin(moderator):
            return await _reply_ephemeral(interaction, "Solo los Admins pueden expulsar usuarios.")

        await interaction.response.defer(ephemeral=True)
        await self._kick_impl(interaction, usuario, motivo, moderator)

    @group.command(name="ban", description="Banea a un usuario con motivo.")
    @app_commands.describe(usuario="Miembro a banear", motivo="Motivo (se mostrará en el cartel del canal)")
    @app_commands.default_permissions(administrator=True)
    async def group_ban(self, interaction: discord.Interaction, usuario: discord.Member, motivo: str):
        moderator = interaction.user
        if not isinstance(moderator, discord.Member) or not _is_admin(moderator):
            return await _reply_ephemeral(interaction, "Solo los Admins pueden banear usuarios.")

        await interaction.response.defer(ephemeral=True)
        await self._ban_impl(interaction, usuario, motivo, moderator)

    # ------------------- alias -------------------
    @app_commands.command(name="mod-clear", description="Alias: borra N mensajes en este canal.")
    @app_commands.describe(
        cantidad="Número de mensajes a borrar (1–1000)",
        motivo="Motivo (se mostrará en el cartel del canal)"
    )
    @app_commands.default_permissions(manage_messages=True)
    async def clear_alias(
        self,
        interaction: discord.Interaction,
        cantidad: app_commands.Range[int, 1, 1000],
        motivo: str
    ):
        moderator = interaction.user
        if not isinstance(moderator, discord.Member) or not _is_mod_or_admin(moderator):
            return await _reply_ephemeral(interaction, "Solo Mods/Admins pueden usar este comando.")

        await interaction.response.defer(ephemeral=True)
        await self._clear_impl(interaction, cantidad, motivo, moderator)

    @app_commands.command(name="mod-kick", description="Alias: expulsa a un usuario con motivo.")
    @app_commands.describe(usuario="Miembro a expulsar", motivo="Motivo (se mostrará en el cartel del canal)")
    @app_commands.default_permissions(administrator=True)
    async def kick_alias(self, interaction: discord.Interaction, usuario: discord.Member, motivo: str):
        moderator = interaction.user
        if not isinstance(moderator, discord.Member) or not _is_admin(moderator):
            return await _reply_ephemeral(interaction, "Solo los Admins pueden expulsar usuarios.")

        await interaction.response.defer(ephemeral=True)
        await self._kick_impl(interaction, usuario, motivo, moderator)

    @app_commands.command(name="mod-ban", description="Alias: banea a un usuario con motivo.")
    @app_commands.describe(usuario="Miembro a banear", motivo="Motivo (se mostrará en el cartel del canal)")
    @app_commands.default_permissions(administrator=True)
    async def ban_alias(self, interaction: discord.Interaction, usuario: discord.Member, motivo: str):
        moderator = interaction.user
        if not isinstance(moderator, discord.Member) or not _is_admin(moderator):
            return await _reply_ephemeral(interaction, "Solo los Admins pueden banear usuarios.")

        await interaction.response.defer(ephemeral=True)
        await self._ban_impl(interaction, usuario, motivo, moderator)


async def setup(bot: commands.Bot):
    cog = Moderation(bot)
    await bot.add_cog(cog)
    guild_id = os.getenv("GUILD_ID")
    if guild_id and guild_id.isdigit():
        gobj = discord.Object(id=int(guild_id))
        try:
            bot.tree.add_command(cog.group, guild=gobj)
        except app_commands.CommandAlreadyRegistered:
            bot.tree.remove_command(cog.group.name, guild=gobj)
            bot.tree.add_command(cog.group, guild=gobj)
