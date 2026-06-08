import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime, timezone
from cogs.config import (
    STAFF_ROLE, SELLER_ROLES, TICKET_PREFIXES,
    staff_only, admin_only,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def get_creator_name(channel: discord.TextChannel) -> str:
    """Return the lowercased creator username from the channel topic or name."""
    if channel.topic and "Ticket by " in channel.topic:
        try:
            return channel.topic.split("Ticket by ")[1].split(" |")[0].strip().lower()
        except IndexError:
            pass
    name = channel.name
    for prefix in TICKET_PREFIXES:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return name.lower()


def is_ticket_channel(channel: discord.TextChannel) -> bool:
    return any(channel.name.startswith(p) for p in TICKET_PREFIXES)


async def open_ticket(interaction: discord.Interaction, cfg: dict, category: str):
    """Shared ticket creation logic used by all category cogs."""
    await interaction.response.defer(ephemeral=True)

    uname = interaction.user.name.lower()
    for ch in interaction.guild.text_channels:
        if is_ticket_channel(ch) and ch.name.endswith(f"-{uname}"):
            await interaction.followup.send(
                f"❌ You already have an open ticket: {ch.mention}", ephemeral=True
            )
            return

    dc_cat = discord.utils.get(interaction.guild.categories, name=cfg["cat"])
    if not dc_cat:
        dc_cat = await interaction.guild.create_category(cfg["cat"])
        await dc_cat.set_permissions(interaction.guild.default_role, read_messages=False)

    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(
            read_messages=True, send_messages=True,
            read_message_history=True, attach_files=True,
        ),
    }
    for role_name in cfg["allow"]:
        role = discord.utils.get(interaction.guild.roles, name=role_name)
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                read_messages=True, send_messages=True,
                read_message_history=True, attach_files=True,
            )

    channel = await interaction.guild.create_text_channel(
        name=f"ticket-{uname}",
        category=dc_cat,
        overwrites=overwrites,
        topic=f"Ticket by {interaction.user.name} | {category}",
    )

    embed = discord.Embed(
        title=f"{cfg['emoji']} {category} Ticket",
        description=(
            f"### Welcome {interaction.user.mention}!\n\n"
            "Please answer the questions below:\n\n━━━━━━━━━━━━━━━━━━"
        ),
        color=cfg["color"],
        timestamp=datetime.now(timezone.utc),
    )
    for i, q in enumerate(cfg["q"], 1):
        embed.add_field(name=f"Question {i}", value=q, inline=False)
    embed.add_field(name="Created By", value=interaction.user.mention, inline=True)
    embed.add_field(name="Category",   value=category,                inline=True)
    embed.set_footer(text=f"Channel ID: {channel.id}")
    if interaction.guild.icon:
        embed.set_thumbnail(url=interaction.guild.icon.url)

    view = TicketView()
    await channel.send(embed=embed, view=view)

    mentions = " ".join(
        role.mention
        for rn in cfg["ping"]
        if (role := discord.utils.get(interaction.guild.roles, name=rn))
    )
    if mentions:
        await channel.send(f"{mentions}\nNew **{category}** ticket from {interaction.user.mention}!")

    await interaction.followup.send(f"✅ Ticket created: {channel.mention}", ephemeral=True)


# ---------------------------------------------------------------------------
# Persistent TicketView (inside a ticket channel)
# ---------------------------------------------------------------------------

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Request Close", style=discord.ButtonStyle.grey, custom_id="req_close_v14")
    async def request_close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        creator_name = get_creator_name(interaction.channel)
        if interaction.user.name.lower() != creator_name:
            await interaction.response.send_message(
                "❌ Only the ticket creator can request a close.", ephemeral=True
            )
            return
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE)
        mention = staff_role.mention if staff_role else "@Staff"
        await interaction.response.send_message(
            f"{mention}\n**{interaction.user.mention}** has requested to close this ticket."
        )

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="close_v14")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE)
        if not staff_role or staff_role not in interaction.user.roles:
            await interaction.response.send_message("❌ Staff only!", ephemeral=True)
            return
        await interaction.response.send_message("🔒 Closing ticket in 5 seconds…")
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except discord.NotFound:
            pass


# ---------------------------------------------------------------------------
# Persistent panel view — buttons instead of dropdown
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Full panel view (all 6 buttons)
# ---------------------------------------------------------------------------

class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🏠 Base Buying",   style=discord.ButtonStyle.primary,   custom_id="tp_base_v14",     row=0)
    async def btn_base(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.tickets_base_buying import BASE_CFG
        await open_ticket(interaction, BASE_CFG, "Base Buying")

    @discord.ui.button(label="🕳️ Bedrock Hole",  style=discord.ButtonStyle.primary,   custom_id="tp_bedrock_v14",  row=0)
    async def btn_bedrock(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.tickets_bedrock import BEDROCK_CFG
        await open_ticket(interaction, BEDROCK_CFG, "Bedrock Hole Buying")

    @discord.ui.button(label="🔄 Spawner Trade", style=discord.ButtonStyle.primary,   custom_id="tp_spawner_v14",  row=0)
    async def btn_spawner(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.tickets_spawner import SPAWNER_CFG
        await open_ticket(interaction, SPAWNER_CFG, "Spawner Trading")

    @discord.ui.button(label="🏗️ Building",      style=discord.ButtonStyle.primary,   custom_id="tp_building_v14", row=1)
    async def btn_building(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.tickets_building import BUILDING_CFG
        await open_ticket(interaction, BUILDING_CFG, "Building")

    @discord.ui.button(label="❓ Support",        style=discord.ButtonStyle.secondary, custom_id="tp_support_v14",  row=1)
    async def btn_support(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.tickets_support import SUPPORT_CFG
        await open_ticket(interaction, SUPPORT_CFG, "General Support")

    @discord.ui.button(label="⚠️ Scam Report",   style=discord.ButtonStyle.danger,    custom_id="tp_scam_v14",     row=1)
    async def btn_scam(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.tickets_support import SCAM_CFG
        await open_ticket(interaction, SCAM_CFG, "Scam Report")


# ---------------------------------------------------------------------------
# Single-category panel views
# ---------------------------------------------------------------------------

class BaseBuyingPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🏠 Open Base Buying Ticket", style=discord.ButtonStyle.primary, custom_id="sp_base_v14")
    async def btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.tickets_base_buying import BASE_CFG
        await open_ticket(interaction, BASE_CFG, "Base Buying")


class BedrockPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🕳️ Open Bedrock Hole Ticket", style=discord.ButtonStyle.primary, custom_id="sp_bedrock_v14")
    async def btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.tickets_bedrock import BEDROCK_CFG
        await open_ticket(interaction, BEDROCK_CFG, "Bedrock Hole Buying")


class SpawnerPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔄 Open Spawner Trade Ticket", style=discord.ButtonStyle.primary, custom_id="sp_spawner_v14")
    async def btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.tickets_spawner import SPAWNER_CFG
        await open_ticket(interaction, SPAWNER_CFG, "Spawner Trading")


class BuildingPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🏗️ Open Building Ticket", style=discord.ButtonStyle.primary, custom_id="sp_building_v14")
    async def btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.tickets_building import BUILDING_CFG
        await open_ticket(interaction, BUILDING_CFG, "Building")


class SupportPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="❓ Open Support Ticket",   style=discord.ButtonStyle.secondary, custom_id="sp_support_v14", row=0)
    async def btn_support(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.tickets_support import SUPPORT_CFG
        await open_ticket(interaction, SUPPORT_CFG, "General Support")

    @discord.ui.button(label="⚠️ Report a Scam",        style=discord.ButtonStyle.danger,    custom_id="sp_scam_v14",    row=0)
    async def btn_scam(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.tickets_support import SCAM_CFG
        await open_ticket(interaction, SCAM_CFG, "Scam Report")


# ---------------------------------------------------------------------------
# Helper: clear bot messages in a channel before posting a panel
# ---------------------------------------------------------------------------

async def _clear_bot_messages(channel: discord.TextChannel, bot_user):
    async for msg in channel.history(limit=20):
        if msg.author == bot_user:
            try:
                await msg.delete()
            except discord.HTTPException:
                pass


# ---------------------------------------------------------------------------
# Cog — ticket management commands + panel commands
# ---------------------------------------------------------------------------

class TicketsBase(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(TicketView())
        bot.add_view(TicketPanelView())
        bot.add_view(BaseBuyingPanelView())
        bot.add_view(BedrockPanelView())
        bot.add_view(SpawnerPanelView())
        bot.add_view(BuildingPanelView())
        bot.add_view(SupportPanelView())

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        msg = str(error) if isinstance(error, app_commands.CheckFailure) else f"❌ Unexpected error: {error}"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    # ------------------------------------------------------------------
    # Full panel (all categories)
    # ------------------------------------------------------------------

    @app_commands.command(name="ticketpanel", description="Post the full ticket panel (all categories)")
    @admin_only()
    async def ticketpanel(self, interaction: discord.Interaction):
        await _clear_bot_messages(interaction.channel, self.bot.user)
        embed = discord.Embed(
            title="🎫 Support Tickets",
            description=(
                "### Click a button below to open a ticket!\n\n"
                "🏠 **Base Buying** — Purchase a base\n"
                "🕳️ **Bedrock Hole** — Buy a bedrock hole\n"
                "🔄 **Spawner Trade** — Buy or sell spawners\n"
                "🏗️ **Building** — Building services\n"
                "❓ **Support** — General help\n"
                "⚠️ **Scam Report** — Report a scam"
            ),
            color=0x2b2d31,
        )
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        await interaction.response.send_message(embed=embed, view=TicketPanelView())

    # ------------------------------------------------------------------
    # Per-category panels
    # ------------------------------------------------------------------

    @app_commands.command(name="ticketpanel_basebuying", description="Post the Base Buying ticket panel")
    @admin_only()
    async def ticketpanel_basebuying(self, interaction: discord.Interaction):
        await _clear_bot_messages(interaction.channel, self.bot.user)
        embed = discord.Embed(
            title="🏠 Base Buying",
            description="Click the button below to open a **Base Buying** ticket.",
            color=0x2ecc71,
        )
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        await interaction.response.send_message(embed=embed, view=BaseBuyingPanelView())

    @app_commands.command(name="ticketpanel_bedrock", description="Post the Bedrock Hole ticket panel")
    @admin_only()
    async def ticketpanel_bedrock(self, interaction: discord.Interaction):
        await _clear_bot_messages(interaction.channel, self.bot.user)
        embed = discord.Embed(
            title="🕳️ Bedrock Hole Buying",
            description="Click the button below to open a **Bedrock Hole** ticket.",
            color=0x95a5a6,
        )
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        await interaction.response.send_message(embed=embed, view=BedrockPanelView())

    @app_commands.command(name="ticketpanel_spawner", description="Post the Spawner Trading ticket panel")
    @admin_only()
    async def ticketpanel_spawner(self, interaction: discord.Interaction):
        await _clear_bot_messages(interaction.channel, self.bot.user)
        embed = discord.Embed(
            title="🔄 Spawner Trading",
            description="Click the button below to open a **Spawner Trade** ticket.",
            color=0xf1c40f,
        )
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        await interaction.response.send_message(embed=embed, view=SpawnerPanelView())

    @app_commands.command(name="ticketpanel_building", description="Post the Building ticket panel")
    @admin_only()
    async def ticketpanel_building(self, interaction: discord.Interaction):
        await _clear_bot_messages(interaction.channel, self.bot.user)
        embed = discord.Embed(
            title="🏗️ Building",
            description="Click the button below to open a **Building** ticket.",
            color=0x9b59b6,
        )
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        await interaction.response.send_message(embed=embed, view=BuildingPanelView())

    @app_commands.command(name="ticketpanel_support", description="Post the Support & Scam Report ticket panel")
    @admin_only()
    async def ticketpanel_support(self, interaction: discord.Interaction):
        await _clear_bot_messages(interaction.channel, self.bot.user)
        embed = discord.Embed(
            title="❓ Support & Reports",
            description=(
                "Click a button below to open a ticket.\n\n"
                "❓ **Support** — General help\n"
                "⚠️ **Scam Report** — Report a scam"
            ),
            color=0x3498db,
        )
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        await interaction.response.send_message(embed=embed, view=SupportPanelView())

    @app_commands.command(name="rename", description="Rename the current ticket channel")
    @app_commands.describe(new_name="New channel name (replaces current name entirely, prefix is kept)")
    @staff_only()
    async def rename(self, interaction: discord.Interaction, new_name: str):
        ch = interaction.channel
        prefix = None
        for p in TICKET_PREFIXES:
            if ch.name.startswith(p):
                prefix = p
                break

        if not prefix:
            await interaction.response.send_message(
                "❌ This command can only be used in ticket channels.", ephemeral=True
            )
            return

        clean = new_name.lower().replace(" ", "-")[:50]
        new_channel_name = f"{prefix}{clean}"
        try:
            await ch.edit(name=new_channel_name)
            await interaction.response.send_message(f"✅ Channel renamed to `{new_channel_name}`.")
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Rename failed: {e}", ephemeral=True)

    @app_commands.command(name="add", description="Add a user to the current ticket")
    @app_commands.describe(member="The member to add")
    @staff_only()
    async def add(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.channel.set_permissions(
            member, read_messages=True, send_messages=True,
            read_message_history=True, attach_files=True,
        )
        await interaction.response.send_message(f"✅ {member.mention} has been added to this ticket.")

    @app_commands.command(name="remove", description="Remove a user from the current ticket")
    @app_commands.describe(member="The member to remove")
    @staff_only()
    async def remove(self, interaction: discord.Interaction, member: discord.Member):
        if member == interaction.user:
            await interaction.response.send_message("❌ You can't remove yourself!", ephemeral=True)
            return
        await interaction.channel.set_permissions(member, read_messages=False, send_messages=False)
        await interaction.response.send_message(f"✅ {member.mention} has been removed from this ticket.")

    @app_commands.command(name="close", description="Close the current ticket")
    async def close(self, interaction: discord.Interaction):
        ch = interaction.channel
        if not is_ticket_channel(ch):
            await interaction.response.send_message(
                "❌ This command can only be used in ticket channels.", ephemeral=True
            )
            return

        has_perm = any(
            (role := discord.utils.get(interaction.guild.roles, name=rn)) and role in interaction.user.roles
            for rn in [STAFF_ROLE, *SELLER_ROLES]
        )
        if not has_perm:
            has_perm = interaction.user.name.lower() == get_creator_name(ch)

        if not has_perm:
            await interaction.response.send_message(
                "❌ You don't have permission to close this ticket.", ephemeral=True
            )
            return

        await interaction.response.send_message("🔒 Closing ticket in 5 seconds…")
        await asyncio.sleep(5)
        try:
            await ch.delete()
        except discord.NotFound:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsBase(bot))
