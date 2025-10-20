\
import discord
from discord.ext import commands
from discord import app_commands

class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="kick", description="Expulsa a un usuario.")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No especificado"):
        await member.kick(reason=reason)
        await interaction.response.send_message(f"👢 {member} fue expulsado. Razón: {reason}")

    @app_commands.command(name="ban", description="Banea a un usuario.")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No especificado"):
        await member.ban(reason=reason)
        await interaction.response.send_message(f"🔨 {member} fue baneado. Razón: {reason}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
