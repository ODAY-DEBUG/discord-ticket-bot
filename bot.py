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

COGS = ['cogs.tickets', 'cogs.moderation']


class Bot(commands.Bot):
    async def setup_hook(self):
        for cog in COGS:
            try:
                await self.load_extension(cog)
                print(f'✅ {cog} loaded!')
            except Exception as e:
                print(f'❌ Failed to load {cog}: {e}')

        try:
            global_cmds = await self.tree.sync()
            names = ', '.join(f'/{c.name}' for c in global_cmds)
            print(f'✅ Global sync: {len(global_cmds)} command(s): {names}')
        except Exception as e:
            print(f'❌ Global sync error: {e}')


bot = Bot(command_prefix='!', intents=intents, help_command=None)


@bot.event
async def on_ready():
    print(f'✅ Bot online: {bot.user} (ID: {bot.user.id})')
    for guild in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=guild)
            guild_cmds = await bot.tree.sync(guild=guild)
            print(f'✅ Guild sync → {guild.name}: {[f"/{c.name}" for c in guild_cmds]}')
        except Exception as e:
            print(f'❌ Guild sync failed for {guild.name}: {e}')


@bot.command(name='sync')
@commands.has_permissions(administrator=True)
async def sync_commands(ctx):
    msg = await ctx.send('🔄 Reloading all cogs and syncing...')
    try:
        for cog in COGS:
            try:
                await bot.reload_extension(cog)
            except Exception as e:
                print(f'❌ Reload failed for {cog}: {e}')

        bot.tree.copy_global_to(guild=ctx.guild)
        guild_cmds = await bot.tree.sync(guild=ctx.guild)
        global_cmds = await bot.tree.sync()

        names = ', '.join(f'/{c.name}' for c in guild_cmds)
        await msg.edit(content=f'✅ Synced {len(guild_cmds)} guild + {len(global_cmds)} global command(s):\n{names}')
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


def main():
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        raise RuntimeError('DISCORD_TOKEN environment variable is not set.')

    loop = asyncio.get_event_loop()

    def _shutdown(sig):
        print(f'Received {sig.name}, shutting down gracefully...')
        loop.create_task(bot.close())

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _shutdown, sig)
        except NotImplementedError:
            pass

    bot.run(token, log_handler=None)


if __name__ == '__main__':
    main()