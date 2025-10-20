from __future__ import annotations

import re
from typing import List

import discord
from discord import app_commands
from discord.ext import commands

ICON_NAMES = [
    "Petme",
    "Hugme",
    "Gothic",
    "Kawaii",
    "Shy",
    "Shyy",
    "Dead",
    "Killyou",
    "Yeii",
    "Cutie",
    "Cool",
    "Otaku",
    "Akatsuki",
    "Sad",
    "Enojadizzza",
    "Trizzzte",
    "Felizzz",
    "OK!",
    "Softgirl",
    "uwu",
    "Carnalito",
]

URL_RX = re.compile(r"^https?://", re.I)


class RoleIconSelect(discord.ui.Select):
    def __init__(self, idx: int, options: List[discord.SelectOption], role_ids_set: set[int]):
        super().__init__(
            placeholder=f"Iconos Lista {idx}",
            min_values=1,
            max_values=1,
            options=options,
            row=(idx - 1) % 5,
        )
        self.role_ids_set = role_ids_set

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        member: discord.Member = interaction.user
        chosen_role_id = int(self.values[0])
        to_remove = [r for r in member.roles if r.id in self.role_ids_set and r.id != chosen_role_id]
        try:
            if to_remove:
                await member.remove_roles(*to_remove, reason="Cambio de icono")
            role = interaction.guild.get_role(chosen_role_id)
            if role and role not in member.roles:
                await member.add_roles(role, reason="Seleccionó icono")
            await interaction.response.send_message(
                f"✅ Icono aplicado: **{role.name if role else chosen_role_id}**",
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.response.send_message("❌ No tengo permiso para gestionar roles.", ephemeral=True)


class ClearIconButton(discord.ui.Button):
    def __init__(self, role_ids_set: set[int]):
        super().__init__(style=discord.ButtonStyle.secondary, label="Quitar icono", emoji="🧹")
        self.role_ids_set = role_ids_set

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        member: discord.Member = interaction.user
        to_remove = [r for r in member.roles if r.id in self.role_ids_set]
        if not to_remove:
            return await interaction.response.send_message("No tienes icono activo.", ephemeral=True)
        try:
            await member.remove_roles(*to_remove, reason="Quitar icono")
            await interaction.response.send_message("🧹 Icono quitado.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ No tengo permiso para gestionar roles.", ephemeral=True)


class IconMenuView(discord.ui.View):
    def __init__(self, selects: List[RoleIconSelect], role_ids_set: set[int], *, timeout: float | None = None):
        super().__init__(timeout=timeout)
        for sel in selects:
            self.add_item(sel)
        self.add_item(ClearIconButton(role_ids_set))


class PublishIconsPanel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _resolve_icon_roles(self, guild: discord.Guild):
        resolved: List[tuple[str, discord.Role]] = []
        wanted = {name.lower(): name for name in ICON_NAMES}
        by_name = {role.name.lower(): role for role in guild.roles}
        for key, label in wanted.items():
            role = by_name.get(key)
            if role:
                resolved.append((label, role))
        role_ids_set = {r.id for _, r in resolved}
        return resolved, role_ids_set

    def _chunk(self, seq, size):
        for i in range(0, len(seq), size):
            yield seq[i:i + size]

    @app_commands.command(name="publish-icons", description="Publica el panel de iconos con imagen y lo ancla.")
    @app_commands.describe(
        titulo="Título del bloque de instrucciones",
        imagen="Imagen adjunta del catálogo",
        url="URL de imagen (si no adjuntas)",
        anclar="Anclar el mensaje publicado",
    )
    async def publish_icons(
        self,
        inter: discord.Interaction,
        titulo: str = "Instrucciones",
        imagen: discord.Attachment | None = None,
        url: str | None = None,
        anclar: bool = True,
    ):
        await inter.response.defer(thinking=True, ephemeral=False)

        if not inter.guild:
            return await inter.followup.send("Solo usable en servidores.", ephemeral=True)

        pairs, role_ids_set = await self._resolve_icon_roles(inter.guild)
        if not pairs:
            return await inter.followup.send("No encontré roles de icono con los nombres configurados.", ephemeral=True)

        selects: List[RoleIconSelect] = []
        for idx, chunk in enumerate(self._chunk(pairs, 25), start=1):
            options = [discord.SelectOption(label=label, value=str(role.id)) for label, role in chunk]
            selects.append(RoleIconSelect(idx=idx, options=options, role_ids_set=role_ids_set))

        view = IconMenuView(selects, role_ids_set)

        embed = discord.Embed(
            title=titulo,
            description=(
                "1.- Haz click en la **imagen** para ver mejor los iconos y sus nombres.\n"
                "2.- Elige el icono en el **menú** que coincida con el nombre que deseas.\n"
                "3.- Para cambiar de icono, usa **Quitar icono** y vuelve a elegir."
            ),
            color=discord.Color.blurple()
        )

        files = []
        if imagen:
            file = await imagen.to_file()
            embed.set_image(url=f"attachment://{file.filename}")
            files.append(file)
        elif url and URL_RX.match(url):
            embed.set_image(url=url)

        msg = await inter.channel.send(embed=embed, view=view, files=files)  # type: ignore

        if anclar:
            try:
                await msg.pin()
            except discord.Forbidden:
                pass

        await inter.followup.send("Panel de iconos publicado ✅", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(PublishIconsPanel(bot))
