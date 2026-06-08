from discord.ext import commands
from cogs.config import STAFF_ROLE, BEDROCK_ROLE

BEDROCK_CFG = {
    "cat":   "Bedrock Holes",
    "ping":  [STAFF_ROLE, BEDROCK_ROLE],
    "allow": [STAFF_ROLE, BEDROCK_ROLE],
    "color": 0x95a5a6,
    "emoji": "🕳️",
    "q": [
        "What size hole do you need?",
        "What is your budget?",
        "Preferred location?",
    ],
}


class TicketsBedrock(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsBedrock(bot))
