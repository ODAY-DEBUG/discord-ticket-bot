from discord.ext import commands
from cogs.config import STAFF_ROLE, BUILDING_ROLE

BUILDING_CFG = {
    "cat":   "Building",
    "ping":  [BUILDING_ROLE],
    "allow": [STAFF_ROLE, BUILDING_ROLE],
    "color": 0x9b59b6,
    "emoji": "🏗️",
    "q": [
        "What do you need built?",
        "What is your budget?",
        "Do you have a deadline?",
    ],
}


class TicketsBuilding(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsBuilding(bot))
