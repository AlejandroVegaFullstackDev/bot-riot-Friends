\
import discord
from discord.ext import commands
from discord import app_commands

class Poll(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="poll", description="Crea una encuesta rápida con 👍 y 👎")
    async def poll(self, interaction: discord.Interaction, pregunta: str):
        embed = discord.Embed(title="📊 Encuesta", description=pregunta)
        msg = await interaction.channel.send(embed=embed)
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")
        await interaction.response.send_message("Encuesta creada.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Poll(bot))
