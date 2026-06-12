import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import io
from datetime import datetime, timezone
from cogs.config import (
    STAFF_ROLE,
    SELLER_ROLES,
    TICKET_PREFIXES,
    staff_only,
    admin_only,
    get_guild_config,
)

# ---------------------------------------------------------------------------
# Configuration - Set your default transcript channel ID here
# ---------------------------------------------------------------------------
DEFAULT_TRANSCRIPT_CHANNEL_ID = 1515122425556111511 # Replace with your actual default channel ID

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def get_creator_name(channel: discord.TextChannel) -> str:
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

async def create_ticket_channel(interaction: discord.Interaction, cfg: dict, category: str, answers: dict):
    """Creates the ticket channel and posts the answers embed."""
    uname = interaction.user.name.lower()
    dc_cat = discord.utils.get(interaction.guild.categories, name=cfg["cat"])
    if not dc_cat:
        dc_cat = await interaction.guild.create_category(cfg["cat"])
        await dc_cat.set_permissions(interaction.guild.default_role, read_messages=False)

    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(
            read_messages=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
        ),
    }
    for role_name in cfg["allow"]:
        role = discord.utils.get(interaction.guild.roles, name=role_name)
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
            )

    channel = await interaction.guild.create_text_channel(
        name=f"ticket-{uname}",
        category=dc_cat,
        overwrites=overwrites,
        topic=f"Ticket by {interaction.user.name} | {category}",
    )

    embed = discord.Embed(
        title=f"{cfg['emoji']} {category} Ticket",
        description=f"### Welcome {interaction.user.mention}!\n\n━━━━━━━━━━━━━━━━━━",
        color=cfg["color"],
        timestamp=datetime.now(timezone.utc),
    )
    for question, answer in answers.items():
        embed.add_field(name=question, value=answer or "*No answer provided*", inline=False)

    embed.add_field(name="Created By", value=interaction.user.mention, inline=True)
    embed.add_field(name="Category", value=category, inline=True)
    embed.set_footer(text=f"Channel ID: {channel.id}")
    if interaction.guild.icon:
        embed.set_thumbnail(url=interaction.guild.icon.url)

    view = TicketView()
    await channel.send(embed=embed, view=view)
    mentions = " ".join(
        role.mention for rn in cfg["ping"] if (role := discord.utils.get(interaction.guild.roles, name=rn))
    )
    if mentions:
        await channel.send(f"{mentions}\nNew **{category}** ticket from {interaction.user.mention}!")

    await interaction.followup.send(f"✅ Ticket created: {channel.mention}", ephemeral=True)

async def check_existing_ticket(interaction: discord.Interaction) -> bool:
    """Returns True (and notifies user) if they already have an open ticket."""
    uname = interaction.user.name.lower()
    for ch in interaction.guild.text_channels:
        if is_ticket_channel(ch) and ch.name.endswith(f"-{uname}"):
            await interaction.response.send_message(
                f"❌ You already have an open ticket: {ch.mention}", ephemeral=True
            )
            return True
    return False

# ---------------------------------------------------------------------------
# Transcript & Close Helper
# ---------------------------------------------------------------------------
async def _close_ticket(channel: discord.TextChannel, closed_by: discord.Member, db):
    """Generates transcript, sends it, and deletes the channel."""
    guild = channel.guild
    creator_name = get_creator_name(channel)

    # 1. Generate Transcript
    messages = []
    try:
        async for msg in channel.history(limit=None, oldest_first=True):
            timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M UTC")
            content = msg.content
            if msg.attachments:
                attachment_urls = ", ".join(a.url for a in msg.attachments)
                content += f" [Attachments: {attachment_urls}]"
            messages.append(f"[{timestamp}] {msg.author}: {content}")
    except Exception as e:
        print(f"Error fetching messages for transcript: {e}")

    transcript_text = "\n".join(messages) if messages else "No messages were sent."
    transcript_bytes = transcript_text.encode('utf-8')
    file = discord.File(fp=io.BytesIO(transcript_bytes), filename=f"transcript-{channel.name}.txt")

    # 2. Send to Transcript Channel (from website config with default fallback)
    try:
        cfg = get_guild_config(db, guild.id)
        transcript_channel_id = cfg.get("TRANSCRIPT_CHANNEL_ID")

        # Set default if null or not configured
        if transcript_channel_id is None:
            transcript_channel_id = DEFAULT_TRANSCRIPT_CHANNEL_ID
            print(f"Using default transcript channel ID: {transcript_channel_id}")

        if transcript_channel_id:
            t_channel = guild.get_channel(transcript_channel_id)
            if t_channel:
                try:
                    t_embed = discord.Embed(
                        title=f"📑 Ticket Closed: {channel.name}",
                        description=f"**Category:** {channel.topic.split('|')[1].strip() if '|' in channel.topic else 'Unknown'}\n**Closed By:** {closed_by.mention}",
                        color=0x2b2d31,
                        timestamp=datetime.now(timezone.utc)
                    )
                    await t_channel.send(embed=t_embed, file=file)
                except discord.Forbidden:
                    print(f"Missing permissions to send transcript to {t_channel.name}")
            else:
                print(f"Transcript channel with ID {transcript_channel_id} not found")
        else:
            print("No transcript channel configured, skipping transcript save")
    except Exception as e:
        print(f"Error sending transcript to channel: {e}")

    # 3. Send to Ticket Creator DM
    try:
        creator_member = guild.get_member_named(creator_name) or discord.utils.get(guild.members, name=creator_name)
        if creator_member:
            try:
                dm_embed = discord.Embed(
                    title=f"📑 Ticket Closed: {channel.name}",
                    description=f"Your ticket in **{guild.name}** was closed by {closed_by.mention}. Here is your transcript:",
                    color=0x2b2d31
                )
                dm_file = discord.File(fp=io.BytesIO(transcript_bytes), filename=f"transcript-{channel.name}.txt")
                await creator_member.send(embed=dm_embed, file=dm_file)
            except discord.HTTPException:
                pass  # DMs closed
    except Exception as e:
        print(f"Error sending transcript to DM: {e}")

    # 4. Delete Channel (Always run this, even if transcript fails)
    try:
        await channel.delete()
    except discord.NotFound:
        pass
    except Exception as e:
        print(f"Error deleting channel: {e}")

# ---------------------------------------------------------------------------
# Modals — one per category (Keep as is)
# ---------------------------------------------------------------------------
class BaseBuyingModal(discord.ui.Modal, title="🏠 Base Buying Ticket"):
    q1 = discord.ui.TextInput(label="What type of base are you looking for?", style=discord.TextStyle.short, required=True)
    q2 = discord.ui.TextInput(label="What is your budget?", style=discord.TextStyle.short, required=True)
    q3 = discord.ui.TextInput(label="Any specific requirements?", style=discord.TextStyle.paragraph, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets_base_buying import BASE_CFG
        await create_ticket_channel(interaction, BASE_CFG, "Base Buying", {
            self.q1.label: self.q1.value,
            self.q2.label: self.q2.value,
            self.q3.label: self.q3.value,
        })

class BedrockModal(discord.ui.Modal, title="🕳️ Bedrock Hole Ticket"):
    q1 = discord.ui.TextInput(label="What size hole do you need?", style=discord.TextStyle.short, required=True)
    q2 = discord.ui.TextInput(label="What is your budget?", style=discord.TextStyle.short, required=True)
    q3 = discord.ui.TextInput(label="Preferred location?", style=discord.TextStyle.paragraph, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets_bedrock import BEDROCK_CFG
        await create_ticket_channel(interaction, BEDROCK_CFG, "Bedrock Hole Buying", {
            self.q1.label: self.q1.value,
            self.q2.label: self.q2.value,
            self.q3.label: self.q3.value,
        })

class SpawnerModal(discord.ui.Modal, title="🔄 Spawner Trading Ticket"):
    q1 = discord.ui.TextInput(label="Are you buying or selling?", style=discord.TextStyle.short, required=True)
    q2 = discord.ui.TextInput(label="What spawner type?", style=discord.TextStyle.short, required=True)
    q3 = discord.ui.TextInput(label="Quantity and price?", style=discord.TextStyle.paragraph, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets_spawner import SPAWNER_CFG
        await create_ticket_channel(interaction, SPAWNER_CFG, "Spawner Trading", {
            self.q1.label: self.q1.value,
            self.q2.label: self.q2.value,
            self.q3.label: self.q3.value,
        })

class BuildingModal(discord.ui.Modal, title="🏗️ Building Ticket"):
    q1 = discord.ui.TextInput(label="What is your IGN?", style=discord.TextStyle.short, required=True)
    q2 = discord.ui.TextInput(label="What is your budget?", style=discord.TextStyle.short, required=True)
    q3 = discord.ui.TextInput(label="What base do you need?", style=discord.TextStyle.short, required=True)
    q4 = discord.ui.TextInput(label="Specific requirements?", style=discord.TextStyle.paragraph, required=False)
    q5 = discord.ui.TextInput(label="How soon do you need the base?", style=discord.TextStyle.short, required=True, placeholder="ASAP / Within a week / No rush")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets_building import BUILDING_CFG
        await create_ticket_channel(interaction, BUILDING_CFG, "Building", {
            self.q1.label: self.q1.value,
            self.q2.label: self.q2.value,
            self.q3.label: self.q3.value,
            self.q4.label: self.q4.value,
            self.q5.label: self.q5.value,
        })

class SupportModal(discord.ui.Modal, title="❓ Support Ticket"):
    q1 = discord.ui.TextInput(label="What do you need help with?", style=discord.TextStyle.short, required=True)
    q2 = discord.ui.TextInput(label="Please provide as much detail as possible", style=discord.TextStyle.paragraph, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets_support import SUPPORT_CFG
        await create_ticket_channel(interaction, SUPPORT_CFG, "General Support", {
            self.q1.label: self.q1.value,
            self.q2.label: self.q2.value,
        })

class ScamModal(discord.ui.Modal, title="⚠️ Scam Report"):
    q1 = discord.ui.TextInput(label="Who scammed you?", style=discord.TextStyle.short, required=True)
    q2 = discord.ui.TextInput(label="What happened?", style=discord.TextStyle.paragraph, required=True)
    q3 = discord.ui.TextInput(label="Do you have proof?", style=discord.TextStyle.short, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets_support import SCAM_CFG
        await create_ticket_channel(interaction, SCAM_CFG, "Scam Report", {
            self.q1.label: self.q1.value,
            self.q2.label: self.q2.value,
            self.q3.label: self.q3.value,
        })

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
        await interaction.response.send_message("🔒 Closing ticket and generating transcript...", ephemeral=True)
        await _close_ticket(interaction.channel, interaction.user, interaction.client.db)

# ---------------------------------------------------------------------------
# Panel views — buttons open modals (Keep as is)
# ---------------------------------------------------------------------------
class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🏠 Base Buying", style=discord.ButtonStyle.primary, custom_id="tp_base_v14", row=0)
    async def btn_base(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction): return
        await interaction.response.send_modal(BaseBuyingModal())

    @discord.ui.button(label="🕳️ Bedrock Hole", style=discord.ButtonStyle.primary, custom_id="tp_bedrock_v14", row=0)
    async def btn_bedrock(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction): return
        await interaction.response.send_modal(BedrockModal())

    @discord.ui.button(label="🔄 Spawner Trade", style=discord.ButtonStyle.primary, custom_id="tp_spawner_v14", row=0)
    async def btn_spawner(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction): return
        await interaction.response.send_modal(SpawnerModal())

    @discord.ui.button(label="🏗️ Building", style=discord.ButtonStyle.primary, custom_id="tp_building_v14", row=1)
    async def btn_building(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction): return
        await interaction.response.send_modal(BuildingModal())

    @discord.ui.button(label="❓ Support", style=discord.ButtonStyle.secondary, custom_id="tp_support_v14", row=1)
    async def btn_support(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction): return
        await interaction.response.send_modal(SupportModal())

    @discord.ui.button(label="⚠️ Scam Report", style=discord.ButtonStyle.danger, custom_id="tp_scam_v14", row=1)
    async def btn_scam(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction): return
        await interaction.response.send_modal(ScamModal())

class BaseBuyingPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🏠 Open Base Buying Ticket", style=discord.ButtonStyle.primary, custom_id="sp_base_v14")
    async def btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction): return
        await interaction.response.send_modal(BaseBuyingModal())

class BedrockPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🕳️ Open Bedrock Hole Ticket", style=discord.ButtonStyle.primary, custom_id="sp_bedrock_v14")
    async def btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction): return
        await interaction.response.send_modal(BedrockModal())

class SpawnerPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔄 Open Spawner Trade Ticket", style=discord.ButtonStyle.primary, custom_id="sp_spawner_v14")
    async def btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction): return
        await interaction.response.send_modal(SpawnerModal())

class BuildingPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🏗️ Open Building Ticket", style=discord.ButtonStyle.primary, custom_id="sp_building_v14")
    async def btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction): return
        await interaction.response.send_modal(BuildingModal())

class SupportPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="❓ Open Support Ticket", style=discord.ButtonStyle.secondary, custom_id="sp_support_v14", row=0)
    async def btn_support(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction): return
        await interaction.response.send_modal(SupportModal())

    @discord.ui.button(label="⚠️ Report a Scam", style=discord.ButtonStyle.danger, custom_id="sp_scam_v14", row=0)
    async def btn_scam(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction): return
        await interaction.response.send_modal(ScamModal())

# ---------------------------------------------------------------------------
# Helper: clear bot messages before posting a panel
# ---------------------------------------------------------------------------
async def _clear_bot_messages(channel: discord.TextChannel, bot_user):
    async for msg in channel.history(limit=20):
        if msg.author == bot_user:
            try:
                await msg.delete()
            except discord.HTTPException:
                pass

# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------
class TicketsBase(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Re-register all persistent views so buttons survive restarts
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

    @app_commands.command(name="close", description="Close the current ticket")
    async def close(self, interaction: discord.Interaction):
        ch = interaction.channel
        if not is_ticket_channel(ch):
            await interaction.response.send_message("❌ This command can only be used in ticket channels.", ephemeral=True)
            return

        has_perm = any(
            (role := discord.utils.get(interaction.guild.roles, name=rn)) and role in interaction.user.roles
            for rn in [STAFF_ROLE, *SELLER_ROLES]
        )
        if not has_perm:
            has_perm = interaction.user.name.lower() == get_creator_name(ch)

        if not has_perm:
            await interaction.response.send_message("❌ You don't have permission to close this ticket.", ephemeral=True)
            return

        await interaction.response.send_message("🔒 Closing ticket and generating transcript...", ephemeral=True)
        await _close_ticket(ch, interaction.user, self.bot.db)

async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsBase(bot))