import discord
from discord.ext import commands
from discord import app_commands
from cogs.config import staff_only

# In-memory store: { channel_id: { "message_id": int, "content": str } }
_stickies: dict[int, dict] = {}


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

    # ------------------------------------------------------------------
    # /sticky
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

        await interaction.response.send_message(
            f"✅ Sticky message set in {channel.mention}.", ephemeral=True
        )

    # ------------------------------------------------------------------
    # /unsticky
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
        await interaction.response.send_message(
            f"✅ Sticky message removed from {channel.mention}.", ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Sticky(bot))
