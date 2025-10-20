import os, json, re, contextlib, difflib, unicodedata, io, asyncio
from pathlib import Path
from typing import List, Optional, Dict

import aiohttp
import discord
from PIL import Image
from discord.ext import commands
from discord import app_commands

CONFIG_PATH = "data/config.json"

def load_cfg():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_cfg(cfg):
    os.makedirs("data", exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def parse_role_list(guild: discord.Guild, text: str) -> List[int]:
    if not text:
        return []
    ids = set()
    for m in re.findall(r"<@&(\d+)>", text): ids.add(int(m))
    for m in re.findall(r"\b\d{15,20}\b", text): ids.add(int(m))
    for name in [t.strip() for t in re.split(r"[,\n]", text) if t.strip()]:
        r = discord.utils.find(lambda rr: rr.name.lower()==name.lower(), guild.roles)
        if r: ids.add(r.id)
    return list(ids)

def _parse_emoji(s: str):
    """Devuelve unicode o PartialEmoji a partir de una cadena."""
    if not s:
        return None
    try:
        return discord.PartialEmoji.from_str(s)
    except Exception:
        return s


def _load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _get_color_role_ids(cfg: dict) -> set[int]:
    return {int(x) for x in cfg.get("color_role_ids", [])}


class ConfigColorsSelect(discord.ui.Select):
    def __init__(self, title: str, options: list[discord.SelectOption], color_role_ids: set[int]):
        custom_id = f"selfroles:colors:{_normalize_color_text(title)[:80]}" or "selfroles:colors"
        super().__init__(placeholder=title[:100], min_values=1, max_values=1, options=options, custom_id=custom_id)
        self.color_role_ids = color_role_ids

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            return await interaction.response.send_message("Solo en servidores.", ephemeral=True)

        try:
            chosen_role_id = int(self.values[0])
        except (ValueError, IndexError):
            return await interaction.response.send_message("Selección inválida.", ephemeral=True)

        target_role = guild.get_role(chosen_role_id)
        if target_role is None:
            return await interaction.response.send_message("Ese rol ya no existe.", ephemeral=True)

        to_remove = [role for role in member.roles if role.id in self.color_role_ids and role.id != target_role.id]
        try:
            if to_remove:
                await member.remove_roles(*to_remove, reason="SelfRoles: cambio de color")
            if target_role not in member.roles:
                await member.add_roles(target_role, reason="SelfRoles: asignar color")
            await interaction.response.send_message(f"Color actualizado a **{target_role.name}**.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ No tengo permisos para gestionar roles de colores.", ephemeral=True)


class ConfigColorsView(discord.ui.View):
    def __init__(self, title: str, options: list[discord.SelectOption], color_role_ids: set[int]):
        super().__init__(timeout=None)
        self.add_item(ConfigColorsSelect(title, options, color_role_ids))


COLOR_ALIASES = {
    "amarillo": ["amarill"],
    "verde": ["verde"],
    "azul": ["azul"],
    "morado": ["morado", "violeta", "lila", "purp", "magenta"],
    "rosa": ["rosa", "pink", "fucs"],
    "blanco": ["blanc", "white"],
    "negro": ["negro", "black", "gris"],
}

HEX_HINTS = {
    "amarillo": ["#ffd", "#ff0", "ffd", "ffd200", "ffd96", "fff00"],
    "verde": ["#0f0", "#00ff00", "20bc9c", "2ecc71", "30d074", "70ff", "70fa"],
    "azul": ["#00f", "#0000ff", "389cdc", "92c5fc", "f7f9ff", "77f", "70f"],
    "morado": ["#80f", "#8000ff", "a05cb4", "a701eb", "743490", "d29bfd", "ccccff"],
    "rosa": ["#f08", "#ff0080", "ecc9dd", "fba0c7", "ff0080"],
    "blanco": ["#fff", "#ffffff"],
    "negro": ["#000", "#000000", "2f3136", "36393f"],
}


def _normalize_color_text(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    cleaned = re.sub(r"[^0-9A-Za-z#\s\-]+", " ", no_accents).lower()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def guess_color_group(role_name: str) -> Optional[str]:
    norm = _normalize_color_text(role_name)
    for group, tokens in COLOR_ALIASES.items():
        if any(tok in norm for tok in tokens):
            return group
    for group, hints in HEX_HINTS.items():
        if any(hint in norm for hint in hints):
            return group
    return None

ICON_PERSIST_FILE = Path("icon_roles.json")
TARGET_ICON_NAMES = [
    "Petme","Hugme","Gothic","Kawaii","Shy","Shyy","Dead",
    "Killyou","Yeii","Cutie","Cool","Otaku","Akatsuki","Sad",
    "Enojadizzza","Trizzzte","Felizzz","OK!","Softgirl","uwu","Carnalito"
]
ICON_ALIASES = {
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

def _canonical_icon_name(raw: str) -> str:
    low = raw.strip().lower()
    if low in ICON_ALIASES:
        return ICON_ALIASES[low]
    for name in TARGET_ICON_NAMES:
        if name.lower() == low:
            return name
    return raw.strip()

def _slug_icon_name(text: str) -> str:
    canonical = _canonical_icon_name(text)
    nfkd = unicodedata.normalize("NFKD", canonical)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    cleaned = re.sub(r"[^a-zA-Z0-9 ]+", " ", no_accents).lower()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

class IconResolver:
    def __init__(self):
        self.overrides: Dict[str, int] = {}
        self.mapping: Dict[str, int] = {}
        self.extra_names: List[str] = []
        if ICON_PERSIST_FILE.exists():
            try:
                data = json.loads(ICON_PERSIST_FILE.read_text())
                self.overrides = {k: int(v) for k, v in data.get("overrides", {}).items()}
                self.mapping = {k: int(v) for k, v in data.get("mapping", {}).items()}
                self.extra_names = data.get("extra_names", [])
            except Exception:
                self.overrides = {}
                self.mapping = {}
                self.extra_names = []

    def save(self):
        ICON_PERSIST_FILE.write_text(json.dumps({
            "overrides": self.overrides,
            "mapping": self.mapping,
            "extra_names": self.extra_names,
        }, indent=2))

    def names_pool(self) -> List[str]:
        pool = set(TARGET_ICON_NAMES) | set(self.overrides.keys()) | set(self.extra_names)
        return sorted(pool)

    def rebuild(self, guild: discord.Guild) -> List[str]:
        roles_by_slug: Dict[str, List[discord.Role]] = {}
        for role in guild.roles:
            roles_by_slug.setdefault(_slug_icon_name(role.name), []).append(role)

        found: Dict[str, int] = {}
        missing: List[str] = []

        for name in self.names_pool():
            canonical = _canonical_icon_name(name)
            override = self.overrides.get(canonical)
            if override:
                role = guild.get_role(override)
                if role:
                    found[canonical] = role.id
                    continue
            missing.append(canonical)

        still_missing: List[str] = []
        for name in missing:
            slug = _slug_icon_name(name)
            candidates = roles_by_slug.get(slug, [])
            if candidates:
                role = sorted(candidates, key=lambda r: r.position, reverse=True)[0]
                found[name] = role.id
            else:
                still_missing.append(name)

        really_missing: List[str] = []
        all_slugs = list(roles_by_slug.keys())
        for name in still_missing:
            slug = _slug_icon_name(name)
            best = difflib.get_close_matches(slug, all_slugs, n=1, cutoff=0.82)
            if best:
                role = sorted(roles_by_slug[best[0]], key=lambda r: r.position, reverse=True)[0]
                found[name] = role.id
            else:
                really_missing.append(name)

        self.mapping = found
        self.save()
        return really_missing

    async def create_missing(self, guild: discord.Guild, names: List[str]) -> List[str]:
        created_list: List[str] = []
        for name in names:
            try:
                role = await guild.create_role(name=name, reason="SelfRoles: crear faltante")
                self.overrides[name] = role.id
                created_list.append(name)
                await asyncio.sleep(0.2)
            except discord.Forbidden:
                pass
        self.save()
        return created_list

icon_resolver = IconResolver()

async def _fetch_bytes(url: str, timeout: int = 20) -> bytes:
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.read()

def _process_icon_bytes(raw: bytes, size: int = 96) -> bytes:
    image = Image.open(io.BytesIO(raw)).convert("RGBA")
    image.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x = (size - image.width) // 2
    y = (size - image.height) // 2
    canvas.paste(image, (x, y))
    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    return output.getvalue()

class _BaseSelectView(discord.ui.View):
    def __init__(self, cog: "SelfRoles", custom_id: str, placeholder: str):
        super().__init__(timeout=None)
        self.cog = cog
        select = discord.ui.Select(
            custom_id=custom_id,
            placeholder=placeholder,
            min_values=1, max_values=1,
            options=[discord.SelectOption(label="…", value="-1")],
        )
        async def _cb(interaction: discord.Interaction):
            value = interaction.data.get("values", ["-1"])[0]
            await self.on_value(interaction, value)
        select.callback = _cb
        self.add_item(select)

    async def on_value(self, interaction: discord.Interaction, value: str):
        raise NotImplementedError

class ColorsView(_BaseSelectView):
    def __init__(self, cog: "SelfRoles"):
        super().__init__(cog, "selfroles:colors", "Colores")
    async def on_value(self, interaction: discord.Interaction, value: str):
        await self.cog.handle_select(interaction, value, kind="colors")

class IconsView(_BaseSelectView):
    def __init__(self, cog: "SelfRoles"):
        super().__init__(cog, "selfroles:icons", "Iconos")
    async def on_value(self, interaction: discord.Interaction, value: str):
        await self.cog.handle_select(interaction, value, kind="icons")

class GroupSelect(discord.ui.Select):
    def __init__(self, cog: "SelfRoles", guild: discord.Guild, kind: str, role_ids: List[int], title: str):
        self.cog = cog
        self.kind = kind
        self.role_ids = role_ids

        options = [discord.SelectOption(label="Quitar selección", value="0", emoji="❌")]
        for rid in role_ids:
            role = guild.get_role(rid)
            if not role:
                continue
            label = cog.labels.get(kind, {}).get(str(role.id), role.name)[:100]
            emo_str = cog.emojis.get(kind, {}).get(str(role.id))
            emoji = _parse_emoji(emo_str) if emo_str else None
            options.append(discord.SelectOption(label=label, value=str(role.id), emoji=emoji))

        placeholder = title[:100] if title else "Selecciona una opción"
        custom_id = "selfroles:colors" if kind == "colors" else "selfroles:icons"
        super().__init__(custom_id=custom_id, placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0] if self.values else None
        await self.cog.handle_group_select(interaction, selected, self.role_ids, self.kind)

class GroupView(discord.ui.View):
    def __init__(self, cog: "SelfRoles", guild: discord.Guild, kind: str, role_ids: List[int], title: str):
        super().__init__(timeout=None)
        self.add_item(GroupSelect(cog, guild, kind, role_ids, title))


class IconMenuSelect(discord.ui.Select):
    def __init__(self, mapping: Dict[str, int]):
        options = [discord.SelectOption(label=name, value=str(role_id)) for name, role_id in sorted(mapping.items())]
        super().__init__(placeholder="Elige tu icono", min_values=1, max_values=1, options=options, custom_id="selfroles:icon_menu")
        self.icon_ids = set(mapping.values())

    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        role = interaction.guild.get_role(role_id)
        if not role:
            return await interaction.response.send_message("❌ Rol no encontrado.", ephemeral=True)
        to_remove = [r for r in interaction.user.roles if r.id in self.icon_ids and r.id != role_id]
        try:
            if to_remove:
                await interaction.user.remove_roles(*to_remove, reason="Cambio de icono")
            await interaction.user.add_roles(role, reason="Asignación de icono")
            await interaction.response.send_message(f"Icono cambiado a **{role.name}**.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ No tengo permisos para gestionar esos roles.", ephemeral=True)


class IconMenuRemoveButton(discord.ui.Button):
    def __init__(self, icon_ids: set[int]):
        super().__init__(label="Quitar icono", style=discord.ButtonStyle.danger, custom_id="selfroles:icon_remove")
        self.icon_ids = icon_ids

    async def callback(self, interaction: discord.Interaction):
        to_remove = [r for r in interaction.user.roles if r.id in self.icon_ids]
        if not to_remove:
            return await interaction.response.send_message("No tienes icono activo.", ephemeral=True)
        try:
            await interaction.user.remove_roles(*to_remove, reason="Quitar icono")
            await interaction.response.send_message("Icono quitado.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ No pude quitar el rol.", ephemeral=True)


class IconMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.refresh()

    def refresh(self):
        self.clear_items()
        if not icon_resolver.mapping:
            self.add_item(discord.ui.Button(label="Sin iconos configurados", custom_id="selfroles:icon_empty", disabled=True))
            return
        self.add_item(IconMenuSelect(icon_resolver.mapping))
        self.add_item(IconMenuRemoveButton(set(icon_resolver.mapping.values())))

class SelfRoles(commands.Cog):
    """
    Menús de auto-roles para Colores e Iconos (solo Server Boosters),
    con emojis/labels personalizados y imagen por lista.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cfg = load_cfg()

        self.color_role_ids: List[int] = self.cfg.get("color_role_ids", [])
        self.icon_role_ids:  List[int] = self.cfg.get("icon_role_ids", [])
        self.booster_role_id: int = int(self.cfg.get("booster_role_id") or 0)

        self.labels: Dict[str, Dict[str, str]] = self.cfg.get(
            "selfroles_labels", {"colors": {}, "icons": {}}
        )
        self.emojis: Dict[str, Dict[str, str]] = self.cfg.get(
            "selfroles_emojis", {"colors": {}, "icons": {}}
        )
        self.images: Dict[str, Dict[str, str]] = self.cfg.get(
            "selfroles_images", {"colors": {}, "icons": {}}
        )
        self.groups: Dict[str, List[dict]] = self.cfg.get(
            "selfroles_groups", {"colors": [], "icons": []}
        )

        bot.add_view(ColorsView(self))
        bot.add_view(IconsView(self))
        self.icon_menu_view = IconMenuView()
        bot.add_view(self.icon_menu_view)
        icon_resolver.save()
        self.icon_resolver = icon_resolver

    def _save_cfg(self):
        self.cfg["color_role_ids"] = self.color_role_ids
        self.cfg["icon_role_ids"]  = self.icon_role_ids
        self.cfg["selfroles_labels"] = self.labels
        self.cfg["selfroles_emojis"] = self.emojis
        self.cfg["selfroles_images"] = self.images
        self.cfg["selfroles_groups"] = self.groups
        save_cfg(self.cfg)

    def _roles_from_ids(self, guild: discord.Guild, ids: List[int]) -> List[discord.Role]:
        out = []
        for rid in ids:
            r = guild.get_role(int(rid))
            if r:
                out.append(r)
        return out

    @staticmethod
    def _chunk(seq: List, size: int):
        return [seq[i:i+size] for i in range(0, len(seq), size)]

    def _normalize_ids(self, guild: discord.Guild, roles_spec: str) -> List[int]:
        ids = parse_role_list(guild, roles_spec)
        seen = set()
        ordered: List[int] = []
        for rid in ids:
            if rid not in seen:
                seen.add(rid)
                ordered.append(rid)
        return ordered

    async def _send_ephemeral(self, interaction: discord.Interaction, message: str):
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    async def _purge_old_menus(self, channel: discord.TextChannel, kind: str, limit: int = 200):
        custom_id = "selfroles:colors" if kind == "colors" else "selfroles:icons"
        to_delete = []
        async for message in channel.history(limit=limit):
            if message.author.id != self.bot.user.id:
                continue
            has_menu = False
            for row in getattr(message, "components", []) or []:
                for comp in getattr(row, "children", []):
                    if getattr(comp, "custom_id", "") == custom_id:
                        has_menu = True
                        break
                if has_menu:
                    break
            if has_menu:
                to_delete.append(message)
        if to_delete:
            try:
                await channel.delete_messages(to_delete)
            except discord.HTTPException:
                for msg in to_delete:
                    with contextlib.suppress(discord.HTTPException):
                        await msg.delete()

    async def _publish_menus(self, channel: discord.TextChannel, roles: List[discord.Role], kind: str):
        if not roles:
            await channel.send(f"⚠️ No hay roles configurados para **{kind}**.")
            return

        chunks = self._chunk(roles, 24)
        for idx, group in enumerate(chunks, start=1):
            options = [discord.SelectOption(label="Quitar selección", value="0", emoji="❌")]
            for r in group:
                label = self.labels.get(kind, {}).get(str(r.id), r.name)[:100]
                em_value = self.emojis.get(kind, {}).get(str(r.id))
                emoji = _parse_emoji(em_value) if em_value else None
                options.append(discord.SelectOption(label=label, value=str(r.id), emoji=emoji))

            view = discord.ui.View(timeout=None)
            custom_id = "selfroles:colors" if kind == "colors" else "selfroles:icons"
            select = discord.ui.Select(
                custom_id=custom_id,
                placeholder=f"{'Colores' if kind=='colors' else 'Iconos'} · Lista {idx}",
                min_values=1, max_values=1, options=options
            )
            async def _cb(interaction: discord.Interaction, *_ , _kind=kind):
                value = interaction.data.get("values", ["-1"])[0]
                await self.handle_select(interaction, value, kind=_kind)
            select.callback = _cb
            view.add_item(select)

            title = "Colores" if kind == "colors" else "Iconos"
            embed = discord.Embed(
                title=f"{title} · Lista {idx}",
                description=("Selecciona una opción.\n"
                             "🔒 **Solo Server Boosters.**\n"
                             "Se quitará tu selección anterior del mismo grupo."),
                color=discord.Color.blurple()
            )
            img_url = self.images.get(kind, {}).get(str(idx))
            if img_url:
                embed.set_image(url=img_url)

            await channel.send(embed=embed, view=view)

    async def handle_select(self, interaction: discord.Interaction, value: str, *, kind: str):
        user = interaction.user
        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message("Solo en servidor.", ephemeral=True)

        if not self.booster_role_id or not any(r.id == self.booster_role_id for r in user.roles):
            return await interaction.response.send_message("🔒 Solo para **Server Boosters**.", ephemeral=True)

        available_ids = set(self.color_role_ids if kind=="colors" else self.icon_role_ids)

        if value == "0":
            to_remove = [r for r in user.roles if r.id in available_ids]
            if not to_remove:
                return await interaction.response.send_message("No tienes ninguna selección que quitar.", ephemeral=True)
            try:
                await user.remove_roles(*to_remove, reason=f"Quitar {kind}")
            except discord.Forbidden:
                return await interaction.response.send_message("No puedo quitarte roles aquí (permisos).", ephemeral=True)
            return await interaction.response.send_message("✅ Selección eliminada.", ephemeral=True)

        try:
            target_id = int(value)
        except ValueError:
            return await interaction.response.send_message("Opción inválida.", ephemeral=True)

        role = guild.get_role(target_id)
        if not role or role.id not in available_ids:
            return await interaction.response.send_message("Opción inválida.", ephemeral=True)

        to_remove = [r for r in user.roles if r.id in available_ids and r.id != role.id]
        try:
            if to_remove:
                await user.remove_roles(*to_remove, reason=f"Reemplazar {kind}")
            if role not in user.roles:
                await user.add_roles(role, reason=f"SelfRole {kind}")
        except discord.Forbidden:
            return await interaction.response.send_message("No tengo permisos para asignarte ese rol.", ephemeral=True)

        label = self.labels.get(kind, {}).get(str(role.id), role.name)
        await interaction.response.send_message(f"✅ Seleccionado: **{label}**", ephemeral=True)

    async def handle_group_select(self, interaction: discord.Interaction, selected_value: Optional[str], role_ids: List[int], kind: str):
        guild = interaction.guild
        user = interaction.user
        if guild is None or not isinstance(user, discord.Member):
            return

        if self.booster_role_id and not any(r.id == self.booster_role_id for r in user.roles):
            return await self._send_ephemeral(interaction, "🔒 Solo para **Server Boosters**.")

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=False)

        available_ids = set(role_ids)
        try:
            if not selected_value or selected_value == "0":
                to_remove = [r for r in user.roles if r.id in available_ids]
                if to_remove:
                    await user.remove_roles(*to_remove, reason=f"Quitar {kind}")
                return

            try:
                target_id = int(selected_value)
            except ValueError:
                return

            target_role = guild.get_role(target_id)
            if not target_role or target_role.id not in available_ids:
                return

            to_remove = [r for r in user.roles if r.id in available_ids and r.id != target_role.id]
            if to_remove:
                await user.remove_roles(*to_remove, reason=f"Reemplazar {kind}")
            if target_role not in user.roles:
                await user.add_roles(target_role, reason=f"SelfRole {kind}")
        except discord.Forbidden:
            await interaction.followup.send("No tengo permisos para asignarte ese rol.", ephemeral=True)
        except discord.HTTPException as exc:
            await interaction.followup.send(f"No se pudo aplicar el rol: `{exc}`", ephemeral=True)

    async def _publish_custom_menu(
        self,
        interaction: discord.Interaction,
        *,
        title: str,
        roles_spec: str,
        kind: str,
        channel: Optional[discord.TextChannel] = None,
        image_url: Optional[str] = None,
        image: Optional[discord.Attachment] = None,
        respond: bool = True,
    ):
        if not interaction.user.guild_permissions.manage_channels:
            return await self._send_ephemeral(interaction, "Requiere **Manage Channels**.")

        ch = channel or interaction.channel
        ids = parse_role_list(interaction.guild, roles_spec)
        roles = self._roles_from_ids(interaction.guild, ids)
        if not roles:
            return await interaction.response.send_message("No pude reconocer roles.", ephemeral=True)

        options = [discord.SelectOption(label="Quitar selección", value="0", emoji="❌")]
        for r in roles:
            label = self.labels.get(kind, {}).get(str(r.id), r.name)[:100]
            emo_str = self.emojis.get(kind, {}).get(str(r.id))
            emoji = _parse_emoji(emo_str) if emo_str else None
            options.append(discord.SelectOption(label=label, value=str(r.id), emoji=emoji))

        view = discord.ui.View(timeout=None)
        custom_id = "selfroles:colors" if kind == "colors" else "selfroles:icons"
        select = discord.ui.Select(custom_id=custom_id, placeholder=title, min_values=1, max_values=1, options=options)

        async def _cb(inter: discord.Interaction, _kind=kind):
            value = inter.data.get("values", ["-1"])[0]
            await self.handle_select(inter, value, kind=_kind)

        select.callback = _cb
        view.add_item(select)

        embed = discord.Embed(
            title=title,
            description=("Selecciona una opción. 🔒 **Solo Server Boosters**.\n"
                         "Al elegir, se quitará tu selección anterior del mismo grupo."),
            color=discord.Color.blurple()
        )
        url = (image.url if image else None) or (image_url.strip() if image_url else None)
        if url:
            embed.set_image(url=url)

        await ch.send(embed=embed, view=view)
        if respond:
            msg = f"✅ Publicado: **{title}**"
            await self._send_ephemeral(interaction, msg)

    group = app_commands.Group(name="selfroles", description="Gestiona menús de Colores/Iconos (solo Boosters)")
    icons_manage = app_commands.Group(name="icons", description="Configura iconos dinámicos", parent=group)

    @group.command(name="colors-setup", description="Configura la lista de roles de Color")
    @app_commands.describe(roles="Menciona o escribe IDs/nombres separados por coma")
    async def colors_setup(self, interaction: discord.Interaction, roles: str):
        if not interaction.user.guild_permissions.manage_roles:
            return await interaction.response.send_message("Requiere **Manage Roles**.", ephemeral=True)
        ids = parse_role_list(interaction.guild, roles)
        if not ids:
            return await interaction.response.send_message("No pude reconocer roles.", ephemeral=True)
        self.color_role_ids = ids
        self._save_cfg()
        await interaction.response.send_message(f"✅ Guardados {len(ids)} roles de **colores**.", ephemeral=True)

    @group.command(name="colors-auto", description="Detecta roles de colores por nombre/hex y los carga automáticamente.")
    async def colors_auto(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_roles:
            return await interaction.response.send_message("Requiere **Manage Roles**.", ephemeral=True)
        guild = interaction.guild
        matched_ids: List[int] = []
        matched_groups = set()
        for role in guild.roles:
            group = guess_color_group(role.name)
            if group:
                matched_ids.append(role.id)
                matched_groups.add(group)
        if not matched_ids:
            return await interaction.response.send_message("No encontré roles de colores por nombre/hex. Ajusta los nombres o usa el modo manual.", ephemeral=True)
        seen = set()
        unique_ids = []
        for rid in matched_ids:
            if rid not in seen:
                seen.add(rid)
                unique_ids.append(rid)
        self.color_role_ids = unique_ids
        self._save_cfg()
        all_groups = set(COLOR_ALIASES.keys())
        missing_groups = sorted(all_groups - matched_groups)
        mensaje = [f"✅ Detectados {len(unique_ids)} roles para colores."]
        if missing_groups:
            mensaje.append("Grupos sin coincidencias: " + ", ".join(missing_groups))
        await interaction.response.send_message("\n".join(mensaje), ephemeral=True)

    @group.command(name="icons-setup", description="Configura la lista de roles de Icono")
    @app_commands.describe(roles="Menciona o escribe IDs/nombres separados por coma")
    async def icons_setup(self, interaction: discord.Interaction, roles: str):
        if not interaction.user.guild_permissions.manage_roles:
            return await interaction.response.send_message("Requiere **Manage Roles**.", ephemeral=True)
        ids = parse_role_list(interaction.guild, roles)
        if not ids:
            return await interaction.response.send_message("No pude reconocer roles.", ephemeral=True)
        self.icon_role_ids = ids
        self._save_cfg()
        await interaction.response.send_message(f"✅ Guardados {len(ids)} roles de **iconos**.", ephemeral=True)

    @group.command(name="set-label", description="Define etiqueta personalizada para un rol")
    @app_commands.describe(kind="colors o icons", role="Rol objetivo", label="Texto a mostrar")
    async def set_label(self, interaction: discord.Interaction, kind: str, role: discord.Role, label: str):
        if kind not in ("colors", "icons"):
            return await interaction.response.send_message("kind debe ser **colors** o **icons**.", ephemeral=True)
        if not interaction.user.guild_permissions.manage_roles:
            return await interaction.response.send_message("Requiere **Manage Roles**.", ephemeral=True)
        self.labels.setdefault(kind, {})[str(role.id)] = label[:100]
        self._save_cfg()
        await interaction.response.send_message(f"✅ Label guardado para **{role.name}**.", ephemeral=True)

    @group.command(name="set-emoji", description="Define emoji (unicode o <:name:id>) para un rol")
    @app_commands.describe(kind="colors o icons", role="Rol objetivo", emoji="Unicode o <:name:id>")
    async def set_emoji(self, interaction: discord.Interaction, kind: str, role: discord.Role, emoji: str):
        if kind not in ("colors", "icons"):
            return await interaction.response.send_message("kind debe ser **colors** o **icons**.", ephemeral=True)
        if not interaction.user.guild_permissions.manage_roles:
            return await interaction.response.send_message("Requiere **Manage Roles**.", ephemeral=True)
        self.emojis.setdefault(kind, {})[str(role.id)] = emoji.strip()
        self._save_cfg()
        await interaction.response.send_message(f"✅ Emoji guardado para **{role.name}**.", ephemeral=True)

    @group.command(name="clear-display", description="Borra etiqueta/emoji personalizados de un rol")
    @app_commands.describe(kind="colors o icons", role="Rol objetivo")
    async def clear_display(self, interaction: discord.Interaction, kind: str, role: discord.Role):
        if kind not in ("colors", "icons"):
            return await interaction.response.send_message("kind debe ser **colors** o **icons**.", ephemeral=True)
        if not interaction.user.guild_permissions.manage_roles:
            return await interaction.response.send_message("Requiere **Manage Roles**.", ephemeral=True)
        self.labels.get(kind, {}).pop(str(role.id), None)
        self.emojis.get(kind, {}).pop(str(role.id), None)
        self._save_cfg()
        await interaction.response.send_message(f"✅ Display limpio para **{role.name}**.", ephemeral=True)

    @group.command(name="set-list-image", description="Define imagen para una lista (1,2,3...)")
    @app_commands.describe(
        kind="colors o icons",
        index="Número de lista (1,2,3… según publicación)",
        image_url="URL (opcional si adjuntas imagen)",
        image="Adjunta imagen para usar su URL"
    )
    async def set_list_image(
        self,
        interaction: discord.Interaction,
        kind: str,
        index: int,
        image_url: Optional[str] = None,
        image: Optional[discord.Attachment] = None
    ):
        if kind not in ("colors", "icons"):
            return await interaction.response.send_message("kind debe ser **colors** o **icons**.", ephemeral=True)
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("Requiere **Manage Channels**.", ephemeral=True)
        url = (image.url if image else None) or (image_url.strip() if image_url else None)
        if not url:
            return await interaction.response.send_message("Debes adjuntar imagen o pasar una URL.", ephemeral=True)
        self.images.setdefault(kind, {})[str(max(1, index))] = url
        self._save_cfg()
        await interaction.response.send_message(f"✅ Imagen guardada para **{kind} lista {index}**.", ephemeral=True)

    @group.command(name="publish-colors", description="Publica los menús de colores con instrucciones únicas")
    async def publish_colors(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("Requiere **Manage Channels**.", ephemeral=True)

        cfg = _load_config()
        groups = cfg.get("selfroles_groups", {}).get("colors", [])
        if not groups:
            return await interaction.response.send_message(
                "No hay grupos de colores en `selfroles_groups.colors`.",
                ephemeral=True,
            )

        color_role_ids = _get_color_role_ids(cfg)
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        channel = interaction.channel

        instrucciones = (
            "**Instrucciones:**\n"
            "1.- Haz click en la imagen o lista para ver los nombres y elige el color que deseas.\n"
            " -\n"
            "2.- Para cambiar de color, primero quítate el anterior (botón 'Quitar icono') o elige otro en la misma lista.\n"
            " -"
        )
        embed = discord.Embed(description=instrucciones, color=discord.Color.blurple())
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())  # type: ignore
        published = 0

        for group in groups:
            title = str(group.get("title", "Colores")).replace('"', "").strip() or "Colores"
            role_ids = [int(rid) for rid in group.get("role_ids", [])]
            roles = [guild.get_role(rid) for rid in role_ids if guild.get_role(rid)]
            if not roles:
                continue

            color_role_ids.update(role.id for role in roles)
            menciones = " - ".join(role.mention for role in roles)
            options = [discord.SelectOption(label=role.name[:100], value=str(role.id)) for role in roles]
            view = ConfigColorsView(title, options, color_role_ids)

            await channel.send(
                content=menciones,
                view=view,
                allowed_mentions=discord.AllowedMentions.none()
            )  # type: ignore
            published += 1

        if published == 0:
            await interaction.followup.send(
                "No se publicó ningún grupo porque ninguno tiene roles válidos.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"Listas de colores publicadas: {published}.",
                ephemeral=True,
            )

    @group.command(name="publish-icons", description="Publica los menús de iconos")
    @app_commands.describe(channel="Canal destino (por defecto, actual)")
    async def publish_icons(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("Requiere **Manage Channels**.", ephemeral=True)
        ch = channel or interaction.channel
        roles = self._roles_from_ids(interaction.guild, self.icon_role_ids)
        await self._publish_menus(ch, roles, "icons")
        await interaction.response.send_message("✅ Menús de **iconos** publicados.", ephemeral=True)

    @group.command(name="publish-colors-group", description="Publica un menú de colores con un título/imagen")
    @app_commands.describe(
        title="Título del menú (ej: Colores Rojos)",
        roles="Menciona/IDs/nombres separados por coma",
        channel="Canal destino (opcional)",
        image_url="URL de imagen (opcional)",
        image="Adjunta imagen (opcional)"
    )
    async def publish_colors_group(
        self,
        interaction: discord.Interaction,
        title: str,
        roles: str,
        channel: Optional[discord.TextChannel] = None,
        image_url: Optional[str] = None,
        image: Optional[discord.Attachment] = None
    ):
        await self._publish_custom_menu(
            interaction, title=title, roles_spec=roles, kind="colors",
            channel=channel, image_url=image_url, image=image
        )

    @group.command(name="publish-icons-group", description="Publica un menú de iconos con un título/imagen")
    @app_commands.describe(
        title="Título del menú (ej: Iconos Lista 1)",
        roles="Menciona/IDs/nombres separados por coma",
        channel="Canal destino (opcional)",
        image_url="URL de imagen (opcional)",
        image="Adjunta imagen (opcional)"
    )
    async def publish_icons_group(
        self,
        interaction: discord.Interaction,
        title: str,
        roles: str,
        channel: Optional[discord.TextChannel] = None,
        image_url: Optional[str] = None,
        image: Optional[discord.Attachment] = None
    ):
        await self._publish_custom_menu(
            interaction, title=title, roles_spec=roles, kind="icons",
            channel=channel, image_url=image_url, image=image
        )

    @icons_manage.command(name="upload", description="Crea o actualiza un icono con imagen y lo agrega al menú.")
    @app_commands.describe(
        nombre="Nombre visible del icono",
        imagen="Adjunta la imagen del icono (PNG/JPG/GIF)",
        url="URL directa de imagen (opcional si no adjuntas)",
        color_hex="Color opcional del rol (formato #RRGGBB)",
        mover_arriba="Intenta mover el rol debajo del rol del bot"
    )
    @app_commands.default_permissions(administrator=True)
    async def icons_upload(
        self,
        interaction: discord.Interaction,
        nombre: str,
        imagen: Optional[discord.Attachment] = None,
        url: Optional[str] = None,
        color_hex: Optional[str] = None,
        mover_arriba: bool = True
    ):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None:
            return await self._send_ephemeral(interaction, "Este comando solo funciona en servidores.")

        if "ROLE_ICONS" not in guild.features:
            return await self._send_ephemeral(interaction, "⚠️ Tu servidor no tiene **Role Icons** habilitado.")

        raw = None
        try:
            if imagen:
                raw = await imagen.read()
            elif url:
                raw = await _fetch_bytes(url)
            else:
                return await self._send_ephemeral(interaction, "Adjunta una imagen o proporciona una URL.")
        except Exception as exc:
            return await self._send_ephemeral(interaction, f"No pude descargar la imagen: {exc}")

        try:
            icon_bytes = _process_icon_bytes(raw)
        except Exception as exc:
            return await self._send_ephemeral(interaction, f"Error procesando imagen: {exc}")

        canonical = _canonical_icon_name(nombre)
        target_slug = _slug_icon_name(canonical)
        role = discord.utils.find(lambda r: _slug_icon_name(r.name) == target_slug, guild.roles)
        created = False
        if not role:
            kwargs = {}
            if color_hex:
                try:
                    kwargs["colour"] = discord.Colour.from_str(color_hex)
                except ValueError:
                    pass
            role = await guild.create_role(name=canonical, reason="SelfRoles: icon upload", **kwargs)
            created = True

        try:
            edit_kwargs = {"display_icon": icon_bytes}
            if color_hex:
                try:
                    edit_kwargs["colour"] = discord.Colour.from_str(color_hex)
                except ValueError:
                    pass
            await role.edit(**edit_kwargs, reason="SelfRoles: establecer icono")
        except discord.Forbidden:
            return await self._send_ephemeral(interaction, "No tengo permisos para editar ese rol.")
        except Exception as exc:
            return await self._send_ephemeral(interaction, f"No pude aplicar el icono: {exc}")

        if mover_arriba:
            bot_member = guild.get_member(self.bot.user.id)
            if bot_member and bot_member.top_role and bot_member.top_role.position > role.position:
                try:
                    await role.edit(position=bot_member.top_role.position - 1, reason="SelfRoles: ordenar icono")
                except discord.Forbidden:
                    pass

        if canonical not in TARGET_ICON_NAMES and canonical not in icon_resolver.extra_names:
            icon_resolver.extra_names.append(canonical)
        icon_resolver.overrides[canonical] = role.id
        icon_resolver.rebuild(guild)
        self.icon_menu_view.refresh()

        status = "creado" if created else "actualizado"
        await self._send_ephemeral(interaction, f"Rol **{role.name}** {status} y agregado al menú.")

    @icons_manage.command(name="auto", description="Detecta roles existentes por nombre y actualiza el menú.")
    @app_commands.describe(crear_faltantes="Crear roles faltantes si es posible")
    @app_commands.default_permissions(administrator=True)
    async def icons_auto(self, interaction: discord.Interaction, crear_faltantes: bool = False):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None:
            return await self._send_ephemeral(interaction, "Este comando solo funciona en servidores.")
        missing = icon_resolver.rebuild(guild)
        created: List[str] = []
        if crear_faltantes and missing:
            created = await icon_resolver.create_missing(guild, missing)
            missing = icon_resolver.rebuild(guild)
        self.icon_menu_view.refresh()
        resumen = [
            f"Encontrados: {len(icon_resolver.mapping)}",
            f"Overrides: {len(icon_resolver.overrides)}",
            f"Faltantes: {len(missing)}",
        ]
        if created:
            resumen.append("Creados: " + ", ".join(created))
        if missing:
            resumen.append("No hallados: " + ", ".join(missing))
        await interaction.followup.send("\n".join(resumen), ephemeral=True)

    @icons_manage.command(name="view", description="Muestra el mapeo actual de iconos.")
    @app_commands.default_permissions(administrator=True)
    async def icons_view(self, interaction: discord.Interaction):
        if not icon_resolver.mapping:
            return await self._send_ephemeral(interaction, "Aún no hay iconos configurados.")
        lines = [f"- {name} → <@&{rid}>" for name, rid in sorted(icon_resolver.mapping.items())]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @icons_manage.command(name="clear", description="Borra el mapeo y overrides de iconos.")
    @app_commands.default_permissions(administrator=True)
    async def icons_clear(self, interaction: discord.Interaction):
        icon_resolver.overrides.clear()
        icon_resolver.mapping.clear()
        icon_resolver.extra_names.clear()
        icon_resolver.save()
        self.icon_menu_view.refresh()
        await self._send_ephemeral(interaction, "Configuración de iconos limpiada.")

    @icons_manage.command(name="publish", description="Publica el menú de iconos actual en este canal.")
    @app_commands.describe(titulo="Título opcional", imagen="Imagen opcional del catálogo")
    @app_commands.default_permissions(administrator=True)
    async def icons_publish(self, interaction: discord.Interaction, titulo: Optional[str] = None, imagen: Optional[discord.Attachment] = None):
        if not icon_resolver.mapping:
            return await self._send_ephemeral(interaction, "Configura iconos antes de publicar.")
        embed = discord.Embed(
            title=titulo or "Iconos",
            description="Elige un icono en el menú. Usa el botón rojo para quitarlo.",
            color=0x5865F2
        )
        if imagen:
            file = await imagen.to_file()
            embed.set_image(url=f"attachment://{file.filename}")
            await interaction.response.send_message(embed=embed, file=file, view=self.icon_menu_view)
        else:
            await interaction.response.send_message(embed=embed, view=self.icon_menu_view)
    @group.command(name="group-add", description="Agrega o actualiza un grupo de roles")
    @app_commands.describe(
        kind="colors o icons",
        title="Título del grupo (ej: Colores Rojos)",
        roles="Menciona/IDs/nombres separados por coma",
        position="Posición (1..N) opcional",
        image_url="URL de imagen (opcional)",
        image="Adjunta imagen (opcional)"
    )
    async def group_add(
        self,
        interaction: discord.Interaction,
        kind: str,
        title: str,
        roles: str,
        position: Optional[int] = None,
        image_url: Optional[str] = None,
        image: Optional[discord.Attachment] = None
    ):
        if kind not in ("colors", "icons"):
            return await interaction.response.send_message("kind debe ser **colors** o **icons**.", ephemeral=True)
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("Requiere **Manage Channels**.", ephemeral=True)

        ids = self._normalize_ids(interaction.guild, roles)
        if not ids:
            return await interaction.response.send_message("No pude reconocer roles.", ephemeral=True)

        url = (image.url if image else None) or (image_url.strip() if image_url else None)
        arr = self.groups.setdefault(kind, [])
        for group in arr:
            if group.get("title") == title:
                group["role_ids"] = ids
                group["image_url"] = url
                self._save_cfg()
                return await interaction.response.send_message(
                    f"✅ Grupo **{title}** actualizado ({len(ids)} roles).", ephemeral=True
                )

        payload = {"title": title, "role_ids": ids, "image_url": url}
        if position and 1 <= position <= len(arr) + 1:
            arr.insert(position - 1, payload)
        else:
            arr.append(payload)
        self._save_cfg()
        await interaction.response.send_message(
            f"✅ Grupo **{title}** guardado ({len(ids)} roles).", ephemeral=True
        )

    @group.command(name="group-clear", description="Elimina todos los grupos guardados del tipo indicado")
    @app_commands.describe(kind="colors o icons")
    async def group_clear(self, interaction: discord.Interaction, kind: str):
        if kind not in ("colors", "icons"):
            return await interaction.response.send_message("kind debe ser **colors** o **icons**.", ephemeral=True)
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("Requiere **Manage Channels**.", ephemeral=True)
        self.groups[kind] = []
        self._save_cfg()
        await interaction.response.send_message(f"🗑️ Grupos de **{kind}** eliminados.", ephemeral=True)

    @group.command(name="publish-groups", description="Publica todos los grupos guardados en orden")
    @app_commands.describe(
        kind="colors o icons",
        channel="Canal destino (por defecto, actual)",
        purge_before="Borrar menús previos del bot en este canal"
    )
    async def publish_groups(
        self,
        interaction: discord.Interaction,
        kind: str,
        channel: Optional[discord.TextChannel] = None,
        purge_before: Optional[bool] = False
    ):
        if kind not in ("colors", "icons"):
            return await interaction.response.send_message("kind debe ser **colors** o **icons**.", ephemeral=True)
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("Requiere **Manage Channels**.", ephemeral=True)

        ch = channel or interaction.channel
        if not isinstance(ch, discord.TextChannel):
            return await interaction.response.send_message("Canal inválido.", ephemeral=True)

        groups = self.groups.get(kind, [])
        if not groups:
            return await interaction.response.send_message("No hay grupos guardados.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        if purge_before:
            await self._purge_old_menus(ch, kind)

        title = "¡Te damos la bienvenida a #『📌』colores!" if kind == "colors" else "¡Iconos!"
        desc = (
            "Selecciona un rol en el menú correspondiente.\n"
            "Puedes quitar tu selección con la opción ❌.\n"
            "🔒 **Solo para Server Boosters.**"
        )
        await ch.send(embed=discord.Embed(title=title, description=desc, color=discord.Color.blurple()))

        guild = interaction.guild
        for group in groups:
            role_ids: List[int] = []
            for rid in group.get("role_ids", []):
                try:
                    role_ids.append(int(rid))
                except (TypeError, ValueError):
                    continue
            if not role_ids:
                continue
            roles = []
            for rid in role_ids:
                role = guild.get_role(int(rid))
                if role:
                    roles.append(role)
            if not roles:
                continue

            title = group.get("title", "Grupo")
            header = f"**{title}**\n" + " - ".join(role.mention for role in roles)
            view = GroupView(self, guild, kind, [role.id for role in roles], title)
            await ch.send(content=header, view=view)

        await interaction.followup.send(
            f"✅ Publicados **{len(groups)}** grupos de **{kind}** en {ch.mention}.",
            ephemeral=True
        )

async def setup(bot: commands.Bot):
    cog = SelfRoles(bot)
    await bot.add_cog(cog)
    gid = os.getenv("GUILD_ID")
    gobj = discord.Object(id=int(gid)) if gid and gid.isdigit() else None
    if gobj:
        try:
            bot.tree.add_command(cog.group, guild=gobj)
        except app_commands.CommandAlreadyRegistered:
            bot.tree.remove_command(cog.group.name, guild=gobj)
            bot.tree.add_command(cog.group, guild=gobj)
