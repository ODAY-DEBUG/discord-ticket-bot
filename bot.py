import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

@bot.event
async def on_ready():
    print(f'✅ Bot Online: {bot.user}')
    try:
        await bot.load_extension('cogs.tickets')
        print("✅ Tickets loaded!")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"❌ Sync error: {e}")

bot.run(os.getenv('DISCORD_TOKEN'))