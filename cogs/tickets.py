import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime, timezone

STAFF_ROLE = "Staff"
BASE_BUYING_ROLE = "Base Seller"
BEDROCK_ROLE = "Bedrock Seller"
SPAWNER_ROLE = "Spawner Trader"
BUILDING_ROLE = "Builder"

SELLER_ROLES = [BASE_BUYING_ROLE, BEDROCK_ROLE, SPAWNER_ROLE, BUILDING_ROLE]


# ---------------------------------------------------------------------------
# Permission checks
# ---------------------------------------------------------------------------

def is_staff():
    async def predicate(interaction: discord.Interaction) -> bool:
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE)
        if staff_role and staff_role in interaction.user.roles:
            return True
        # Don't call send_message here – let the error handler do it cleanly
        raise app_commands.CheckFailure("❌ Staff only!")
    return app_commands.check(predicate)


def is_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        raise app_commands.CheckFailure("❌ Admins only!")
    return app_commands.check(predicate)


# ---------------------------------------------------------------------------
# Helper: resolve ticket creator from channel
# ---------------------------------------------------------------------------

def _get_creator_name(channel: discord.TextChannel) -> str:
    """Return the lowercased creator username from the channel topic or name."""
    if channel.topic and "Ticket by " in channel.topic:
        # Topic format: "Ticket by Username | Category"
        try:
            return channel.topic.split("Ticket by ")[1].split(" |")[0].strip().lower()
        except IndexError:
            pass
    # Fallback: strip known prefixes from channel name
    name = channel.name
    for prefix in ("claimed-", "ticket-"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return name.lower()


# ---------------------------------------------------------------------------
# Persistent views
# ---------------------------------------------------------------------------

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Request Close", style=discord.ButtonStyle.red, custom_id="req_close_v13")
    async def request_close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        creator_name = _get_creator_name(interaction.channel)

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

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="close_v13")
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


class CategorySelect(discord.ui.Select):
    CONFIGS = {
        "Base Buying": {
            "cat": "Base Buying",
            "ping": [STAFF_ROLE, BASE_BUYING_ROLE],
            "allow": [STAFF_ROLE, BASE_BUYING_ROLE],
            "color": 0x2ecc71, "emoji": "🏠",
            "q": ["What type of base are you looking for?", "What is your budget?", "Any specific requirements?"],
        },
        "Bedrock Hole Buying": {
            "cat": "Bedrock Holes",
            "ping": [STAFF_ROLE, BEDROCK_ROLE],
            "allow": [STAFF_ROLE, BEDROCK_ROLE],
            "color": 0x95a5a6, "emoji": "🕳️",
            "q": ["What size hole do you need?", "What is your budget?", "Preferred location?"],
        },
        "Spawner Trading": {
            "cat": "Spawner Trading",
            "ping": [STAFF_ROLE, SPAWNER_ROLE],
            "allow": [STAFF_ROLE, SPAWNER_ROLE],
            "color": 0xf1c40f, "emoji": "🔄",
            "q": ["Are you buying or selling?", "What spawner type?", "Quantity and price?"],
        },
        "Building": {
            "cat": "Building",
            "ping": [BUILDING_ROLE],
            "allow": [STAFF_ROLE, BUILDING_ROLE],
            "color": 0x9b59b6, "emoji": "🏗️",
            "q": ["What do you need built?", "What is your budget?", "Do you have a deadline?"],
        },
        "General Support": {
            "cat": "General Support",
            "ping": [STAFF_ROLE],
            "allow": [STAFF_ROLE],
            "color": 0x3498db, "emoji": "❓",
            "q": ["What do you need help with?", "Please provide as much detail as possible."],
        },
        "Scam Report": {
            "cat": "Scam Reports",
            "ping": [STAFF_ROLE],
            "allow": [STAFF_ROLE],
            "color": 0xe74c3c, "emoji": "⚠️",
            "q": ["Who scammed you?", "What happened?", "Do you have proof?"],
        },
    }

    SELECT_MAP = {
        "Base Buying": "Base Buying",
        "Bedrock Hole": "Bedrock Hole Buying",
        "Spawner Trade": "Spawner Trading",
        "Building": "Building",
        "Support": "General Support",
        "Scam Report": "Scam Report",
    }

    def __init__(self):
        options = [
            discord.SelectOption(label="Base Buying",   description="Purchase a base",        emoji="🏠"),
            discord.SelectOption(label="Bedrock Hole",  description="Buy a bedrock hole",      emoji="🕳️"),
            discord.SelectOption(label="Spawner Trade", description="Buy/sell spawners",       emoji="🔄"),
            discord.SelectOption(label="Building",      description="Building services",       emoji="🏗️"),
            discord.SelectOption(label="Support",       description="General help",            emoji="❓"),
            discord.SelectOption(label="Scam Report",   description="Report a scam",           emoji="⚠️"),
        ]
        super().__init__(
            placeholder="Select a ticket category…",
            options=options,
            custom_id="cat_select_v13",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Check for an existing open ticket owned by this user
        uname = interaction.user.name.lower()
        for ch in interaction.guild.text_channels:
            if (ch.name.startswith("ticket-") or ch.name.startswith("claimed-")) and \
                    ch.name.endswith(f"-{uname}"):
                await interaction.followup.send(
                    f"❌ You already have an open ticket: {ch.mention}", ephemeral=True
                )
                try:
                    await interaction.message.edit(view=TicketPanelView())
                except Exception:
                    pass
                return

        category = self.SELECT_MAP[self.values[0]]
        cfg = self.CONFIGS[category]

        # Ensure Discord category exists
        dc_cat = discord.utils.get(interaction.guild.categories, name=cfg["cat"])
        if not dc_cat:
            dc_cat = await interaction.guild.create_category(cfg["cat"])
            await dc_cat.set_permissions(interaction.guild.default_role, read_messages=False)

        # Build permission overwrites
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

        # Ping relevant roles
        mentions = " ".join(
            role.mention
            for rn in cfg["ping"]
            if (role := discord.utils.get(interaction.guild.roles, name=rn))
        )
        if mentions:
            await channel.send(f"{mentions}\nNew **{category}** ticket from {interaction.user.mention}!")

        await interaction.followup.send(f"✅ Ticket created: {channel.mention}", ephemeral=True)

        # Reset the dropdown back to the placeholder by re-sending a fresh view
        try:
            await interaction.message.edit(view=TicketPanelView())
        except Exception:
            pass


class TicketPanelView(discord.ui.View):
    """Persistent view that holds the CategorySelect dropdown."""
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CategorySelect())


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Register persistent views so buttons survive bot restarts
        bot.add_view(TicketView())
        bot.add_view(TicketPanelView())

    # ------------------------------------------------------------------
    # Global slash-command error handler
    # ------------------------------------------------------------------
    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        msg = str(error)
        if isinstance(error, app_commands.CheckFailure):
            msg = str(error)
        else:
            msg = f"❌ Unexpected error: {error}"

        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    @app_commands.command(name="ticketpanel", description="Post the ticket panel in this channel")
    @is_admin()
    async def ticketpanel(self, interaction: discord.Interaction):
        # Clean up old bot messages in this channel (last 20)
        async for msg in interaction.channel.history(limit=20):
            if msg.author == self.bot.user:
                try:
                    await msg.delete()
                except discord.HTTPException:
                    pass

        embed = discord.Embed(
            title="🎫 Support Tickets",
            description=(
                "### Select a category below to open a ticket!\n\n"
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

    @app_commands.command(name="rename", description="Rename the current ticket channel")
    @app_commands.describe(new_name="New name for the ticket (no spaces needed)")
    @is_staff()
    async def rename(self, interaction: discord.Interaction, new_name: str):
        ch = interaction.channel
        if not (ch.name.startswith("ticket-") or ch.name.startswith("claimed-")):
            await interaction.response.send_message("❌ This command can only be used in ticket channels.", ephemeral=True)
            return

        clean = new_name.lower().replace(" ", "-")[:50]
        try:
            await ch.edit(name=f"ticket-{clean}")
            await interaction.response.send_message(f"✅ Channel renamed to `ticket-{clean}`.")
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Rename failed: {e}", ephemeral=True)

    @app_commands.command(name="add", description="Add a user to the current ticket")
    @app_commands.describe(member="The member to add")
    @is_staff()
    async def add(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.channel.set_permissions(
            member, read_messages=True, send_messages=True,
            read_message_history=True, attach_files=True,
        )
        await interaction.response.send_message(f"✅ {member.mention} has been added to this ticket.")

    @app_commands.command(name="remove", description="Remove a user from the current ticket")
    @app_commands.describe(member="The member to remove")
    @is_staff()
    async def remove(self, interaction: discord.Interaction, member: discord.Member):
        if member == interaction.user:
            await interaction.response.send_message("❌ You can't remove yourself!", ephemeral=True)
            return
        await interaction.channel.set_permissions(member, read_messages=False, send_messages=False)
        await interaction.response.send_message(f"✅ {member.mention} has been removed from this ticket.")

    @app_commands.command(name="close", description="Close the current ticket")
    async def close(self, interaction: discord.Interaction):
        ch = interaction.channel
        if not (ch.name.startswith("ticket-") or ch.name.startswith("claimed-")):
            await interaction.response.send_message("❌ This command can only be used in ticket channels.", ephemeral=True)
            return

        # Check permissions: staff/seller roles OR the ticket creator
        has_perm = any(
            (role := discord.utils.get(interaction.guild.roles, name=rn)) and role in interaction.user.roles
            for rn in [STAFF_ROLE, *SELLER_ROLES]
        )
        if not has_perm:
            creator = _get_creator_name(ch)
            has_perm = interaction.user.name.lower() == creator

        if not has_perm:
            await interaction.response.send_message("❌ You don't have permission to close this ticket.", ephemeral=True)
            return

        await interaction.response.send_message("🔒 Closing ticket in 5 seconds…")
        await asyncio.sleep(5)
        try:
            await ch.delete()
        except discord.NotFound:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))