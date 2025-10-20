from __future__ import annotations

import asyncio
import json
import difflib
import re
import unicodedata
from pathlib import Path
from typing import Dict, List

import discord
from discord import app_commands
from discord.ext import commands

PERSIST_FILE = Path("icon_roles.json")

TARGET_ICON_NAMES: List[str] = [
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

ALIASES: Dict[str, str] = {
    "pet me": "Petme",
    "hug me": "Hugme",
    "goth": "Gothic",
    "soft girl": "Softgirl",
    "trizzte": "Trizzzte",
    "trizte": "Trizzzte",
    "felizz": "Felizzz",
    "ok": "OK!",
    "uwu": "uwu",
}


def canonical_name(raw: str) -> str:
    text = raw.strip()
    low = text.lower()
    if low in ALIASES:
        return ALIASES[low]
    for target in TARGET_ICON_NAMES:
        if target.lower() == low:
            return target
    return text


def slugify(text: str) -> str:
    canonical = canonical_name(text)
    nfkd = unicodedata.normalize("NFKD", canonical)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    cleaned = re.sub(r"[^a-zA-Z0-9 ]+", " ", no_accents).lower()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


class IconResolver:
    def __init__(self) -> None:
        self.overrides: Dict[str, int] = {}
        self.mapping: Dict[str, int] = {}
        if PERSIST_FILE.exists():
            try:
                data = json.loads(PERSIST_FILE.read_text())
                self.overrides = {k: int(v) for k, v in data.get("overrides", {}).items()}
                self.mapping = {k: int(v) for k, v in data.get("mapping", {}).items()}
            except Exception:
                self.overrides = {}
                self.mapping = {}

    def save(self) -> None:
        PERSIST_FILE.write_text(json.dumps({"overrides": self.overrides, "mapping": self.mapping}, indent=2))

    def build_from_guild(self, guild: discord.Guild):
        roles_by_slug: Dict[str, List[discord.Role]] = {}
        for role in guild.roles:
            roles_by_slug.setdefault(slugify(role.name), []).append(role)

        found: Dict[str, int] = {}
        missing: List[str] = []

        for name in TARGET_ICON_NAMES:
            canonical = canonical_name(name)
            override_id = self.overrides.get(canonical)
            if override_id:
                role = guild.get_role(override_id)
                if role:
                    found[canonical] = role.id
                    continue
            missing.append(canonical)

        still_missing: List[str] = []
        for name in missing:
            slug = slugify(name)
            candidates = roles_by_slug.get(slug, [])
            if candidates:
                role = sorted(candidates, key=lambda r: r.position, reverse=True)[0]
                found[name] = role.id
            else:
                still_missing.append(name)

        really_missing: List[str] = []
        all_slugs = list(roles_by_slug.keys())
        for name in still_missing:
            slug = slugify(name)
            best = difflib.get_close_matches(slug, all_slugs, n=1, cutoff=0.82)
            if best:
                role = sorted(roles_by_slug[best[0]], key=lambda r: r.position, reverse=True)[0]
                found[name] = role.id
            else:
                really_missing.append(name)

        self.mapping = found
        self.save()

        async def _create_missing() -> List[str]:
            created: List[str] = []
            for name in really_missing:
                try:
                    role = await guild.create_role(name=name, reason="Iconos: crear faltante")
                    found[name] = role.id
                    created.append(name)
                    await asyncio.sleep(0.2)
                except discord.Forbidden:
                    pass
            self.mapping = found
            self.save()
            return created

        return really_missing, _create_missing

resolver = IconResolver()


class IconSelect(discord.ui.Select):
    def __init__(self, mapping: Dict[str, int]):
        options = [discord.SelectOption(label=name, value=str(role_id)) for name, role_id in sorted(mapping.items())]
        super().__init__(placeholder="Elige tu icono", min_values=1, max_values=1, options=options, custom_id="iconos_select")
        self.icon_role_ids = set(mapping.values())

    async def callback(self, interaction: discord.Interaction) -> None:
        role_id = int(self.values[0])
        role = interaction.guild.get_role(role_id)
        if not role:
            return await interaction.response.send_message("❌ Rol no encontrado. Avísale a un admin.", ephemeral=True)
        to_remove = [r for r in interaction.user.roles if r.id in self.icon_role_ids and r.id != role_id]
        try:
            if to_remove:
                await interaction.user.remove_roles(*to_remove, reason="Cambio de icono")
            await interaction.user.add_roles(role, reason="Asignación de icono")
            await interaction.response.send_message(f"✅ Icono cambiado a **{role.name}**.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ No tengo permisos para gestionar esos roles.", ephemeral=True)


class RemoveIcon(discord.ui.Button):
    def __init__(self, icon_role_ids: set[int]):
        super().__init__(label="Quitar icono", style=discord.ButtonStyle.danger, custom_id="iconos_remove")
        self.icon_role_ids = icon_role_ids

    async def callback(self, interaction: discord.Interaction) -> None:
        to_remove = [r for r in interaction.user.roles if r.id in self.icon_role_ids]
        if not to_remove:
            return await interaction.response.send_message("No tienes icono activo.", ephemeral=True)
        try:
            await interaction.user.remove_roles(*to_remove, reason="Quitar icono")
            await interaction.response.send_message("Icono quitado.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ No pude quitar el rol.", ephemeral=True)


class IconView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.refresh()

    def refresh(self) -> None:
        self.clear_items()
        if not resolver.mapping:
            self.add_item(
                discord.ui.Button(
                    label="No hay iconos configurados",
                    custom_id="iconos_placeholder",
                    style=discord.ButtonStyle.secondary,
                    disabled=True,
                )
            )
            return
        self.add_item(IconSelect(resolver.mapping))
        self.add_item(RemoveIcon(set(resolver.mapping.values())))


class Iconos(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.view = IconView()

    async def cog_load(self) -> None:
        self.bot.add_view(self.view)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="iconos_set", description="Asocia un nombre de icono con un rol (override manual).")
    async def iconos_set(self, interaction: discord.Interaction, nombre: str, rol: discord.Role) -> None:
        canonical = canonical_name(nombre)
        resolver.overrides[canonical] = rol.id
        resolver.mapping[canonical] = rol.id
        resolver.save()
        self.view.refresh()
        await interaction.response.send_message(f"✅ Override: **{canonical}** → {rol.mention}", ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="iconos_auto", description="Detecta roles por nombre; opcionalmente crea los faltantes.")
    async def iconos_auto(self, interaction: discord.Interaction, crear_faltantes: bool = False) -> None:
        await interaction.response.defer(ephemeral=True)
        missing, creator = resolver.build_from_guild(interaction.guild)
        created: List[str] = []
        if crear_faltantes and missing:
            created = await creator()
            missing, _ = resolver.build_from_guild(interaction.guild)
        self.view.refresh()
        resumen = [
            f"Encontrados: {len(resolver.mapping)}",
            f"Overrides: {len(resolver.overrides)}",
            f"Faltantes: {len(missing)}",
        ]
        if created:
            resumen.append("Creados: " + ", ".join(created))
        if missing:
            resumen.append("No hallados: " + ", ".join(missing))
        await interaction.followup.send("\n".join(resumen), ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="iconos_ver", description="Muestra el mapeo actual (nombre → rol).")
    async def iconos_ver(self, interaction: discord.Interaction) -> None:
        if not resolver.mapping:
            return await interaction.response.send_message("Aún no hay mapeo. Usa /iconos_auto o /iconos_set.", ephemeral=True)
        lines = [f"- {name} → <@&{role_id}>" for name, role_id in sorted(resolver.mapping.items())]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="post_iconos", description="Publica el selector de iconos en el canal actual.")
    async def post_iconos(self, interaction: discord.Interaction) -> None:
        if not resolver.mapping:
            return await interaction.response.send_message("⚠️ Primero configura con /iconos_auto o /iconos_set.", ephemeral=True)
        embed = discord.Embed(
            title="Instrucciones:",
            description=(
                "1) Mira la imagen con los nombres de iconos.\n"
                "2) Elige el nombre en el menú.\n"
                "3) Usa 'Quitar icono' para limpiar antes de cambiar."
            ),
            color=0x5865F2,
        )
        try:
            file = discord.File("catalogo_iconos.png", filename="catalogo_iconos.png")
            embed.set_image(url="attachment://catalogo_iconos.png")
            await interaction.response.send_message(embed=embed, file=file, view=self.view)
        except FileNotFoundError:
            await interaction.response.send_message(embed=embed, view=self.view)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Iconos(bot))
