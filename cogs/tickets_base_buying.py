from discord.ext import commands
from cogs.config import STAFF_ROLE, BASE_BUYING_ROLE

BASE_CFG = {
    "cat":   "Base Buying",
    "ping":  [STAFF_ROLE, BASE_BUYING_ROLE],
    "allow": [STAFF_ROLE, BASE_BUYING_ROLE],
    "color": 0x2ecc71,
    "emoji": "🏠",
    "q": [
        "What type of base are you looking for?",
        "What is your budget?",
        "Any specific requirements?",
    ],
}


class TicketsBaseBuying(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsBaseBuying(bot))
