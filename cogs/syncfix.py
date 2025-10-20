import discord
from discord import app_commands
from discord.ext import commands

class SyncFix(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="syncfix",
        description="Forzar recreación de slash commands en este servidor."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def syncfix(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None:
            return await interaction.followup.send("Este comando solo funciona dentro de un servidor.", ephemeral=True)

        self.bot.tree.clear_commands(guild=guild)
        await self.bot.tree.sync(guild=guild)
        await interaction.followup.send("✅ Comandos limpiados y sincronizados en este servidor.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(SyncFix(bot))
