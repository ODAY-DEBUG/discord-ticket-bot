"""
config.py — Central configuration for roles, permissions, and settings.
Edit this file to control who can use which commands across all cogs.
"""

import discord
from discord import app_commands

# ---------------------------------------------------------------------------
# Role names — match these exactly to your Discord server role names
# ---------------------------------------------------------------------------

# Add these lines anywhere above the permission check helpers:

OWNER_ROLE = "👑 Owner"  # The only role (besides the creator) that sees builder tickets initially
BUILDER_ORDERS_CHANNEL_ID = 1512866063833104384  # <-- REPLACE WITH YOUR ORDERS CHANNEL ID
STAFF_ROLE      = "Staff"
MOD_ROLE        = "Moderator"
ADMIN_ROLE      = "Admin"          # Optional extra admin role
TRUSTED_STAFF_ROLE = "Trusted Staff" # Restricted access for specific tickets

# Ticket seller roles
BASE_BUYING_ROLE  = "Base Seller"
BEDROCK_ROLE      = "Bedrock Seller"
SPAWNER_ROLE      = "Spawner Trader"
BUILDING_ROLE     = "Builder"

SELLER_ROLES = [BASE_BUYING_ROLE, BEDROCK_ROLE, SPAWNER_ROLE, BUILDING_ROLE]

# ---------------------------------------------------------------------------
# Channel names
# ---------------------------------------------------------------------------

LOG_CHANNEL = "mod-logs"           # Channel where moderation actions are logged

# ---------------------------------------------------------------------------
# Ticket channel prefixes
# ---------------------------------------------------------------------------

TICKET_PREFIXES = ("ticket-", "claimed-", "claim-")

# ---------------------------------------------------------------------------
# Giveaway settings
# ---------------------------------------------------------------------------

GIVEAWAYS_FILE = "giveaways.json"

# ---------------------------------------------------------------------------
# Permission check helpers
# ---------------------------------------------------------------------------

def has_role(interaction: discord.Interaction, *role_names: str) -> bool:
    """Return True if the user has any of the given role names."""
    user_roles = {r.name for r in interaction.user.roles}
    return bool(user_roles & set(role_names))


def is_admin_user(interaction: discord.Interaction) -> bool:
    """Return True if the user is a server administrator or has the Admin role."""
    return (
        interaction.user.guild_permissions.administrator
        or has_role(interaction, ADMIN_ROLE)
    )


def is_mod_user(interaction: discord.Interaction) -> bool:
    """Return True if the user is a mod, staff, or admin."""
    return is_admin_user(interaction) or has_role(interaction, STAFF_ROLE, MOD_ROLE)


def is_staff_user(interaction: discord.Interaction) -> bool:
    """Return True if the user has the Staff role or higher."""
    return is_admin_user(interaction) or has_role(interaction, STAFF_ROLE)


# ---------------------------------------------------------------------------
# Reusable app_commands check decorators
# ---------------------------------------------------------------------------

def admin_only():
    """Slash-command check: server admins (or Admin role) only."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if is_admin_user(interaction):
            return True
        raise app_commands.CheckFailure("❌ Admins only!")
    return app_commands.check(predicate)


def mod_only():
    """Slash-command check: Moderator, Staff, or admin."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if is_mod_user(interaction):
            return True
        raise app_commands.CheckFailure("❌ You need the Moderator or Staff role.")
    return app_commands.check(predicate)


def staff_only():
    """Slash-command check: Staff role or admin."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if is_staff_user(interaction):
            return True
        raise app_commands.CheckFailure("❌ Staff only!")
    return app_commands.check(predicate)