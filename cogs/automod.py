import discord
from discord.ext import commands
from discord import app_commands
import re
from cogs.config import admin_only, mod_only

class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db

    def get_settings(self, guild_id: int):
        return self.db["automod_settings"].find_one({"guild_id": guild_id})

    @app_commands.command(name="automod_links", description="Toggle deleting all links")
    @app_commands.describe(enabled="True to enable, False to disable")
    @admin_only()
    async def toggle_links(self, interaction: discord.Interaction, enabled: bool):
        self.db["automod_settings"].update_one(
            {"guild_id": interaction.guild.id},
            {"$set": {"block_links": enabled}},
            upsert=True
        )
        await interaction.response.send_message(f"✅ Link blocking {'enabled' if enabled else 'disabled'}.")

    @app_commands.command(name="automod_invites", description="Toggle deleting Discord invites")
    @app_commands.describe(enabled="True to enable, False to disable")
    @admin_only()
    async def toggle_invites(self, interaction: discord.Interaction, enabled: bool):
        self.db["automod_settings"].update_one(
            {"guild_id": interaction.guild.id},
            {"$set": {"block_invites": enabled}},
            upsert=True
        )
        await interaction.response.send_message(f"✅ Discord invite blocking {'enabled' if enabled else 'disabled'}.")

    @app_commands.command(name="automod_addword", description="Add a word to the blocklist")
    @admin_only()
    async def add_word(self, interaction: discord.Interaction, word: str):
        settings = self.get_settings(interaction.guild.id)
        banned_words = settings.get("banned_words", []) if settings else []
        
        if word.lower() in banned_words:
            return await interaction.response.send_message("❌ That word is already blocked.", ephemeral=True)
            
        banned_words.append(word.lower())
        self.db["automod_settings"].update_one(
            {"guild_id": interaction.guild.id},
            {"$set": {"banned_words": banned_words}},
            upsert=True
        )
        await interaction.response.send_message(f"✅ Added `{word}` to the blocklist.")

    @app_commands.command(name="automod_removeword", description="Remove a word from the blocklist")
    @admin_only()
    async def remove_word(self, interaction: discord.Interaction, word: str):
        settings = self.get_settings(interaction.guild.id)
        banned_words = settings.get("banned_words", []) if settings else []
        
        if word.lower() not in banned_words:
            return await interaction.response.send_message("❌ That word isn't on the blocklist.", ephemeral=True)
            
        banned_words.remove(word.lower())
        self.db["automod_settings"].update_one(
            {"guild_id": interaction.guild.id},
            {"$set": {"banned_words": banned_words}},
            upsert=True
        )
        await interaction.response.send_message(f"✅ Removed `{word}` from the blocklist.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Skip mods/admins
        if isinstance(message.author, discord.Member):
            if message.author.guild_permissions.administrator or message.author.guild_permissions.manage_messages:
                return

        settings = self.get_settings(message.guild.id)
        if not settings:
            return

        content_lower = message.content.lower()
        deleted = False

        # Check Discord Invites
        if settings.get("block_invites") and ("discord.gg/" in content_lower or "discord.com/invite/" in content_lower):
            await message.delete()
            deleted = True

        # Check Links
        elif settings.get("block_links") and re.search(r'(https?://|www\.)', content_lower):
            await message.delete()
            deleted = True

        # Check Banned Words
        elif not deleted:
            banned_words = settings.get("banned_words", [])
            for word in banned_words:
                if word in content_lower:
                    await message.delete()
                    deleted = True
                    break

        if deleted:
            try:
                await message.channel.send(f"⚠️ {message.author.mention}, that message was blocked by AutoMod.", delete_after=5)
            except discord.HTTPException:
                pass

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))