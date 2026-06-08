import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from cogs.config import admin_only

# ---------------------------------------------------------------------------
# Persistence for Reaction Roles
# ---------------------------------------------------------------------------

REACT_ROLES_FILE = "reactionroles.json"

# Data structure: { str(message_id): { str(emoji): int(role_id) } }
_react_roles = {}

def load_react_roles():
    global _react_roles
    if os.path.exists(REACT_ROLES_FILE):
        try:
            with open(REACT_ROLES_FILE, 'r') as f:
                _react_roles = json.load(f)
            print(f"✅ Loaded {sum(len(v) for v in _react_roles.values())} reaction roles")
        except Exception as e:
            print(f"❌ Failed to load reaction roles: {e}")

def save_react_roles():
    try:
        with open(REACT_ROLES_FILE, 'w') as f:
            json.dump(_react_roles, f, indent=2)
    except Exception as e:
        print(f"❌ Failed to save reaction roles: {e}")

# Load on startup
load_react_roles()


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class ReactionRoles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # Slash Command Group: /reactionrole add / remove
    # ------------------------------------------------------------------

    rr_group = app_commands.Group(name="reactionrole", description="Manage reaction roles")

    @rr_group.command(name="add", description="Add a reaction role to a specific message")
    @app_commands.describe(
        message_id="The ID of the message to attach the reaction to",
        emoji="The emoji to use (standard or custom)",
        role="The role to give when reacted"
    )
    @admin_only()
    async def rr_add(
        self,
        interaction: discord.Interaction,
        message_id: str,
        emoji: str,
        role: discord.Role,
    ):
        # Validate message ID
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.response.send_message("❌ Invalid Message ID.", ephemeral=True)
            return

        # Fetch the message to ensure it exists and bot can see it
        found_msg = None
        for channel in interaction.guild.text_channels:
            try:
                found_msg = await channel.fetch_message(msg_id)
                break
            except (discord.NotFound, discord.Forbidden):
                continue
        
        if not found_msg:
            await interaction.response.send_message("❌ Could not find that message. Make sure the ID is correct and I can see the channel.", ephemeral=True)
            return

        # Add the emoji reaction to the message
        try:
            await found_msg.add_reaction(emoji)
        except (discord.HTTPException, TypeError):
            await interaction.response.send_message("❌ Invalid emoji, or I don't have access to that emoji.", ephemeral=True)
            return

        # Save to memory and JSON
        msg_id_str = str(msg_id)
        if msg_id_str not in _react_roles:
            _react_roles[msg_id_str] = {}

        _react_roles[msg_id_str][emoji] = role.id
        save_react_roles()

        await interaction.response.send_message(
            f"✅ Reaction role added!\n**Emoji:** {emoji} → **Role:** {role.mention}",
            ephemeral=True
        )

    @rr_group.command(name="remove", description="Remove a reaction role from a message")
    @app_commands.describe(
        message_id="The ID of the message",
        emoji="The emoji to remove"
    )
    @admin_only()
    async def rr_remove(
        self,
        interaction: discord.Interaction,
        message_id: str,
        emoji: str,
    ):
        msg_id_str = str(message_id)
        
        if msg_id_str not in _react_roles or emoji not in _react_roles[msg_id_str]:
            await interaction.response.send_message("❌ That reaction role doesn't exist.", ephemeral=True)
            return

        # Remove from data
        del _react_roles[msg_id_str][emoji]
        if not _react_roles[msg_id_str]:  # Clean up empty message entries
            del _react_roles[msg_id_str]
            
        save_react_roles()

        # Optionally remove the bot's reaction from the message
        try:
            msg_id = int(message_id)
            for channel in interaction.guild.text_channels:
                try:
                    found_msg = await channel.fetch_message(msg_id)
                    await found_msg.remove_reaction(emoji, self.bot.user)
                    break
                except (discord.NotFound, discord.Forbidden):
                    continue
        except Exception:
            pass # Ignore if we can't remove the visual reaction

        await interaction.response.send_message(f"✅ Reaction role removed for {emoji}.", ephemeral=True)

    # ------------------------------------------------------------------
    # Listeners: Assign/Remove role on reaction
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Gives role when reaction is added."""
        if payload.guild_id is None or payload.member.bot:
            return

        msg_id_str = str(payload.message_id)
        if msg_id_str not in _react_roles:
            return

        emoji_str = str(payload.emoji)
        if emoji_str not in _react_roles[msg_id_str]:
            return

        role_id = _react_roles[msg_id_str][emoji_str]
        guild = self.bot.get_guild(payload.guild_id)
        role = guild.get_role(role_id)
        
        if role and payload.member:
            try:
                await payload.member.add_roles(role, reason="Reaction Role")
            except discord.Forbidden:
                print(f"❌ Missing permissions to assign role {role.name}")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """Removes role when reaction is removed."""
        if payload.guild_id is None:
            return

        msg_id_str = str(payload.message_id)
        if msg_id_str not in _react_roles:
            return

        emoji_str = str(payload.emoji)
        if emoji_str not in _react_roles[msg_id_str]:
            return

        role_id = _react_roles[msg_id_str][emoji_str]
        guild = self.bot.get_guild(payload.guild_id)
        role = guild.get_role(role_id)
        member = guild.get_member(payload.user_id)
        
        # Avoid removing roles from bots
        if role and member and not member.bot:
            try:
                await member.remove_roles(role, reason="Reaction Role removed")
            except discord.Forbidden:
                print(f"❌ Missing permissions to remove role {role.name}")


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionRoles(bot))