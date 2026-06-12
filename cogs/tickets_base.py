import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import io
from datetime import datetime, timezone
from cogs.config import (
    STAFF_ROLE, SELLER_ROLES, TICKET_PREFIXES,
    staff_only, admin_only, get_guild_config,
)

# ✅ DEFAULT FALLBACK TRANSCRIPT CHANNEL ID
DEFAULT_TRANSCRIPT_CHANNEL_ID = 123456789012345678  # <-- CHANGE THIS

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
    uname = interaction.user.name.lower()

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
        description=f"### Welcome {interaction.user.mention}!\n\n━━━━━━━━━━━━━━━━━━",
        color=cfg["color"],
        timestamp=datetime.now(timezone.utc),
    )
    for question, answer in answers.items():
        embed.add_field(name=question, value=answer or "*No answer provided*", inline=False)
    embed.add_field(name="Created By", value=interaction.user.mention, inline=True)
    embed.add_field(name="Category",   value=category,                 inline=True)
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


async def check_existing_ticket(interaction: discord.Interaction) -> bool:
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
    guild = channel.guild
    creator_name = get_creator_name(channel)

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

    file = discord.File(
        fp=io.BytesIO(transcript_bytes),
        filename=f"transcript-{channel.name}.txt"
    )

    # -------------------------------
    # FIXED: DEFAULT FALLBACK LOGIC
    # -------------------------------
    try:
        cfg = get_guild_config(db, guild.id) or {}

        transcript_channel_id = cfg.get("TRANSCRIPT_CHANNEL_ID") or DEFAULT_TRANSCRIPT_CHANNEL_ID

        t_channel = guild.get_channel(int(transcript_channel_id))

        if t_channel:
            t_embed = discord.Embed(
                title=f"📑 Ticket Closed: {channel.name}",
                description=f"**Category:** {channel.topic.split('|')[1].strip() if '|' in channel.topic else 'Unknown'}\n**Closed By:** {closed_by.mention}",
                color=0x2b2d31,
                timestamp=datetime.now(timezone.utc)
            )
            await t_channel.send(embed=t_embed, file=file)

    except Exception as e:
        print(f"Error sending transcript: {e}")

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
                dm_file = discord.File(
                    fp=io.BytesIO(transcript_bytes),
                    filename=f"transcript-{channel.name}.txt"
                )
                await creator_member.send(embed=dm_embed, file=dm_file)
            except discord.HTTPException:
                pass
    except Exception as e:
        print(f"Error sending transcript to DM: {e}")

    # 4. Delete channel
    try:
        await channel.delete()
    except Exception as e:
        print(f"Error deleting channel: {e}")


# ---------------------------------------------------------------------------
# (rest of your file unchanged below this point)
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


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsBase(bot))