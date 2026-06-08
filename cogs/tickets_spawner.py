from discord.ext import commands
from cogs.config import STAFF_ROLE, SPAWNER_ROLE

SPAWNER_CFG = {
    "cat":   "Spawner Trading",
    "ping":  [STAFF_ROLE, SPAWNER_ROLE],
    "allow": [STAFF_ROLE, SPAWNER_ROLE],
    "color": 0xf1c40f,
    "emoji": "🔄",
    "q": [
        "Are you buying or selling?",
        "What spawner type?",
        "Quantity and price?",
    ],
}


class TicketsSpawner(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsSpawner(bot))
