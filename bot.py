import discord
from discord.ext import commands
import os
import asyncio
import signal
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

COGS = [
    'cogs.moderation',
    'cogs.giveaway',
    'cogs.tickets_base',
    'cogs.tickets_base_buying',
    'cogs.tickets_bedrock',
    'cogs.tickets_spawner',
    'cogs.tickets_building',
    'cogs.tickets_support',
]


class Bot(commands.Bot):
    async def setup_hook(self):
        for cog in COGS:
            try:
                await self.load_extension(cog)
                print(f'✅ {cog} loaded!')
            except Exception as e:
                print(f'❌ Failed to load {cog}: {e}')


bot = Bot(command_prefix='!', intents=intents, help_command=None)


@bot.event
async def on_ready():
    print(f'✅ Bot online: {bot.user} (ID: {bot.user.id})')
    
    # Wait a bit for the cache to be fully ready
    await asyncio.sleep(2)
    
    # Sync commands for each guild
    for guild in bot.guilds:
        try:
            # Sync commands globally or per guild
            bot.tree.copy_global_to(guild=guild)
            guild_cmds = await bot.tree.sync(guild=guild)
            print(f'✅ Synced {len(guild_cmds)} command(s) to {guild.name}: {[f"/{c.name}" for c in guild_cmds]}')
        except Exception as e:
            print(f'❌ Sync failed for {guild.name}: {e}')


@bot.command(name='sync')
@commands.has_permissions(administrator=True)
async def sync_commands(ctx):
    msg = await ctx.send('🔄 Reloading all cogs and syncing...')
    try:
        # Reload cogs
        for cog in COGS:
            try:
                await bot.reload_extension(cog)
                print(f'✅ Reloaded {cog}')
            except Exception as e:
                print(f'❌ Reload failed for {cog}: {e}')
        
        # Sync commands
        bot.tree.copy_global_to(guild=ctx.guild)
        guild_cmds = await bot.tree.sync(guild=ctx.guild)
        names = ', '.join(f'/{c.name}' for c in guild_cmds)
        await msg.edit(content=f'✅ Synced {len(guild_cmds)} command(s):\n{names}')
    except Exception as e:
        await msg.edit(content=f'❌ Sync failed: {e}')


@bot.command(name='reload')
@commands.has_permissions(administrator=True)
async def reload_cog(ctx, cog: str = ''):
    targets = COGS if not cog else [cog]
    results = []
    for c in targets:
        try:
            await bot.reload_extension(c)
            results.append(f'✅ {c}')
        except Exception as e:
            results.append(f'❌ {c}: {e}')
    await ctx.send('\n'.join(results))


@bot.command(name='listcogs')
@commands.has_permissions(administrator=True)
async def list_cogs(ctx):
    """List all loaded cogs and commands"""
    loaded = list(bot.extensions.keys())
    await ctx.send(f"Loaded cogs: {', '.join(loaded) if loaded else 'None'}")


def main():
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        raise RuntimeError('DISCORD_TOKEN environment variable is not set.')

    # Fix for the deprecation warning - use asyncio.run() instead of get_event_loop()
    async def run_bot():
        async with bot:
            await bot.start(token)
    
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("Bot stopped by user")


if __name__ == '__main__':
    main()