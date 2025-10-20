\
import discord
from discord.ext import commands
from discord import app_commands

class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Muestra latencia del bot.")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Pong! {round(self.bot.latency*1000)} ms")

    @app_commands.command(name="server-info", description="Información del servidor actual.")
    async def server_info(self, interaction: discord.Interaction):
        g = interaction.guild
        if not g:
            return await interaction.response.send_message("Solo disponible en servidores.", ephemeral=True)
        embed = discord.Embed(title=g.name)
        embed.add_field(name="Miembros", value=str(g.member_count))
        embed.add_field(name="Canales", value=f"Text: {len(g.text_channels)} | Voice: {len(g.voice_channels)}")
        embed.set_thumbnail(url=g.icon.url if g.icon else discord.Embed.Empty)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="user-info", description="Información de un usuario.")
    @app_commands.describe(member="Selecciona un miembro")
    async def user_info(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        roles = ", ".join(r.mention for r in member.roles[1:]) or "Sin roles"
        embed = discord.Embed(title=str(member), description=f"ID: {member.id}")
        embed.add_field(name="Roles", value=roles, inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
