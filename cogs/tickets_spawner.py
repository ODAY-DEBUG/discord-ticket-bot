from discord.ext import commands
from cogs.config import TRUSTED_STAFF_ROLE, SPAWNER_ROLE  # <-- Changed import

SPAWNER_CFG = {
    "cat":   "Spawner Trading",
    "ping":  [TRUSTED_STAFF_ROLE, SPAWNER_ROLE],  # <-- Changed from STAFF_ROLE
    "allow": [TRUSTED_STAFF_ROLE, SPAWNER_ROLE],  # <-- Changed from STAFF_ROLE
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