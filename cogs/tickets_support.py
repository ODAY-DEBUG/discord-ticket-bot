from discord.ext import commands
from cogs.config import STAFF_ROLE

SUPPORT_CFG = {
    "cat":   "General Support",
    "ping":  [STAFF_ROLE],
    "allow": [STAFF_ROLE],
    "color": 0x3498db,
    "emoji": "❓",
    "q": [
        "What do you need help with?",
        "Please provide as much detail as possible.",
    ],
}

SCAM_CFG = {
    "cat":   "Scam Reports",
    "ping":  [STAFF_ROLE],
    "allow": [STAFF_ROLE],
    "color": 0xe74c3c,
    "emoji": "⚠️",
    "q": [
        "Who scammed you?",
        "What happened?",
        "Do you have proof?",
    ],
}


class TicketsSupport(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsSupport(bot))
