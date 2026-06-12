import discord
from discord.ext import commands
import os
import asyncio
from dotenv import load_dotenv
import pymongo
from pymongo import MongoClient
import threading
from web.app import app as flask_app
load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.reactions = True  # Make sure this is here for reaction roles!

COGS = [
    'cogs.moderation',
    'cogs.giveaway',
    'cogs.sticky',
    'cogs.tickets_base',
    'cogs.tickets_base_buying',
    'cogs.tickets_bedrock',
    'cogs.tickets_spawner',
    'cogs.tickets_building',
    'cogs.tickets_support',
    'cogs.reactionroles',
    'cogs.welcome',
    'cogs.automod',
    'cogs.logging',
    'cogs.autorole',      # <-- ADD THIS
    'cogs.applications',  # ADD THIS
]

class Bot(commands.Bot):
    async def setup_hook(self):
        # --- MongoDB Setup ---
        mongo_uri = os.getenv("MONGO_URI")
        if not mongo_uri:
            print("❌ MONGO_URI environment variable is not set!")
        else:
            try:
                self.mongo_client = MongoClient(mongo_uri)
                # The database name will be "discord_bot"
                self.db = self.mongo_client["discord_bot"]
                # Test the connection
                self.mongo_client.admin.command('ping')
                print("✅ Successfully connected to MongoDB!")
            except Exception as e:
                print(f"❌ Failed to connect to MongoDB: {e}")
        # ---------------------

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
    try:
        synced = await bot.tree.sync()
        print(f'✅ Synced {len(synced)} global command(s): {[f"/{c.name}" for c in synced]}')
    except Exception as e:
        print(f'❌ Global sync failed: {e}')

# --- ADD THIS ENTIRE FUNCTION ---
@bot.tree.interaction_check
async def global_interaction_check(interaction: discord.Interaction) -> bool:
    # 1. Admins ALWAYS have access
    if interaction.user.guild_permissions.administrator:
        return True

    command_name = interaction.command.qualified_name
    
    # 2. Check if this command has custom role overrides in MongoDB
    override = bot.db["command_perms"].find_one({
        "guild_id": interaction.guild.id,
        "command_name": command_name
    })
    
    if override:
        # If configured on the website, ONLY allow the selected roles
        from cogs.config import has_role
        allowed_roles = override.get("roles", [])
        if has_role(interaction, *allowed_roles):
            return True
        raise app_commands.CheckFailure("❌ You don't have the required role for this command.")
    
    # 3. If NOT configured on the website, let the bot's default checks handle it
    return True
# --------------------------------


@bot.command(name='sync')
@commands.has_permissions(administrator=True)
async def sync_commands(ctx):
    msg = await ctx.send('🔄 Wiping old commands, reloading cogs, and syncing...')
    try:
        # 1. Wipe the internal command tree clean
        bot.tree.clear_commands(guild=None)
        bot.tree.clear_commands(guild=ctx.guild)
        
        # 2. Reload all cogs so they re-register their commands into the empty tree
        for cog in COGS:
            try:
                await bot.reload_extension(cog)
                print(f'✅ Reloaded {cog}')
            except Exception as e:
                print(f'❌ Reload failed for {cog}: {e}')
        
        # 3. Push the freshly rebuilt command list to Discord
        synced = await bot.tree.sync()
        names = ', '.join(f'/{c.name}' for c in synced)
        await msg.edit(content=f"✅ Synced {len(synced)} global command(s):\n{names}\n\n*Note: Discord can take up to an hour to remove ghost commands from users' autocomplete, but they will work immediately for you.*")
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
    loaded = list(bot.extensions.keys())
    await ctx.send(f"Loaded cogs: {', '.join(loaded) if loaded else 'None'}")


def main():
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        raise RuntimeError('DISCORD_TOKEN environment variable is not set.')

    async def run_bot():
        async with bot:
            await bot.start(token)
    
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("Bot stopped by user")


if __name__ == '__main__':
    main()