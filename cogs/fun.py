\
import random
import discord
from discord.ext import commands
from discord import app_commands

class Fun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="dice", description="Lanza un dado NdM (por defecto 1d6).")
    async def dice(self, interaction: discord.Interaction, n: int = 1, caras: int = 6):
        if n < 1 or caras < 2 or n > 20 or caras > 1000:
            return await interaction.response.send_message("Valores fuera de rango.", ephemeral=True)
        rolls = [random.randint(1, caras) for _ in range(n)]
        await interaction.response.send_message(f"🎲 {n}d{caras}: {rolls} = **{sum(rolls)}**")

    @app_commands.command(name="rps", description="Piedra, papel o tijera.")
    async def rps(self, interaction: discord.Interaction, eleccion: str):
        opciones = ["piedra","papel","tijera"]
        e = eleccion.lower()
        if e not in opciones:
            return await interaction.response.send_message("Elige: piedra, papel o tijera.", ephemeral=True)
        bot_e = random.choice(opciones)
        resultado = "🎉 ¡Ganaste!" if (e=="piedra" and bot_e=="tijera") or (e=="papel" and bot_e=="piedra") or (e=="tijera" and bot_e=="papel") else ("🤝 Empate" if e==bot_e else "💀 Perdiste")
        await interaction.response.send_message(f"Tú: **{e}** | Bot: **{bot_e}** → {resultado}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
