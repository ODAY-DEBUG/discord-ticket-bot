import os
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import io
import re
import html
from datetime import datetime, timezone
from bson import ObjectId
from cogs.config import (
    STAFF_ROLE,
    SELLER_ROLES,
    TICKET_PREFIXES,
    staff_only,
    admin_only,
    get_guild_config,
    resolve_role_names,
)
from jinja2 import Template

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
            name = name[len(prefix) :]
            break
    return name.lower()


def is_ticket_channel(channel: discord.TextChannel) -> bool:
    return any(channel.name.startswith(p) for p in TICKET_PREFIXES)


async def create_ticket_channel(interaction: discord.Interaction, cfg: dict, category: str, answers: dict):
    """Creates the ticket channel and posts the answers embed."""
    uname = interaction.user.name.lower()
    db = interaction.client.db
    allow_roles = resolve_role_names(db, interaction.guild.id, cfg["allow"])
    ping_roles = resolve_role_names(db, interaction.guild.id, cfg["ping"])

    dc_cat = discord.utils.get(interaction.guild.categories, name=cfg["cat"])
    if not dc_cat:
        dc_cat = await interaction.guild.create_category(cfg["cat"])
        await dc_cat.set_permissions(interaction.guild.default_role, read_messages=False)

    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(
            read_messages=True, send_messages=True, read_message_history=True, attach_files=True
        ),
    }
    for role_name in allow_roles:
        role = discord.utils.get(interaction.guild.roles, name=role_name)
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                read_messages=True, send_messages=True, read_message_history=True, attach_files=True
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
        role.mention for rn in ping_roles if (role := discord.utils.get(interaction.guild.roles, name=rn))
    )
    if mentions:
        await channel.send(f"{mentions}\nNew **{category}** ticket from {interaction.user.mention}!")

    await interaction.followup.send(f"✅ Ticket created: {channel.mention}", ephemeral=True)


async def check_existing_ticket(interaction: discord.Interaction) -> bool:
    """Returns True (and notifies user) if they already have an open ticket."""
    uname = interaction.user.name.lower()
    for ch in interaction.guild.text_channels:
        if is_ticket_channel(ch) and ch.name.endswith(f"-{uname}"):
            await interaction.response.send_message(f"❌ You already have an open ticket: {ch.mention}", ephemeral=True)
            return True
    return False


# ---------------------------------------------------------------------------
# HTML Transcript Generator
# ---------------------------------------------------------------------------

async def generate_html_transcript(channel: discord.TextChannel, messages: list, closed_by: discord.Member) -> str:
    """Generate an HTML transcript from channel messages."""
    
    # Parse creator name and category from channel topic
    creator_name = "Unknown"
    category = "Unknown"
    if channel.topic:
        if "Ticket by " in channel.topic:
            creator_name = channel.topic.split("Ticket by ")[1].split(" |")[0]
        if "|" in channel.topic:
            category = channel.topic.split("|")[1].strip() if len(channel.topic.split("|")) > 1 else "Unknown"
    
    # Process messages for HTML
    processed_messages = []
    for msg in messages:
        # Escape HTML content
        content = html.escape(msg.get("content", ""))
        
        # Convert markdown-style links to HTML
        content = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2" target="_blank">\1</a>', content)
        
        # Convert code blocks
        content = re.sub(r'```(.*?)```', r'<pre><code>\1</code></pre>', content, flags=re.DOTALL)
        content = re.sub(r'`(.*?)`', r'<code>\1</code>', content)
        
        # Convert newlines to <br>
        content = content.replace("\n", "<br>")
        
        processed_messages.append({
            "author": html.escape(msg.get("author", "Unknown")),
            "timestamp": msg.get("timestamp", ""),
            "content": content,
            "attachments": msg.get("attachments", []),
            "is_bot": msg.get("is_bot", False),
            "is_system": msg.get("is_system", False),
            "avatar_url": msg.get("avatar_url", "")
        })
    
    # HTML Template
    template_str = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ticket Transcript - {{ channel_name }}</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
            background: #1e1f22;
            color: #dbdee1;
            padding: 20px;
        }
        
        .container {
            max-width: 1000px;
            margin: 0 auto;
            background: #2b2d31;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 8px 24px rgba(0,0,0,0.3);
        }
        
        .header {
            background: #1e1f22;
            padding: 30px;
            border-bottom: 1px solid #3f4147;
            text-align: center;
        }
        
        .header h1 {
            font-size: 28px;
            margin-bottom: 10px;
            color: #5865F2;
        }
        
        .header .ticket-id {
            background: #313338;
            display: inline-block;
            padding: 6px 12px;
            border-radius: 6px;
            font-family: monospace;
            font-size: 14px;
            margin-top: 10px;
        }
        
        .info-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            padding: 20px 30px;
            background: #1e1f22;
            border-bottom: 1px solid #3f4147;
        }
        
        .info-item {
            text-align: center;
        }
        
        .info-label {
            font-size: 11px;
            text-transform: uppercase;
            color: #949ba4;
            letter-spacing: 0.5px;
            margin-bottom: 5px;
        }
        
        .info-value {
            font-size: 14px;
            font-weight: 600;
        }
        
        .messages {
            padding: 20px 30px;
        }
        
        .message {
            display: flex;
            gap: 16px;
            padding: 16px;
            margin-bottom: 8px;
            border-radius: 8px;
            transition: background 0.2s;
        }
        
        .message:hover {
            background: #313338;
        }
        
        .avatar {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            background: #5865F2;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            flex-shrink: 0;
        }
        
        .message-content {
            flex: 1;
        }
        
        .message-header {
            display: flex;
            align-items: baseline;
            gap: 10px;
            margin-bottom: 6px;
            flex-wrap: wrap;
        }
        
        .author-name {
            font-weight: 600;
            color: #dbdee1;
        }
        
        .timestamp {
            font-size: 11px;
            color: #949ba4;
        }
        
        .message-text {
            font-size: 15px;
            line-height: 1.4;
            word-wrap: break-word;
        }
        
        .message-text a {
            color: #5865F2;
            text-decoration: none;
        }
        
        .message-text a:hover {
            text-decoration: underline;
        }
        
        .attachment {
            background: #1e1f22;
            padding: 8px 12px;
            border-radius: 6px;
            margin-top: 8px;
            display: inline-block;
            font-size: 13px;
        }
        
        .attachment a {
            color: #5865F2;
            text-decoration: none;
        }
        
        .system-message {
            background: #313338;
            opacity: 0.8;
        }
        
        .system-message .message-text {
            font-style: italic;
            color: #949ba4;
        }
        
        .footer {
            background: #1e1f22;
            padding: 20px 30px;
            text-align: center;
            border-top: 1px solid #3f4147;
            font-size: 12px;
            color: #949ba4;
        }
        
        pre {
            background: #1e1f22;
            padding: 12px;
            border-radius: 6px;
            overflow-x: auto;
            font-size: 13px;
            margin-top: 8px;
        }
        
        code {
            font-family: 'Courier New', monospace;
        }
        
        @media (max-width: 600px) {
            .container {
                border-radius: 0;
            }
            .messages {
                padding: 12px;
            }
            .message {
                padding: 10px;
            }
            .avatar {
                width: 32px;
                height: 32px;
                font-size: 12px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📑 Ticket Transcript</h1>
            <div class="ticket-id">{{ channel_name }}</div>
        </div>
        
        <div class="info-grid">
            <div class="info-item">
                <div class="info-label">Created By</div>
                <div class="info-value">{{ creator_name }}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Category</div>
                <div class="info-value">{{ category }}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Created At</div>
                <div class="info-value">{{ created_at }}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Closed At</div>
                <div class="info-value">{{ closed_at }}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Closed By</div>
                <div class="info-value">{{ closed_by }}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Message Count</div>
                <div class="info-value">{{ message_count }}</div>
            </div>
        </div>
        
        <div class="messages">
            {% for message in messages %}
            <div class="message {% if message.is_system %}system-message{% endif %}">
                <div class="avatar">
                    {% if message.avatar_url %}
                    <img src="{{ message.avatar_url }}" alt="{{ message.author }}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">
                    {% else %}
                    {{ message.author[:1] }}
                    {% endif %}
                </div>
                <div class="message-content">
                    <div class="message-header">
                        <span class="author-name">{{ message.author }}</span>
                        <span class="timestamp">{{ message.timestamp }}</span>
                        {% if message.is_bot %}
                        <span class="timestamp">🤖 Bot</span>
                        {% endif %}
                    </div>
                    <div class="message-text">
                        {{ message.content | safe }}
                        {% if message.attachments %}
                            <div class="attachment">
                                📎 Attachments: 
                                {% for att in message.attachments %}
                                <a href="{{ att.url }}" target="_blank">{{ att.filename }}</a>{% if not loop.last %}, {% endif %}
                                {% endfor %}
                            </div>
                        {% endif %}
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
        
        <div class="footer">
            Generated on {{ generated_at }} • Ticket closed by {{ closed_by }}
        </div>
    </div>
</body>
</html>"""
    
    template = Template(template_str)
    
    html_content = template.render(
        channel_name=html.escape(channel.name),
        creator_name=html.escape(creator_name),
        category=html.escape(category),
        created_at=channel.created_at.strftime("%Y-%m-%d %H:%M UTC"),
        closed_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        closed_by=html.escape(str(closed_by)),
        message_count=len(processed_messages),
        messages=processed_messages,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    )
    
    return html_content


# ---------------------------------------------------------------------------
# Transcript & Close Helper (Enhanced)
# ---------------------------------------------------------------------------

async def _close_ticket(channel: discord.TextChannel, closed_by: discord.Member, db):
    """Generates HTML transcript, saves to MongoDB, sends to channel and DM, deletes channel."""
    guild = channel.guild
    
    # 1. Fetch all messages
    messages = []
    try:
        async for msg in channel.history(limit=None, oldest_first=True):
            msg_data = {
                "id": msg.id,
                "author": str(msg.author),
                "author_id": msg.author.id,
                "timestamp": msg.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "content": msg.content or "",
                "attachments": [{"filename": a.filename, "url": a.url} for a in msg.attachments],
                "is_bot": msg.author.bot,
                "is_system": False,
                "avatar_url": msg.author.display_avatar.url if msg.author.avatar else None
            }
            messages.append(msg_data)
    except Exception as e:
        print(f"Error fetching messages for transcript: {e}")
    
    # 2. Generate HTML transcript
    html_content = await generate_html_transcript(channel, messages, closed_by)
    html_bytes = html_content.encode('utf-8')
    
    # 3. Create transcript document for MongoDB
    creator_name = "Unknown"
    creator_id = None
    category = "Unknown"
    if channel.topic:
        if "Ticket by " in channel.topic:
            creator_name = channel.topic.split("Ticket by ")[1].split(" |")[0]
        if "|" in channel.topic:
            category = channel.topic.split("|")[1].strip() if len(channel.topic.split("|")) > 1 else "Unknown"

    # FIX: resolve creator by stored author_id from messages instead of fragile name lookup
    creator_member = None
    for msg_data in messages:
        if not msg_data["is_bot"] and str(msg_data["author"]).lower().startswith(creator_name.lower()):
            creator_member = guild.get_member(msg_data["author_id"])
            if creator_member:
                break
    
    transcript_doc = {
        "_id": ObjectId(),
        "guild_id": guild.id,
        "guild_name": guild.name,
        "channel_id": channel.id,
        "channel_name": channel.name,
        "creator_name": creator_name,
        "category": category,
        "closed_by": str(closed_by),
        "closed_by_id": closed_by.id,
        "created_at": channel.created_at,
        "closed_at": datetime.now(timezone.utc),
        "message_count": len(messages),
        "html_content": html_content,
        "participants": list(set(m["author_id"] for m in messages if not m["is_bot"]))
    }
    
    # 4. Save to MongoDB transcripts collection
    try:
        db["transcripts"].insert_one(transcript_doc)
        print(f"✅ Transcript saved to MongoDB for {channel.name}")
    except Exception as e:
        print(f"❌ Failed to save transcript to MongoDB: {e}")
    
    # FIX: resolve dashboard URL once and reuse
    dashboard_url = os.getenv("DASHBOARD_URL", "https://your-domain.com")

    # 5. Send to Transcript Channel - ONLY embed with link, NO file
    try:
        cfg = get_guild_config(db, guild.id)
        transcript_channel_id = cfg.get("TRANSCRIPT_CHANNEL_ID")
        
        if transcript_channel_id:
            t_channel = guild.get_channel(transcript_channel_id)
            if t_channel:
                t_embed = discord.Embed(
                    title=f"📑 Ticket Closed: {channel.name}",
                    description=f"**Category:** {transcript_doc['category']}\n**Creator:** {transcript_doc['creator_name']}\n**Closed By:** {closed_by.mention}\n**Messages:** {len(messages)}",
                    color=0x5865F2,
                    timestamp=datetime.now(timezone.utc)
                )
                t_embed.add_field(
                    name="View Full Transcript", 
                    value=f"[Click Here to View Online]({dashboard_url}/transcripts/{transcript_doc['_id']})\n\n*Staff can also download the HTML file from the dashboard*", 
                    inline=False
                )
                t_embed.set_footer(text=f"Transcript ID: {transcript_doc['_id']}")
                await t_channel.send(embed=t_embed)
                print(f"✅ Transcript link sent to {t_channel.name}")
    except Exception as e:
        print(f"Error sending transcript to channel: {e}")
    
    # 6. Send to Ticket Creator DM - readable summary, NOT an HTML file
    # FIX: use guild.get_member() with resolved ID instead of deprecated get_member_named()
    if creator_member:
        try:
            dm_embed = discord.Embed(
                title=f"📑 Ticket Closed: {channel.name}",
                description=f"Your ticket in **{guild.name}** has been closed by {closed_by.mention}.",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc)
            )
            
            if messages:
                last_messages = messages[-5:]
                preview = ""
                for msg in last_messages:
                    author_name = msg.get("author", "Unknown")[:20]
                    content_preview = msg.get("content", "")[:50]
                    if content_preview:
                        preview += f"**{author_name}:** {content_preview}\n"
                
                if preview:
                    dm_embed.add_field(name="Last Messages", value=preview[:500], inline=False)
            
            dm_embed.add_field(name="Total Messages", value=str(len(messages)), inline=True)
            dm_embed.add_field(name="Category", value=transcript_doc['category'], inline=True)
            dm_embed.add_field(
                name="View Full Transcript", 
                value=f"You can view the complete conversation here:\n{dashboard_url}/transcripts/{transcript_doc['_id']}",
                inline=False
            )
            
            await creator_member.send(embed=dm_embed)
            print(f"✅ Transcript summary sent to {creator_member.name}")
        except discord.Forbidden:
            print(f"Cannot DM {creator_name} - DMs disabled")
        except Exception as e:
            print(f"Error sending DM: {e}")
    
    # 7. Delete Channel
    try:
        await channel.delete()
    except Exception as e:
        print(f"Error deleting channel: {e}")


# ---------------------------------------------------------------------------
# Modals — one per category
# ---------------------------------------------------------------------------
class BaseBuyingModal(discord.ui.Modal, title="🏠 Base Buying Ticket"):
    q1 = discord.ui.TextInput(label="What type of base are you looking for?", style=discord.TextStyle.short, required=True)
    q2 = discord.ui.TextInput(label="What is your budget?", style=discord.TextStyle.short, required=True)
    q3 = discord.ui.TextInput(label="Any specific requirements?", style=discord.TextStyle.paragraph, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets_base_buying import BASE_CFG

        await create_ticket_channel(
            interaction,
            BASE_CFG,
            "Base Buying",
            {self.q1.label: self.q1.value, self.q2.label: self.q2.value, self.q3.label: self.q3.value},
        )


class BedrockModal(discord.ui.Modal, title="🕳️ Bedrock Hole Ticket"):
    q1 = discord.ui.TextInput(label="What size hole do you need?", style=discord.TextStyle.short, required=True)
    q2 = discord.ui.TextInput(label="What is your budget?", style=discord.TextStyle.short, required=True)
    q3 = discord.ui.TextInput(label="Preferred location?", style=discord.TextStyle.paragraph, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets_bedrock import BEDROCK_CFG

        await create_ticket_channel(
            interaction,
            BEDROCK_CFG,
            "Bedrock Hole Buying",
            {self.q1.label: self.q1.value, self.q2.label: self.q2.value, self.q3.label: self.q3.value},
        )


class SpawnerModal(discord.ui.Modal, title="🔄 Spawner Trading Ticket"):
    q1 = discord.ui.TextInput(label="Are you buying or selling?", style=discord.TextStyle.short, required=True)
    q2 = discord.ui.TextInput(label="What spawner type?", style=discord.TextStyle.short, required=True)
    q3 = discord.ui.TextInput(label="Quantity and price?", style=discord.TextStyle.paragraph, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets_spawner import SPAWNER_CFG

        await create_ticket_channel(
            interaction,
            SPAWNER_CFG,
            "Spawner Trading",
            {self.q1.label: self.q1.value, self.q2.label: self.q2.value, self.q3.label: self.q3.value},
        )


class BuildingModal(discord.ui.Modal, title="🏗️ Building Ticket"):
    q1 = discord.ui.TextInput(label="What is your IGN?", style=discord.TextStyle.short, required=True)
    q2 = discord.ui.TextInput(label="What is your budget?", style=discord.TextStyle.short, required=True)
    q3 = discord.ui.TextInput(label="What base do you need?", style=discord.TextStyle.short, required=True)
    q4 = discord.ui.TextInput(label="Specific requirements?", style=discord.TextStyle.paragraph, required=False)
    q5 = discord.ui.TextInput(
        label="How soon do you need the base?",
        style=discord.TextStyle.short,
        required=True,
        placeholder="ASAP / Within a week / No rush",
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets_building import create_builder_ticket

        await create_builder_ticket(
            interaction,
            {
                self.q1.label: self.q1.value,
                self.q2.label: self.q2.value,
                self.q3.label: self.q3.value,
                self.q4.label: self.q4.value,
                self.q5.label: self.q5.value,
            },
        )


class SupportModal(discord.ui.Modal, title="❓ Support Ticket"):
    q1 = discord.ui.TextInput(label="What do you need help with?", style=discord.TextStyle.short, required=True)
    q2 = discord.ui.TextInput(label="Please provide as much detail as possible", style=discord.TextStyle.paragraph, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets_support import SUPPORT_CFG

        await create_ticket_channel(
            interaction,
            SUPPORT_CFG,
            "General Support",
            {self.q1.label: self.q1.value, self.q2.label: self.q2.value},
        )


class ScamModal(discord.ui.Modal, title="⚠️ Scam Report"):
    q1 = discord.ui.TextInput(label="Who scammed you?", style=discord.TextStyle.short, required=True)
    q2 = discord.ui.TextInput(label="What happened?", style=discord.TextStyle.paragraph, required=True)
    q3 = discord.ui.TextInput(label="Do you have proof?", style=discord.TextStyle.short, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        from cogs.tickets_support import SCAM_CFG

        await create_ticket_channel(
            interaction,
            SCAM_CFG,
            "Scam Report",
            {self.q1.label: self.q1.value, self.q2.label: self.q2.value, self.q3.label: self.q3.value},
        )


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
            await interaction.response.send_message("❌ Only the ticket creator can request a close.", ephemeral=True)
            return
        staff_role_name = get_guild_config(interaction.client.db, interaction.guild.id)["STAFF_ROLE"]
        staff_role = discord.utils.get(interaction.guild.roles, name=staff_role_name)
        mention = staff_role.mention if staff_role else f"@{staff_role_name}"
        await interaction.response.send_message(f"{mention}\n**{interaction.user.mention}** has requested to close this ticket.")

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="close_v14")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = get_guild_config(interaction.client.db, interaction.guild.id)
        staff_role = discord.utils.get(interaction.guild.roles, name=cfg["STAFF_ROLE"])
        if not staff_role or staff_role not in interaction.user.roles:
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("❌ Staff only!", ephemeral=True)
                return
        await interaction.response.send_message("🔒 Closing ticket and generating transcript...", ephemeral=True)
        await _close_ticket(interaction.channel, interaction.user, interaction.client.db)


# ---------------------------------------------------------------------------
# Panel views — buttons open modals
# ---------------------------------------------------------------------------
class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🏠 Base Buying", style=discord.ButtonStyle.primary, custom_id="tp_base_v14", row=0)
    async def btn_base(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction):
            return
        await interaction.response.send_modal(BaseBuyingModal())

    @discord.ui.button(label="🕳️ Bedrock Hole", style=discord.ButtonStyle.primary, custom_id="tp_bedrock_v14", row=0)
    async def btn_bedrock(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction):
            return
        await interaction.response.send_modal(BedrockModal())

    @discord.ui.button(label="🔄 Spawner Trade", style=discord.ButtonStyle.primary, custom_id="tp_spawner_v14", row=0)
    async def btn_spawner(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction):
            return
        await interaction.response.send_modal(SpawnerModal())

    @discord.ui.button(label="❓ Support", style=discord.ButtonStyle.secondary, custom_id="tp_support_v14", row=1)
    async def btn_support(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction):
            return
        await interaction.response.send_modal(SupportModal())

    @discord.ui.button(label="⚠️ Scam Report", style=discord.ButtonStyle.danger, custom_id="tp_scam_v14", row=1)
    async def btn_scam(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction):
            return
        await interaction.response.send_modal(ScamModal())

class BaseBuyingPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🏠 Open Base Buying Ticket", style=discord.ButtonStyle.primary, custom_id="sp_base_v14")
    async def btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction):
            return
        await interaction.response.send_modal(BaseBuyingModal())


class BedrockPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🕳️ Open Bedrock Hole Ticket", style=discord.ButtonStyle.primary, custom_id="sp_bedrock_v14")
    async def btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction):
            return
        await interaction.response.send_modal(BedrockModal())


class SpawnerPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔄 Open Spawner Trade Ticket", style=discord.ButtonStyle.primary, custom_id="sp_spawner_v14")
    async def btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction):
            return
        await interaction.response.send_modal(SpawnerModal())


class BuildingPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🏗️ Open Building Ticket", style=discord.ButtonStyle.primary, custom_id="sp_building_v14")
    async def btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction):
            return
        await interaction.response.send_modal(BuildingModal())


class SupportPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="❓ Open Support Ticket", style=discord.ButtonStyle.secondary, custom_id="sp_support_v14", row=0)
    async def btn_support(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction):
            return
        await interaction.response.send_modal(SupportModal())

    @discord.ui.button(label="⚠️ Report a Scam", style=discord.ButtonStyle.danger, custom_id="sp_scam_support_v14", row=0)
    async def btn_scam(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction):
            return
        await interaction.response.send_modal(ScamModal())


class ScamPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # FIX: was sp_scam_v14, which clashed with SupportPanelView's scam button
    @discord.ui.button(label="⚠️ Report a Scam", style=discord.ButtonStyle.danger, custom_id="sp_scam_only_v14")
    async def btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await check_existing_ticket(interaction):
            return
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
        bot.add_view(ScamPanelView())

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        msg = str(error) if isinstance(error, app_commands.CheckFailure) else f"❌ Unexpected error: {error}"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="ticketpanel", description="Post a ticket panel for a specific category")
    @app_commands.describe(category="Select which type of ticket panel to post")
    @app_commands.choices(category=[
        app_commands.Choice(name="All Categories (Full Panel)", value="all"),
        app_commands.Choice(name="🏠 Base Buying", value="basebuying"),
        app_commands.Choice(name="🕳️ Bedrock Hole", value="bedrock"),
        app_commands.Choice(name="🔄 Spawner Trade", value="spawner"),
        app_commands.Choice(name="🏗️ Building", value="building"),
        app_commands.Choice(name="❓ Support", value="support"),
        app_commands.Choice(name="⚠️ Scam Report", value="scam"),
    ])
    @admin_only()
    async def ticketpanel(self, interaction: discord.Interaction, category: app_commands.Choice[str]):
        await _clear_bot_messages(interaction.channel, self.bot.user)
        
        # Category configurations
        panels = {
            "all": {
                "title": "🎫 Support Tickets",
                "description": (
                    "### Click a button below to open a ticket!\n\n"
                    "🏠 **Base Buying** — Purchase a base\n"
                    "🕳️ **Bedrock Hole** — Buy a bedrock hole\n"
                    "🔄 **Spawner Trade** — Buy or sell spawners\n"
                    "🏗️ **Building** — Building services\n"
                    "❓ **Support** — General help\n"
                    "⚠️ **Scam Report** — Report a scam"
                ),
                "color": 0x2b2d31,
                "view": TicketPanelView()
            },
            "basebuying": {
                "title": "🏠 Base Buying Tickets",
                "description": "Click the button below to open a ticket for purchasing a base.\n\nA staff member will assist you shortly.",
                "color": 0x2ecc71,
                "view": BaseBuyingPanelView()
            },
            "bedrock": {
                "title": "🕳️ Bedrock Hole Tickets",
                "description": "Click the button below to open a ticket for purchasing a bedrock hole.\n\nA staff member will assist you shortly.",
                "color": 0x95a5a6,
                "view": BedrockPanelView()
            },
            "spawner": {
                "title": "🔄 Spawner Trading Tickets",
                "description": "Click the button below to open a ticket for buying or selling spawners.\n\nA staff member will assist you shortly.",
                "color": 0xf1c40f,
                "view": SpawnerPanelView()
            },
            "building": {
                "title": "🏗️ Building Tickets",
                "description": "Click the button below to open a ticket for building services.\n\nA builder will be assigned to your order.",
                "color": 0x9b59b6,
                "view": BuildingPanelView()
            },
            "support": {
                "title": "❓ Support Tickets",
                "description": "Click the button below to open a ticket for general help and questions.\n\nA staff member will assist you shortly.",
                "color": 0x3498db,
                "view": SupportPanelView()
            },
            "scam": {
                "title": "⚠️ Scam Report Tickets",
                "description": "Click the button below to report a scam.\n\nPlease provide proof in the ticket.",
                "color": 0xe74c3c,
                "view": ScamPanelView()
            }
        }
        
        selected = panels[category.value]
        
        embed = discord.Embed(
            title=selected["title"],
            description=selected["description"],
            color=selected["color"],
        )
        
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        
        embed.set_footer(text="Your ticket will be created in the appropriate category")
        
        await interaction.response.send_message(embed=embed, view=selected["view"])

    @app_commands.command(name="close", description="Close the current ticket")
    async def close(self, interaction: discord.Interaction):
        ch = interaction.channel
        if not is_ticket_channel(ch):
            await interaction.response.send_message("❌ This command can only be used in ticket channels.", ephemeral=True)
            return

        has_perm = interaction.user.guild_permissions.administrator
        if not has_perm:
            close_roles = resolve_role_names(self.bot.db, interaction.guild.id, [STAFF_ROLE, *SELLER_ROLES])
            has_perm = any(
                (role := discord.utils.get(interaction.guild.roles, name=rn)) and role in interaction.user.roles
                for rn in close_roles
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