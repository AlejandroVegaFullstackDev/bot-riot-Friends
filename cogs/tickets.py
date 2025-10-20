import os, re, json, asyncio
from typing import List, Optional
import discord
from discord.ext import commands
from discord import app_commands
from discord.errors import Forbidden, NotFound, HTTPException

CONFIG_PATH = "data/config.json"
TICKETS_PATH = "data/tickets.json"

def load_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def parse_role_list(guild: discord.Guild, text: str) -> List[int]:
    """Acepta menciones <@&id>, IDs o nombres separados por coma."""
    if not text: return []
    ids = set()
    for m in re.findall(r"<@&(\d+)>", text): ids.add(int(m))
    for m in re.findall(r"\b\d{15,20}\b", text): ids.add(int(m))
    for name in [t.strip() for t in re.split(r"[,\n]", text) if t.strip()]:
        r = discord.utils.find(lambda rr: rr.name.lower()==name.lower(), guild.roles)
        if r: ids.add(r.id)
    return list(ids)

async def _safe_first_response(interaction: discord.Interaction, content: str, *, ephemeral: bool = True):
    """Envía respuesta única sin importar si ya se respondió/defer."""
    try:
        if interaction.response.is_done():
            await interaction.followup.send(content, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(content, ephemeral=ephemeral)
    except Exception:
        try:
            await interaction.followup.send(content, ephemeral=ephemeral)
        except Exception:
            pass

async def _defer_once(interaction: discord.Interaction, *, ephemeral: bool = True):
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=ephemeral, thinking=True)

class TicketControlsView(discord.ui.View):
    """Controles persistentes para tickets abiertos."""
    def __init__(self, cog: "Tickets"):
        super().__init__(timeout=None)
        self.cog = cog
        self.add_item(discord.ui.Button(
            label="Cerrar",
            emoji="🔒",
            style=discord.ButtonStyle.success,
            custom_id="tickets:close"
        ))
        self.add_item(discord.ui.Button(
            label="Borrar",
            emoji="🗑️",
            style=discord.ButtonStyle.danger,
            custom_id="tickets:delete"
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        cid = (interaction.data or {}).get("custom_id")
        if cid == "tickets:close":
            await self.cog.ticket_close_core(interaction)
            return False
        if cid == "tickets:delete":
            await self.cog.ticket_delete_core(interaction)
            return False
        return True

class TicketPanelView(discord.ui.View):
    """Panel principal con menú de motivos y botones."""
    def __init__(self, cog: commands.Cog, reasons: list[str] | None = None):
        super().__init__(timeout=None)
        self.cog = cog
        self.reasons = reasons or ["Soporte", "Reporte", "Apelación", "Compras", "Otros"]
        self._choice: dict[int, str] = {}

        opts = [discord.SelectOption(label=r) for r in self.reasons[:25]]
        self.select = discord.ui.Select(
            placeholder="Elige el motivo del ticket…",
            min_values=1,
            max_values=1,
            options=opts,
            custom_id="tickets:reason"
        )
        self.select.callback = self.on_select  # type: ignore[assignment]
        self.add_item(self.select)

        self.add_item(discord.ui.Button(
            label="Abrir ticket",
            emoji="🎫",
            style=discord.ButtonStyle.success,
            custom_id="tickets:open"
        ))

        self.add_item(discord.ui.Button(
            label="Reglas",
            emoji="📜",
            style=discord.ButtonStyle.secondary,
            custom_id="tickets:rules"
        ))

    async def on_select(self, interaction: discord.Interaction):
        self._choice[interaction.user.id] = self.select.values[0]
        await _defer_once(interaction, ephemeral=True)
        await interaction.followup.send(f"Motivo seleccionado: **{self.select.values[0]}**", ephemeral=True)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        cid = (interaction.data or {}).get("custom_id")
        if cid == "tickets:open":
            reason = self._choice.get(interaction.user.id, self.reasons[0])
            if hasattr(self.cog, "ticket_open_core"):
                await self.cog.ticket_open_core(interaction, motivo=reason)  # type: ignore[attr-defined]
            else:
                await self._fallback_open(interaction, motivo=reason)
            return False
        if cid == "tickets:rules":
            await _defer_once(interaction, ephemeral=True)
            embed = discord.Embed(
                title="📜 Reglas del ticket",
                description=(
                    "1) Explica tu caso con respeto.\n"
                    "2) Evita el spam o ping innecesario.\n"
                    "3) Adjunta capturas si aplica.\n"
                    "4) Ten paciencia mientras te atendemos."
                ),
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return False
        return True

    async def _fallback_open(self, interaction: discord.Interaction, motivo: str):
        await _defer_once(interaction, ephemeral=True)
        guild = interaction.guild
        user = interaction.user

        cfg = getattr(self.cog, "cfg", {})
        cat_id = int(cfg.get("tickets_category_id", 0))
        staff_ids = [int(x) for x in cfg.get("tickets_staff_role_ids", [])]
        logs_id = int(cfg.get("tickets_logs_channel_id", 0))

        category = guild.get_channel(cat_id) if cat_id else None  # type: ignore[arg-type]
        if not isinstance(category, discord.CategoryChannel):
            return await interaction.followup.send("❌ Falta configurar la **categoría** de tickets.", ephemeral=True)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True
            )
        }
        for rid in staff_ids:
            role = guild.get_role(rid)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True
                )

        name = f"ticket-{user.name[:20].lower()}"
        topic = f"ticket-owner:{user.id}"
        ch = await guild.create_text_channel(
            name=name,
            category=category,
            overwrites=overwrites,
            topic=topic,
            reason=f"Ticket de {user}"
        )

        embed = discord.Embed(
            title="🎫 Ticket creado",
            description=f"{user.mention}, gracias por contactarnos.\n**Motivo:** {motivo}",
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Equipo de Soporte")
        await ch.send(embed=embed, view=TicketControlsView(self.cog))

        if logs_id:
            log = guild.get_channel(logs_id)
            if isinstance(log, discord.TextChannel):
                await log.send(f"🆕 Ticket {ch.mention} creado por {user.mention} — Motivo: **{motivo}**")

        await interaction.followup.send(f"✅ Ticket creado: {ch.mention}", ephemeral=True)

class Tickets(commands.Cog):
    """Sistema de tickets con panel + botones."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cfg = load_json(CONFIG_PATH)
        self.state = load_json(TICKETS_PATH)  # { "open_by_user_id": channel_id }
        # claves de config (pueden venir del cogs/setup.py)
        self.staff_role_ids: List[int] = self.cfg.get("tickets_staff_role_ids", self.cfg.get("protected_role_ids", []))
        self.panel_channel_id: int = self.cfg.get("tickets_panel_channel_id", 0)
        self.target_category_id: int = self.cfg.get("tickets_category_id", 0)
        self.logs_channel_id: int = self.cfg.get("tickets_logs_channel_id", 0)
        reasons = self.cfg.get("tickets_panel_reasons", ["Soporte", "Reporte", "Apelación", "Compras", "Otros"])
        if not isinstance(reasons, list) or not reasons:
            reasons = ["Soporte", "Reporte", "Apelación", "Compras", "Otros"]
        self.panel_reasons: List[str] = [str(r).strip() for r in reasons if str(r).strip()]
        if not self.panel_reasons:
            self.panel_reasons = ["Soporte", "Reporte", "Apelación", "Compras", "Otros"]

    # ---------- helpers ----------
    def _save_cfg(self):
        self.cfg["tickets_staff_role_ids"] = self.staff_role_ids
        if self.panel_channel_id:  self.cfg["tickets_panel_channel_id"] = self.panel_channel_id
        if self.target_category_id: self.cfg["tickets_category_id"] = self.target_category_id
        if self.logs_channel_id:   self.cfg["tickets_logs_channel_id"] = self.logs_channel_id
        self.cfg["tickets_panel_reasons"] = self.panel_reasons
        save_json(CONFIG_PATH, self.cfg)

    def _save_state(self):
        save_json(TICKETS_PATH, self.state)

    def staff_roles(self, guild: discord.Guild) -> List[discord.Role]:
        roles = []
        for rid in self.staff_role_ids:
            r = guild.get_role(int(rid))
            if r: roles.append(r)
        return roles

    def _ticket_owner_id(self, channel: discord.TextChannel | None) -> Optional[int]:
        if channel is None:
            return None
        topic = channel.topic or ""
        if "ticket-owner:" in topic:
            try:
                return int(topic.split("ticket-owner:")[-1].strip())
            except ValueError:
                return None
        # fallback to state map
        for uid, cid in self.state.items():
            if cid == channel.id:
                try:
                    return int(uid)
                except ValueError:
                    return None
        return None

    def _is_staff(self, member: discord.Member) -> bool:
        staff_ids = set(int(x) for x in self.staff_role_ids)
        return any(r.id in staff_ids for r in getattr(member, "roles", []))

    async def _can_manage_ticket(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.manage_channels:
            return True
        channel = interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None
        owner_id = self._ticket_owner_id(channel)
        return self._is_staff(interaction.user) or (owner_id is not None and owner_id == interaction.user.id)

    async def ticket_open_core(self, interaction: discord.Interaction, motivo: Optional[str] = None):
        guild = interaction.guild
        user = interaction.user
        if guild is None:
            return await _safe_first_response(interaction, "Solo disponible dentro del servidor.")

        await _defer_once(interaction, ephemeral=True)

        try:
            existing_id = self.state.get(str(user.id))
            if existing_id:
                ch = guild.get_channel(int(existing_id))
                if isinstance(ch, discord.TextChannel):
                    return await interaction.followup.send(f"Ya tienes un ticket abierto: {ch.mention}", ephemeral=True)
                self.state.pop(str(user.id), None)
                self._save_state()

            category = guild.get_channel(self.target_category_id) if self.target_category_id else None
            if category and not isinstance(category, discord.CategoryChannel):
                category = None
            if category is None:
                panel_channel = getattr(interaction, "channel", None)
                if isinstance(panel_channel, discord.TextChannel) and panel_channel.category:
                    category = panel_channel.category
            if category is None:
                return await interaction.followup.send("❌ Falta configurar la categoría de tickets.", ephemeral=True)

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                user: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True
                ),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True
                ),
            }
            for role in self.staff_roles(guild):
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True,
                    manage_messages=True
                )

            base = re.sub(r"[^a-zA-Z0-9\-_. ]+", "", user.display_name).strip() or str(user.id)
            slug = re.sub(r"\s+", "-", base.lower())[:70]
            name = f"ticket-{slug}"
            topic = f"ticket-owner:{user.id}"

            channel = await guild.create_text_channel(
                name=name,
                category=category,
                overwrites=overwrites,
                topic=topic,
                reason=f"Ticket de {user} ({user.id})"
            )

            self.state[str(user.id)] = channel.id
            self._save_state()

            embed = discord.Embed(
                title="🎫 Ticket creado",
                description=(
                    f"Hola {user.mention}, cuéntanos tu consulta. Un miembro del staff te atenderá.\n\n"
                    f"• Motivo: **{motivo or 'No especificado'}**\n"
                    "• Adjunta pruebas o imágenes si es necesario.\n"
                    "• Sé específico para una mejor atención.\n"
                    "• Cuando termines, usa los botones para cerrar o borrar."
                ),
                color=discord.Color.green()
            )
            await channel.send(
                content="📌 **Comunicado de Riot Friends**",
                embed=embed,
                view=TicketControlsView(self)
            )

            if self.logs_channel_id:
                logch = guild.get_channel(self.logs_channel_id)
                if isinstance(logch, discord.TextChannel):
                    await logch.send(f"🟢 Ticket **abierto** por {user.mention} → {channel.mention} (Motivo: {motivo or 'N/A'})")

            await interaction.followup.send(f"✅ Ticket abierto: {channel.mention}", ephemeral=True)
        except Forbidden:
            await interaction.followup.send("❌ No tengo permisos suficientes para crear el canal.", ephemeral=True)
        except HTTPException as e:
            await interaction.followup.send(f"❌ Error al crear el ticket: `{e}`", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Falló al crear el ticket: `{type(e).__name__}: {e}`", ephemeral=True)

    async def ticket_close_core(self, interaction: discord.Interaction):
        await _defer_once(interaction, ephemeral=True)

        if not await self._can_manage_ticket(interaction):
            return await interaction.followup.send("🔒 No puedes cerrar este ticket.", ephemeral=True)

        ch = interaction.channel
        guild = interaction.guild
        if not isinstance(ch, discord.TextChannel) or guild is None:
            return await interaction.followup.send("❌ Canal inválido.", ephemeral=True)

        staff_ids = set(int(x) for x in self.staff_role_ids)

        try:
            await interaction.followup.send("🔒 Ticket cerrado.", ephemeral=True)

            overwrites = ch.overwrites
            owner_id = self._ticket_owner_id(ch)
            if owner_id:
                member = guild.get_member(owner_id)
                if member:
                    overwrites[member] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=False,
                        read_message_history=True
                    )

            for rid in staff_ids:
                role = guild.get_role(rid)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        manage_messages=True
                    )
            overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)

            await ch.edit(overwrites=overwrites, reason="Ticket cerrado")

        except Exception as e:
            print(f"[tickets] close error: {type(e).__name__}: {e}")

    async def ticket_delete_core(self, interaction: discord.Interaction):
        await _defer_once(interaction, ephemeral=True)

        if not await self._can_manage_ticket(interaction):
            return await interaction.followup.send("🔒 No puedes borrar este ticket.", ephemeral=True)

        ch = interaction.channel
        guild = interaction.guild
        if not isinstance(ch, discord.TextChannel) or guild is None:
            return await interaction.followup.send("❌ Canal inválido.", ephemeral=True)

        logs_id = int(self.logs_channel_id or 0)
        owner_id = self._ticket_owner_id(ch)
        if owner_id:
            self.state.pop(str(owner_id), None)
            self._save_state()

        try:
            await interaction.followup.send("🗑️ Borrando este ticket…", ephemeral=True)
            if logs_id:
                log_ch = guild.get_channel(logs_id)
                if isinstance(log_ch, discord.TextChannel):
                    await log_ch.send(f"🗑️ Ticket **{ch.name}** borrado por {interaction.user.mention}")

            await asyncio.sleep(0.2)
            await ch.delete(reason=f"Borrado por {interaction.user}")

        except Exception as e:
            print(f"[tickets] delete error: {type(e).__name__}: {e}")

    # ---------- slash group ----------
    group = app_commands.Group(name="ticket", description="Configura y usa el sistema de tickets")

    @group.command(name="setup", description="Configura roles y destino del panel/categoría de tickets")
    @app_commands.describe(
        staff_roles="Roles que verán los tickets (@Moderación, @Administración, ...)",
        panel_channel="Canal donde se publicará el panel (por defecto, el actual)",
        category="Categoría donde se crean los tickets (por defecto, la del panel)",
        logs_channel="Canal de logs (opcional) para aperturas/cierres"
    )
    async def ticket_setup(
        self,
        interaction: discord.Interaction,
        staff_roles: Optional[str] = None,
        panel_channel: Optional[discord.TextChannel] = None,
        category: Optional[discord.CategoryChannel] = None,
        logs_channel: Optional[discord.TextChannel] = None
    ):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("Requiere **Manage Channels**.", ephemeral=True)

        g = interaction.guild
        if staff_roles:
            self.staff_role_ids = parse_role_list(g, staff_roles)

        if panel_channel:
            self.panel_channel_id = panel_channel.id
            # si no nos dan categoría, usamos la del panel
            if not category and panel_channel.category:
                self.target_category_id = panel_channel.category.id

        if category:
            self.target_category_id = category.id

        if logs_channel:
            self.logs_channel_id = logs_channel.id

        self._save_cfg()
        await interaction.response.send_message("✅ Tickets configurados.", ephemeral=True)

    @group.command(name="panel", description="Publica el panel elegante de tickets")
    @app_commands.describe(
        channel="Canal donde publicar el panel (por defecto, este)",
        title="Título del panel",
        subtitle="Texto introductorio",
        banner_url="URL de banner (opcional)",
        thumb_url="URL de miniatura (opcional)",
        reasons="Motivos separados por coma (máx 25)"
    )
    async def ticket_panel(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        title: str = "Centro de Soporte",
        subtitle: str = "Selecciona el motivo y pulsa **Abrir ticket**. Un moderador te responderá pronto.",
        banner_url: Optional[str] = None,
        thumb_url: Optional[str] = None,
        reasons: Optional[str] = "Soporte,Reporte,Apelación,Compras,Otros"
    ):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("Requiere **Manage Channels**.", ephemeral=True)

        await _defer_once(interaction, ephemeral=True)

        ch = channel or interaction.channel
        if not isinstance(ch, discord.TextChannel):
            return await interaction.followup.send("Selecciona un canal de texto válido.", ephemeral=True)

        motifs = [r.strip() for r in (reasons or "").split(",") if r.strip()]
        if not motifs:
            motifs = ["Soporte", "Reporte", "Apelación", "Compras", "Otros"]
        motifs = motifs[:25]

        embed = discord.Embed(
            title=title,
            description=(
                f"{subtitle}\n\n"
                "🔔 **Importante**\n"
                "• Evita el spam.\n"
                "• Sé claro y adjunta capturas si aplica.\n"
                "• Respeta a los demás.\n"
            ),
            color=discord.Color.from_str("#ff4dd8")
        )
        if thumb_url:
            embed.set_thumbnail(url=thumb_url)
        if banner_url:
            embed.set_image(url=banner_url)
        embed.set_footer(text="Tickets · Riot Friends")

        view = TicketPanelView(self, motifs)
        await ch.send(embed=embed, view=view)

        self.panel_reasons = motifs
        try:
            self.bot.add_view(TicketPanelView(self, self.panel_reasons))
        except Exception:
            pass

        self.panel_channel_id = ch.id
        if ch.category:
            self.target_category_id = ch.category.id
        self._save_cfg()

        await interaction.followup.send(f"✅ Panel publicado en {ch.mention}.", ephemeral=True)

    # ---------- lógica de botones ----------
    async def handle_open(self, interaction: discord.Interaction):
        await self.ticket_open_core(interaction)

    async def handle_close(self, interaction: discord.Interaction):
        await self.ticket_close_core(interaction)

    async def handle_delete(self, interaction: discord.Interaction):
        await self.ticket_delete_core(interaction)

    async def cog_load(self):
        self.bot.add_view(TicketPanelView(self, self.panel_reasons))
        self.bot.add_view(TicketControlsView(self))


# --- ALIAS GLOBALES (fuera de la clase) ---
@app_commands.command(name="ticket-panel", description="Publica/actualiza el panel de tickets en este canal")
async def ticket_panel_global(interaction: discord.Interaction):
    cog = interaction.client.get_cog("Tickets")
    if not cog:
        return await interaction.response.send_message("❌ Cog de Tickets no cargado.", ephemeral=True)
    await cog.ticket_panel.callback(cog, interaction)


@app_commands.command(name="ticket-open", description="Crea un canal privado de ticket")
async def ticket_open_global(interaction: discord.Interaction):
    cog = interaction.client.get_cog("Tickets")
    if not cog:
        return await interaction.response.send_message("❌ Cog de Tickets no cargado.", ephemeral=True)
    await cog.ticket_open_core(interaction)


@app_commands.command(name="ticket-close", description="Cierra el ticket actual")
async def ticket_close_global(interaction: discord.Interaction):
    cog = interaction.client.get_cog("Tickets")
    if not cog:
        return await interaction.response.send_message("❌ Cog de Tickets no cargado.", ephemeral=True)
    await cog.ticket_close_core(interaction)


@app_commands.command(name="ticket-delete", description="Borra el ticket actual")
async def ticket_delete_global(interaction: discord.Interaction):
    cog = interaction.client.get_cog("Tickets")
    if not cog:
        return await interaction.response.send_message("❌ Cog de Tickets no cargado.", ephemeral=True)
    await cog.ticket_delete_core(interaction)


@app_commands.command(name="ticket-setup", description="Configura el sistema de tickets (roles/panel/categoría/logs)")
@app_commands.describe(
    staff_roles="Roles que verán los tickets (@Moderación, @Administración, ...)",
    panel_channel="Canal donde se publica el panel (por defecto, el actual)",
    category="Categoría donde se crean los tickets (por defecto, la del panel)",
    logs_channel="Canal de logs (opcional)"
)
async def ticket_setup_global(
    interaction: discord.Interaction,
    staff_roles: Optional[str] = None,
    panel_channel: Optional[discord.TextChannel] = None,
    category: Optional[discord.CategoryChannel] = None,
    logs_channel: Optional[discord.TextChannel] = None
):
    cog = interaction.client.get_cog("Tickets")
    if not cog:
        return await interaction.response.send_message("❌ Cog de Tickets no cargado.", ephemeral=True)
    await cog.ticket_setup.callback(cog, interaction, staff_roles, panel_channel, category, logs_channel)


async def setup(bot: commands.Bot):
    tickets = Tickets(bot)
    await bot.add_cog(tickets)
    gid = os.getenv("GUILD_ID")
    gobj = discord.Object(id=int(gid)) if gid and gid.isdigit() else None
    cmds = (
        ticket_panel_global,
        ticket_setup_global,
        ticket_open_global,
        ticket_close_global,
        ticket_delete_global,
    )
    if gobj:
        for cmd in cmds:
            try:
                bot.tree.add_command(cmd, guild=gobj)
            except app_commands.CommandAlreadyRegistered:
                bot.tree.remove_command(cmd.name, guild=gobj)
                bot.tree.add_command(cmd, guild=gobj)
