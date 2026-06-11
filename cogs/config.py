"""
config.py — Central configuration for roles, permissions, and settings.
Now supports dynamic overrides from the Web Dashboard (MongoDB)!
"""

import discord
from discord import app_commands

# ---------------------------------------------------------------------------
# Default Fallback Role names & Channels (Used if not overridden on the website)
# ---------------------------------------------------------------------------

DEFAULT_STAFF_ROLE      = "Staff"
DEFAULT_MOD_ROLE        = "Moderator"
DEFAULT_ADMIN_ROLE      = "Admin"          
DEFAULT_TRUSTED_STAFF_ROLE = "Trusted Staff" 

# Ticket seller roles & Builder roles (Needed for Cogs)
BASE_BUYING_ROLE  = "Base Seller"
BEDROCK_ROLE      = "Bedrock Seller"
SPAWNER_ROLE      = "Spawner Trader"
BUILDING_ROLE     = "Builder"
OWNER_ROLE        = "👑 Owner"

SELLER_ROLES = [BASE_BUYING_ROLE, BEDROCK_ROLE, SPAWNER_ROLE, BUILDING_ROLE]

# Channel names & IDs (Needed for Cogs)
LOG_CHANNEL = "mod-logs"
BUILDER_ORDERS_CHANNEL_ID = 1512866063833104384 # Make sure this is your builder orders channel ID

# Ticket channel prefixes
TICKET_PREFIXES = ("ticket-", "claimed-", "claim-")

# Giveaway settings fallback
GIVEAWAYS_FILE = "giveaways.json"


# ---------------------------------------------------------------------------
# Dynamic Config Loader (Reads from MongoDB Dashboard)
# ---------------------------------------------------------------------------

def get_guild_config(db, guild_id: int) -> dict:
    """Fetches dynamic config from MongoDB. Falls back to defaults if not found."""
    config = db["bot_config"].find_one({"guild_id": guild_id})
    if not config:
        config = {}
    
    return {
        "STAFF_ROLE": config.get("STAFF_ROLE", DEFAULT_STAFF_ROLE),
        "MOD_ROLE": config.get("MOD_ROLE", DEFAULT_MOD_ROLE),
        "ADMIN_ROLE": config.get("ADMIN_ROLE", DEFAULT_ADMIN_ROLE),
        "TRUSTED_STAFF_ROLE": config.get("TRUSTED_STAFF_ROLE", DEFAULT_TRUSTED_STAFF_ROLE),
        "LOG_CHANNEL_ID": config.get("LOG_CHANNEL_ID")
    }

# ---------------------------------------------------------------------------
# Permission check helpers
# ---------------------------------------------------------------------------

def has_role(interaction: discord.Interaction, *role_names: str) -> bool:
    user_roles = {r.name for r in interaction.user.roles}
    return bool(user_roles & set(role_names))

def is_admin_user(interaction: discord.Interaction) -> bool:
    # Dynamic check
    cfg = get_guild_config(interaction.client.db, interaction.guild.id)
    return (
        interaction.user.guild_permissions.administrator
        or has_role(interaction, cfg["ADMIN_ROLE"])
    )

def is_mod_user(interaction: discord.Interaction) -> bool:
    cfg = get_guild_config(interaction.client.db, interaction.guild.id)
    return is_admin_user(interaction) or has_role(interaction, cfg["STAFF_ROLE"], cfg["MOD_ROLE"])

def is_staff_user(interaction: discord.Interaction) -> bool:
    cfg = get_guild_config(interaction.client.db, interaction.guild.id)
    return is_admin_user(interaction) or has_role(interaction, cfg["STAFF_ROLE"])

# ---------------------------------------------------------------------------
# Reusable app_commands check decorators
# ---------------------------------------------------------------------------

def admin_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if is_admin_user(interaction): return True
        raise app_commands.CheckFailure("❌ Admins only!")
    return app_commands.check(predicate)

def mod_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if is_mod_user(interaction): return True
        raise app_commands.CheckFailure("❌ You need the Moderator or Staff role.")
    return app_commands.check(predicate)

def staff_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if is_staff_user(interaction): return True
        raise app_commands.CheckFailure("❌ Staff only!")
    return app_commands.check(predicate)