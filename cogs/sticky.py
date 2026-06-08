import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from cogs.config import staff_only

# ---------------------------------------------------------------------------
# Persistence for Stickies
# ---------------------------------------------------------------------------

STICKIES_FILE = "stickies.json"

# In-memory store: { channel_id: { "message_id": int, "content": str } }
_stickies: dict[int, dict] = {}

def load_stickies():
    global _stickies
    if os.path.exists(STICKIES_FILE):
        try:
            with open(STICKIES_FILE, 'r') as f:
                data = json.load(f)
                for channel_id_str, sticky_data in data.items():
                    _stickies[int(channel_id_str)] = sticky_data
            print(f"✅ Loaded {len(_stickies)} sticky messages")
        except Exception as e:
            print(f"❌ Failed to load stickies: {e}")

def save_stickies():
    try:
        # Convert integer keys to strings for JSON compatibility
        data = {str(channel_id): sticky_data for channel_id, sticky_data in _stickies.items()}
        with open(STICKIES_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"❌ Failed to save stickies: {e}")

# Load stickies on startup
load_stickies()

# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class Sticky(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        msg = str(error) if isinstance(error, app_commands.CheckFailure) else f"❌ Error: {error}"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bots and DMs
        if message.author.bot or not message.guild:
            return

        channel_id = message.channel.id
        if channel_id not in _stickies:
            return

        sticky = _stickies[channel_id]

        # Delete the old sticky message
        try:
            old_msg = await message.channel.fetch_message(sticky["message_id"])
            await old_msg.delete()
        except (discord.NotFound, discord.HTTPException):
            pass

        # Repost the sticky at the bottom
        embed = discord.Embed(description=sticky["content"], color=0xf1c40f)
        embed.set_footer(text="📌 Sticky Message")
        new_msg = await message.channel.send(embed=embed)
        
        _stickies[channel_id]["message_id"] = new_msg.id
        save_stickies()  # Save the updated message ID so we delete the right one next time

    # ------------------------------------------------------------------
    # /sticky  (NOW SAVES TO JSON)
    # ------------------------------------------------------------------

    @app_commands.command(name="sticky", description="Set a sticky message in a channel")
    @app_commands.describe(
        channel="Channel to post the sticky in",
        message="The message to sticky",
    )
    @staff_only()
    async def sticky(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        # Remove old sticky in that channel if one exists
        if channel.id in _stickies:
            try:
                old_msg = await channel.fetch_message(_stickies[channel.id]["message_id"])
                await old_msg.delete()
            except (discord.NotFound, discord.HTTPException):
                pass

        embed = discord.Embed(description=message, color=0xf1c40f)
        embed.set_footer(text="📌 Sticky Message")
        sent = await channel.send(embed=embed)

        _stickies[channel.id] = {"message_id": sent.id, "content": message}
        save_stickies()  # <-- Save to file

        await interaction.response.send_message(
            f"✅ Sticky message set in {channel.mention}.", ephemeral=True
        )

    # ------------------------------------------------------------------
    # /unsticky  (NOW SAVES TO JSON)
    # ------------------------------------------------------------------

    @app_commands.command(name="unsticky", description="Remove the sticky message from a channel")
    @app_commands.describe(channel="Channel to remove the sticky from")
    @staff_only()
    async def unsticky(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if channel.id not in _stickies:
            await interaction.response.send_message(
                f"❌ No sticky message found in {channel.mention}.", ephemeral=True
            )
            return

        try:
            old_msg = await channel.fetch_message(_stickies[channel.id]["message_id"])
            await old_msg.delete()
        except (discord.NotFound, discord.HTTPException):
            pass

        del _stickies[channel.id]
        save_stickies()  # <-- Save to file

        await interaction.response.send_message(
            f"✅ Sticky message removed from {channel.mention}.", ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Sticky(bot))