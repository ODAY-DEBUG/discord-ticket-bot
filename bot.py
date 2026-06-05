import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(
    command_prefix='!',
    intents=intents,
    help_command=None
)

# ================= STAFF ROLE =================
STAFF_ROLE = "Staff"
# =============================================


@bot.event
async def on_ready():
    print(f'✅ Bot is online: {bot.user}')


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


# ================= SECURITY FIX =================

def is_staff():
    async def predicate(ctx):
        role = discord.utils.get(ctx.guild.roles, name=STAFF_ROLE)
        return role in ctx.author.roles
    return commands.check(predicate)


# ================= TICKET COMMANDS =================

@bot.command(name='close')
@is_staff()
async def close(ctx):
    await ctx.send("Closing ticket in 5 seconds...")
    await asyncio.sleep(5)
    await ctx.channel.delete()


@bot.command(name='add')
@is_staff()
async def add_user(ctx, member: discord.Member):
    await ctx.channel.set_permissions(member, read_messages=True, send_messages=True)
    await ctx.send(f"Added {member.mention}")


@bot.command(name='remove')
@is_staff()
async def remove_user(ctx, member: discord.Member):
    await ctx.channel.set_permissions(member, overwrite=None)
    await ctx.send(f"Removed {member.mention}")


# ================= ERROR HANDLER =================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.CheckFailure):
        await ctx.send("You don't have permission to use this command.")
    else:
        await ctx.send(f"Error: {error}")


# ================= STARTUP FIX (RAILWAY SAFE) =================

async def main():
    async with bot:
        await bot.load_extension("cogs.tickets")
        await bot.start(os.getenv("DISCORD_TOKEN"))


asyncio.run(main())