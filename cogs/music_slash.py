from __future__ import annotations

import asyncio
import os
import re
from typing import Optional

import discord
import wavelink
from discord import app_commands
from discord.ext import commands

URL_RX = re.compile(r"https?://")
LAVALINK_URI = os.getenv("LAVALINK_URI", "http://127.0.0.1:2333")
LAVALINK_PASSWORD = os.getenv("LAVALINK_PASSWORD", "changeme")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
GUILD_OBJECT = discord.Object(id=GUILD_ID) if GUILD_ID else None

def guild_scope_decorator():
    if GUILD_OBJECT:
        return app_commands.guilds(GUILD_OBJECT)
    return lambda func: func


def in_voice_channel():
    async def predicate(inter: discord.Interaction):
        voice_state = getattr(inter.user, "voice", None)
        return voice_state and voice_state.channel

    return app_commands.check(predicate)


class MusicSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._connect_task = asyncio.create_task(self._connect_nodes())

    async def cog_unload(self):
        if self._connect_task and not self._connect_task.done():
            self._connect_task.cancel()

    async def _connect_nodes(self):
        await self.bot.wait_until_ready()
        try:
            if hasattr(wavelink, "NodePool"):
                pool = wavelink.NodePool
                if pool.nodes:
                    return
                await pool.connect(
                    client=self.bot,
                    nodes=[wavelink.Node(uri=LAVALINK_URI, password=LAVALINK_PASSWORD)],
                )
            else:
                pool = getattr(wavelink, "Pool", None)
                if pool is None:
                    raise RuntimeError("Wavelink Pool/NodePool no disponible")
                if getattr(pool, "nodes", None):
                    return
                await pool.connect(
                    client=self.bot,
                    nodes=[wavelink.Node(uri=LAVALINK_URI, password=LAVALINK_PASSWORD)],
                )
            print(f"[Music] Conectado a Lavalink: {LAVALINK_URI}")
        except Exception as exc:
            print(f"[Music] Error al conectar con Lavalink: {exc}")

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node):
        identifier = getattr(node, "identifier", "desconocido")
        print(f"[Music] Nodo listo: {identifier}")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player: wavelink.Player = payload.player
        queue = getattr(player, "queue", None)
        if queue and len(queue) > 0:
            try:
                next_track = queue.get()
                await player.play(next_track)
            except Exception:
                pass

    async def _ensure_player(self, inter: discord.Interaction) -> wavelink.Player:
        # Reutilizar player existente si ya está conectado
        voice_client = inter.guild.voice_client  # type: ignore
        if voice_client and isinstance(voice_client, wavelink.Player):
            player: wavelink.Player = voice_client
            # Asegurar que tenga cola inicializada
            if not hasattr(player, "queue") or player.queue is None:
                player.queue = wavelink.Queue()
            return player

        # Solo crear nuevo player si no existe
        channel = inter.user.voice.channel  # type: ignore
        player = await channel.connect(cls=wavelink.Player)
        if isinstance(channel, discord.StageChannel):
            try:
                await channel.guild.change_voice_state(
                    channel=channel,
                    self_mute=False,
                    self_deaf=False,
                    suppress=False,
                )
            except Exception:
                pass
        try:
            await player.set_volume(30)
        except Exception:
            pass
        if not hasattr(player, "queue") or player.queue is None:
            player.queue = wavelink.Queue()
        return player

    @app_commands.command(name="join", description="Conecta el bot a tu canal de voz.")
    @guild_scope_decorator()
    @in_voice_channel()
    async def join(self, inter: discord.Interaction):
        await inter.response.defer(ephemeral=True)
        player = await self._ensure_player(inter)
        await inter.followup.send(f"🎧 Conectado a **{player.channel}**.", ephemeral=True)

    @app_commands.command(name="play", description="Reproduce una canción por nombre o URL (YouTube).")
    @guild_scope_decorator()
    @app_commands.describe(query="Búsqueda o URL de YouTube")
    @in_voice_channel()
    async def play(self, inter: discord.Interaction, query: str):
        await inter.response.defer(ephemeral=True)
        player = await self._ensure_player(inter)

        # Forzar búsqueda en YouTube normal (no YouTube Music) para evitar problemas de autenticación
        original_query = query.strip()
        search_query = original_query

        # Si no es URL, usar búsqueda en YouTube (no YT Music)
        if not search_query.startswith(("http://", "https://")):
            search_query = f"ytsearch:{search_query}"

        # Intentar buscar con YouTube normal (videos, no requiere login)
        try:
            tracks = await wavelink.YouTubeTrack.search(search_query)
        except Exception:
            tracks = None

        # Fallback a YouTube Music solo si no hay resultados
        if not tracks:
            try:
                tracks = await wavelink.YouTubeMusicTrack.search(f"ytmsearch:{original_query}")
            except Exception:
                tracks = None

        if not tracks:
            return await inter.followup.send("❌ No encontré resultados.", ephemeral=True)

        queue = getattr(player, "queue", None)
        response = None

        if isinstance(tracks, wavelink.Playlist):
            added = 0
            if queue:
                for track in tracks:
                    await queue.put_wait(track)
                    added += 1

            # Verificar si está ocupado
            is_busy = False
            try:
                is_busy = (player.current is not None) or getattr(player, "playing", False) or player.paused
            except Exception:
                pass

            if not is_busy and queue and len(queue) > 0:
                next_track = queue.get()
                await player.play(next_track)
                response = f"▶️ Reproduciendo: **{getattr(next_track, 'title', str(next_track))}**"
            else:
                response = f"📃 Playlist **{tracks.name}** añadida ({added} temas)."
        else:
            track = tracks[0]

            # CONDICIÓN ROBUSTA para decidir si encolamos
            is_busy = False
            try:
                is_busy = (player.current is not None) or getattr(player, "playing", False) or player.paused
            except Exception:
                pass

            if is_busy or (queue and len(queue) > 0):
                # Hay algo sonando o hay cola -> ENCOLAR
                await queue.put_wait(track)
                response = f"➕ En cola: **{track.title}** (`{len(queue)}` en cola)"
            else:
                # No hay nada -> REPRODUCIR DIRECTAMENTE
                await player.play(track)
                response = f"▶️ Reproduciendo: **{track.title}**"

        await inter.followup.send(response, ephemeral=True)

    @app_commands.command(name="skip", description="Salta la pista actual.")
    @guild_scope_decorator()
    async def skip(self, inter: discord.Interaction):
        await inter.response.defer(ephemeral=True)
        player = inter.guild.voice_client  # type: ignore
        if not player or not isinstance(player, wavelink.Player) or not player.playing:
            return await inter.followup.send("No estoy reproduciendo nada.", ephemeral=True)
        await player.skip()
        await inter.followup.send("⏭️ Saltado.", ephemeral=True)

    @app_commands.command(name="pause", description="Pausa la reproducción.")
    @guild_scope_decorator()
    async def pause(self, inter: discord.Interaction):
        await inter.response.defer(ephemeral=True)
        player = inter.guild.voice_client  # type: ignore
        if not player or not isinstance(player, wavelink.Player) or not player.playing:
            return await inter.followup.send("Nada que pausar.", ephemeral=True)
        await player.pause(True)
        await inter.followup.send("⏸️ Pausado.", ephemeral=True)

    @app_commands.command(name="resume", description="Reanuda la reproducción.")
    @guild_scope_decorator()
    async def resume(self, inter: discord.Interaction):
        await inter.response.defer(ephemeral=True)
        player = inter.guild.voice_client  # type: ignore
        if not player or not isinstance(player, wavelink.Player):
            return await inter.followup.send("No estoy en voz.", ephemeral=True)
        await player.pause(False)
        await inter.followup.send("▶️ Reanudado.", ephemeral=True)

    @app_commands.command(name="stop", description="Desconecta del canal de voz.")
    @guild_scope_decorator()
    async def stop(self, inter: discord.Interaction):
        await inter.response.defer(ephemeral=True)
        vc = inter.guild.voice_client
        if vc:
            await vc.disconnect()
            return await inter.followup.send("⏹️ Desconectado.", ephemeral=True)
        await inter.followup.send("No estaba conectado.", ephemeral=True)

    @app_commands.command(name="volume", description="Ajusta el volumen (0-150).")
    @guild_scope_decorator()
    @app_commands.describe(valor="Volumen (0-150)")
    async def volume(self, inter: discord.Interaction, valor: int):
        await inter.response.defer(ephemeral=True)
        valor = max(0, min(150, valor))
        player = inter.guild.voice_client  # type: ignore
        if not player or not isinstance(player, wavelink.Player):
            return await inter.followup.send("No estoy en voz.", ephemeral=True)
        try:
            await player.set_volume(valor)
            await inter.followup.send(f"🔊 Volumen: **{valor}%**", ephemeral=True)
        except Exception as exc:
            await inter.followup.send(f"❌ No pude cambiar volumen: `{exc}`", ephemeral=True)

    @app_commands.command(name="queue", description="Muestra la cola actual.")
    @guild_scope_decorator()
    async def queue(self, inter: discord.Interaction):
        await inter.response.defer(ephemeral=True)
        player = inter.guild.voice_client  # type: ignore
        if not player or not isinstance(player, wavelink.Player):
            return await inter.followup.send("No estoy en voz.", ephemeral=True)

        lines = []
        current = getattr(player, "current", None) or getattr(player, "track", None)
        if current:
            lines.append(f"**Ahora:** {current.title}")
        queue = getattr(player, "queue", None)
        if queue and len(queue) > 0:
            for idx, track in enumerate(list(queue)[:10], start=1):
                lines.append(f"{idx}. {track.title}")
            if len(queue) > 10:
                lines.append(f"... y {len(queue) - 10} más")
        else:
            lines.append("_Cola vacía_")
        await inter.followup.send("\n".join(lines), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(MusicSlash(bot))
