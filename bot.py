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
    
    # Force sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands globally")
        
        # Also sync to each guild for instant updates
        for guild in bot.guilds:
            await bot.tree.sync(guild=guild)
            print(f"✅ Synced commands to {guild.name}")
    except Exception as e:
        print(f"❌ Sync error: {e}")

@bot.command(name='sync')
@commands.has_permissions(administrator=True)
async def sync_commands(ctx):
    """Force sync slash commands"""
    await ctx.defer()
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"✅ Synced {len(synced)} commands globally!")
        
        # Sync to current guild
        await bot.tree.sync(guild=ctx.guild)
        await ctx.send(f"✅ Synced commands to this server!")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

bot.run(os.getenv('DISCORD_TOKEN'))