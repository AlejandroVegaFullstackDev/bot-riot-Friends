from __future__ import annotations

import asyncio
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

COLOR_DB = Path("data/color_roles.json")
COLOR_GROUPS_UI = [
    ("rojos", "Colores Rojos"),
    ("naranjas", "Colores Naranjas"),
    ("amarillos", "Colores Amarillos"),
    ("verdes", "Colores Verdes"),
    ("azules", "Colores Azules"),
    ("morados", "Colores Morados"),
    ("rosas", "Colores Rosas"),
    ("blanco_negro", "Colores Blanco - Negro"),
]

PATTERNS = {
    "rojos": [r"\brojo", r"\bred"],
    "naranjas": [r"\bnaranj", r"\borange"],
    "amarillos": [r"\bamarill", r"\byellow"],
    "verdes": [r"\bverde", r"\bgreen"],
    "azules": [r"\bazul", r"\bblue"],
    "morados": [r"\bmorad", r"\bviolet", r"\blila", r"\bpurp", r"\bmagenta"],
    "rosas": [r"\brosa", r"\bpink", r"\bfucs"],
    "blanco_negro": [r"\bblanc", r"\bwhite", r"\bnegro", r"\bblack", r"\bgris", r"36393f", r"2f3136", r"99aab5"],
}

HEX_HINTS = {
    "rojos": ["ff0044", "f01c64", "b01454", "ff0000"],
    "naranjas": ["e87c24", "e4503c", "f7bd56"],
    "amarillos": ["ffd", "ff0", "ffd200", "f4ff00"],
    "verdes": ["20bc9c", "30d074", "70ff6b", "00ff00"],
    "azules": ["389cdc", "92c5fc", "77f9ff", "0000ff"],
    "morados": ["a05cb4", "a70feb", "743490", "8000ff", "ccccff"],
    "rosas": ["ecc9dd", "fba0c7", "ff0080"],
    "blanco_negro": ["ffffff", "000000"],
}

DEFAULT_NAMES = {
    "rojos": ["Rojo"],
    "naranjas": ["Naranja"],
    "amarillos": ["Amarillo"],
    "verdes": ["Verde"],
    "azules": ["Azul"],
    "morados": ["Morado"],
    "rosas": ["Rosa"],
    "blanco_negro": ["Blanco", "Negro", "Gris #36393f"],
}


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("–", "-").replace("—", "-").replace('"', " ")
    text = re.sub(r"[^0-9A-Za-z#\s\-]+", " ", text.lower())
    return " ".join(text.split())


def guess_group(role_name: str) -> Optional[str]:
    normalized = norm(role_name)
    for group, patterns in PATTERNS.items():
        if any(re.search(p, normalized) for p in patterns):
            return group
    for group, hints in HEX_HINTS.items():
        if any(hint in normalized for hint in hints):
            return group
    return None


def ensure_db() -> Dict[str, List[int]]:
    os.makedirs(COLOR_DB.parent, exist_ok=True)
    if COLOR_DB.exists():
        data = json.loads(COLOR_DB.read_text(encoding="utf-8"))
    else:
        data = {"groups": {key: [] for key, _ in COLOR_GROUPS_UI}}
        COLOR_DB.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def save_db(data: Dict[str, List[int]]):
    COLOR_DB.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


class ColorSelect(discord.ui.Select):
    def __init__(self, label: str, role_ids: List[int], all_ids: set[int]):
        options = []
        for rid in role_ids:
            options.append(discord.SelectOption(label=str(rid), value=str(rid)))
        super().__init__(placeholder=label, min_values=1, max_values=1, options=options)
        self.all_ids = all_ids

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        member = interaction.user
        target_id = int(self.values[0])
        to_remove = [role for role in member.roles if role.id in self.all_ids and role.id != target_id]
        try:
            if to_remove:
                await member.remove_roles(*to_remove, reason="Cambio de color")
            target_role = interaction.guild.get_role(target_id)
            if target_role and target_role not in member.roles:
                await member.add_roles(target_role, reason="Color elegido")
            await interaction.response.send_message(
                f"✅ Color aplicado: **{target_role.name if target_role else target_id}**",
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.response.send_message("❌ No tengo permisos para gestionar roles.", ephemeral=True)


class ClearColorButton(discord.ui.Button):
    def __init__(self, all_ids: set[int]):
        super().__init__(style=discord.ButtonStyle.secondary, label="Quitar icono", emoji="🧹")
        self.all_ids = all_ids

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        member = interaction.user
        to_remove = [role for role in member.roles if role.id in self.all_ids]
        if not to_remove:
            return await interaction.response.send_message("No tienes color activo.", ephemeral=True)
        try:
            await member.remove_roles(*to_remove, reason="Quitar color")
            await interaction.response.send_message("🧹 Color quitado.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ No tengo permisos para gestionar roles.", ephemeral=True)


class ColorsView(discord.ui.View):
    def __init__(self, guild: discord.Guild, mapping: Dict[str, List[int]]):
        super().__init__(timeout=None)
        all_ids = {rid for ids in mapping.values() for rid in ids}
        for key, label in COLOR_GROUPS_UI:
            filtered = [rid for rid in mapping.get(key, []) if guild.get_role(rid)]
            if filtered:
                self.add_item(ColorSelect(label, filtered, all_ids))
        if all_ids:
            self.add_item(ClearColorButton(all_ids))


class ColorRoles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="selfroles_colors_auto", description="Detecta roles de colores y los guarda.")
    @app_commands.describe(crear_faltantes="Si faltan roles básicos, crearlos.")
    async def colors_auto(self, interaction: discord.Interaction, crear_faltantes: bool = False):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            return await interaction.followup.send("Úsalo en un servidor.", ephemeral=True)

        data = ensure_db()
        groups = {key: [] for key, _ in COLOR_GROUPS_UI}
        guild = interaction.guild

        for role in guild.roles:
            group = guess_group(role.name)
            if group:
                groups[group].append(role.id)

        created = 0
        if crear_faltantes:
            for group, names in DEFAULT_NAMES.items():
                if groups[group]:
                    continue
                for name in names:
                    try:
                        new_role = await guild.create_role(name=name, reason="SelfRoles Colors Auto")
                        groups[group].append(new_role.id)
                        created += 1
                        await asyncio.sleep(0.2)
                    except discord.Forbidden:
                        pass

        data["groups"] = groups
        save_db(data)
        total = sum(len(ids) for ids in groups.values())
        faltantes = [label for key, label in COLOR_GROUPS_UI if not groups.get(key)]
        msg = [f"✅ Detectados {total} roles.", f"Creados: {created}."]
        if faltantes:
            msg.append("Grupos sin roles: " + ", ".join(faltantes))
        await interaction.followup.send("\n".join(msg), ephemeral=True)

    @app_commands.command(name="selfroles_colors_add", description="Añade un rol existente a un grupo de color.")
    @app_commands.choices(grupo=[app_commands.Choice(name=label, value=key) for key, label in COLOR_GROUPS_UI])
    async def colors_add(self, interaction: discord.Interaction, grupo: app_commands.Choice[str], rol: discord.Role):
        data = ensure_db()
        arr = data["groups"].setdefault(grupo.value, [])
        if rol.id not in arr:
            arr.append(rol.id)
            save_db(data)
        await interaction.response.send_message(f"➕ {rol.mention} añadido a **{dict(COLOR_GROUPS_UI)[grupo.value]}**.", ephemeral=True)

    @app_commands.command(name="selfroles_publish_colors", description="Publica el panel con los colores." )
    async def publish_colors(self, interaction: discord.Interaction, titulo: str = "Elige tu color", anclar: bool = True):
        if not interaction.guild:
            return await interaction.response.send_message("Úsalo en un servidor.", ephemeral=True)
        data = ensure_db()
        view = ColorsView(interaction.guild, data["groups"])
        if len(view.children) <= 1:
            return await interaction.response.send_message("No hay roles de color mapeados. Corre `/selfroles_colors_auto`.", ephemeral=True)
        embed = discord.Embed(
            title=titulo,
            description="1.- Elige tu color en el menú.\n2.- Usa 'Quitar icono' para limpiarlo si quieres cambiar.",
            color=discord.Color.blurple()
        )
        msg = await interaction.channel.send(embed=embed, view=view)  # type: ignore
        if anclar:
            with contextlib.suppress(discord.Forbidden):
                await msg.pin()
        await interaction.response.send_message("Panel de colores publicado ✅", ephemeral=True)
