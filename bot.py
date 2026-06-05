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

STAFF_ROLE = "Staff"

@bot.event
async def on_ready():
    print(f'✅ Bot is online: {bot.user}')
    try:
        await bot.load_extension('cogs.tickets')
        print("✅ Tickets cog loaded!")
    except Exception as e:
        print(f"❌ Failed to load tickets: {e}")

@bot.command(name='help')
async def help_cmd(ctx):
    embed = discord.Embed(title="Ticket Bot Commands", color=discord.Color.blue())
    embed.add_field(name="General", value="`!help` `!ping`", inline=False)
    embed.add_field(name="Ticket Commands", value="`!ticketpanel` `!add @user` `!remove @user`", inline=False)
    embed.add_field(name="Staff Commands", value="`!close`", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='ping')
async def ping(ctx):
    await ctx.send(f'Pong! {round(bot.latency * 1000)}ms')

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.CheckFailure):
        return
    else:
        await ctx.send(f"Error: {error}")

bot.run(os.getenv('DISCORD_TOKEN'))