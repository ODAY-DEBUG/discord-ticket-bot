import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import io
from datetime import datetime

# ===== CONFIGURATION =====
STAFF_ROLE = "Staff"
BASE_BUYING_ROLE = "Base Seller"
BEDROCK_ROLE = "Bedrock Seller"
SPAWNER_ROLE = "Spawner Trader"
BUILDING_ROLE = "Builder"
# =========================

def is_staff():
    async def predicate(interaction: discord.Interaction):
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE)
        if staff_role and staff_role in interaction.user.roles:
            return True
        await interaction.response.send_message("❌ You need the Staff role!", ephemeral=True)
        return False
    return app_commands.check(predicate)

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Request Close", style=discord.ButtonStyle.red, custom_id="req_close_v7", emoji="🔒")
    async def request_close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Get the creator from channel topic
        creator_name = ""
        if interaction.channel.topic and "by " in interaction.channel.topic:
            # Topic format: "Ticket by username | Category"
            topic_part = interaction.channel.topic.split("by ")[1]
            creator_name = topic_part.split(" |")[0].strip().lower()
        else:
            # Fallback to channel name
            creator_name = interaction.channel.name.replace("ticket-", "").replace("claimed-", "").lower()
        
        # Check if user is the creator
        if interaction.user.name.lower() != creator_name:
            await interaction.response.send_message(
                f"❌ Only the ticket creator ({creator_name}) can request closure!", 
                ephemeral=True
            )
            return
        
        # Ping staff
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE)
        if staff_role:
            embed = discord.Embed(
                title="🔒 Close Requested",
                description=f"{staff_role.mention}\n\n**{interaction.user.mention}** has requested to close this ticket!",
                color=discord.Color.orange()
            )
            embed.set_footer(text="Use /close to close this ticket")
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("✅ Close requested! A staff member will review shortly.", ephemeral=True)
    
    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="close_v7", emoji="⛔")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE)
        if not staff_role or staff_role not in interaction.user.roles:
            await interaction.response.send_message("❌ Only staff can close tickets directly!", ephemeral=True)
            return
        
        await interaction.response.send_message("🔒 Closing in 5 seconds...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

class CategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="🏠 Base Buying", description="Purchase a base from someone", emoji="🏠"),
            discord.SelectOption(label="🕳️ Bedrock Hole Buying", description="Buy a bedrock hole", emoji="🕳️"),
            discord.SelectOption(label="🔄 Spawner Trading", description="Buy or sell spawners", emoji="🔄"),
            discord.SelectOption(label="🏗️ Building", description="Request building services", emoji="🏗️"),
            discord.SelectOption(label="❓ General Support", description="General help & questions", emoji="❓"),
            discord.SelectOption(label="⚠️ Scam Report", description="Report a scam or fraud", emoji="⚠️"),
        ]
        super().__init__(placeholder="🎫 Select ticket category...", options=options, custom_id="cat_select_v7")
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Check existing tickets
        for ch in interaction.guild.channels:
            if ch.name.endswith(f"-{interaction.user.name.lower()}") and (
                ch.name.startswith("ticket-") or ch.name.startswith("claimed-")
            ):
                await interaction.followup.send(f"❌ You already have a ticket: {ch.mention}", ephemeral=True)
                return
        
        # Remove emoji from category name
        category = self.values[0].split(" ", 1)[1] if " " in self.values[0] else self.values[0]
        
        configs = {
            "Base Buying": {
                "discord_category": "🏠 Base Buying",
                "ping_roles": [STAFF_ROLE, BASE_BUYING_ROLE],
                "allowed_roles": [STAFF_ROLE, BASE_BUYING_ROLE],
                "color": 0x2ecc71,
                "emoji": "🏠",
                "questions": [
                    "**What type of base are you looking for?**",
                    "**What is your budget?**",
                    "**Any specific requirements?**"
                ]
            },
            "Bedrock Hole Buying": {
                "discord_category": "🕳️ Bedrock Holes",
                "ping_roles": [STAFF_ROLE, BEDROCK_ROLE],
                "allowed_roles": [STAFF_ROLE, BEDROCK_ROLE],
                "color": 0x95a5a6,
                "emoji": "🕳️",
                "questions": [
                    "**What size bedrock hole do you need?**",
                    "**What is your budget?**",
                    "**Do you need it in a specific location?**"
                ]
            },
            "Spawner Trading": {
                "discord_category": "🔄 Spawner Trading",
                "ping_roles": [STAFF_ROLE, SPAWNER_ROLE],
                "allowed_roles": [STAFF_ROLE, SPAWNER_ROLE],
                "color": 0xf1c40f,
                "emoji": "🔄",
                "questions": [
                    "**Are you buying or selling?**",
                    "**What type of spawners?**",
                    "**How many and what price?**"
                ]
            },
            "Building": {
                "discord_category": "🏗️ Building",
                "ping_roles": [BUILDING_ROLE],
                "allowed_roles": [STAFF_ROLE, BUILDING_ROLE],
                "color": 0x9b59b6,
                "emoji": "🏗️",
                "questions": [
                    "**What do you need built?**",
                    "**What is your budget?**",
                    "**Do you have a deadline?**"
                ]
            },
            "General Support": {
                "discord_category": "❓ General Support",
                "ping_roles": [STAFF_ROLE],
                "allowed_roles": [STAFF_ROLE],
                "color": 0x3498db,
                "emoji": "❓",
                "questions": [
                    "**What do you need help with?**",
                    "**Please provide as much detail as possible**"
                ]
            },
            "Scam Report": {
                "discord_category": "⚠️ Scam Reports",
                "ping_roles": [STAFF_ROLE],
                "allowed_roles": [STAFF_ROLE],
                "color": 0xe74c3c,
                "emoji": "⚠️",
                "questions": [
                    "**Who scammed you?** (Username and Discord ID)",
                    "**What were you trying to trade/buy?**",
                    "**Do you have proof?** (Please attach screenshots)"
                ]
            }
        }
        
        cfg = configs[category]
        
        # Get or create Discord category
        dc_cat = discord.utils.get(interaction.guild.categories, name=cfg["discord_category"])
        if not dc_cat:
            dc_cat = await interaction.guild.create_category(cfg["discord_category"])
            await dc_cat.set_permissions(interaction.guild.default_role, read_messages=False)
        
        # Permissions
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True, attach_files=True)
        }
        
        for role_name in cfg["allowed_roles"]:
            role = discord.utils.get(interaction.guild.roles, name=role_name)
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True, attach_files=True)
        
        # Create channel
        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name.lower()}",
            category=dc_cat,
            overwrites=overwrites,
            topic=f"🎫 {category} | Created by {interaction.user.name} | {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
        )
        
        # Beautiful embed
        embed = discord.Embed(
            title=f"{cfg['emoji']} {category} Ticket",
            description=f"### Welcome {interaction.user.mention}!\n\n"
                       f"Thank you for creating a ticket. Please answer the following questions "
                       f"so our team can assist you quickly.\n\n"
                       f"━━━━━━━━━━━━━━━━━━━━━━━",
            color=cfg["color"],
            timestamp=datetime.utcnow()
        )
        
        for i, q in enumerate(cfg["questions"], 1):
            embed.add_field(name=f"📋 Question {i}", value=q, inline=False)
        
        embed.add_field(name="\u200b", value="━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        embed.add_field(name="👤 Created By", value=interaction.user.mention, inline=True)
        embed.add_field(name="📂 Category", value=category, inline=True)
        embed.add_field(name="🕐 Created", value=f"<t:{int(datetime.utcnow().timestamp())}:R>", inline=True)
        embed.set_footer(text=f"Ticket ID: {channel.id}")
        
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        
        # Send with buttons
        view = TicketView()
        await channel.send(embed=embed, view=view)
        
        # Ping roles
        ping_text = ""
        for role_name in cfg["ping_roles"]:
            role = discord.utils.get(interaction.guild.roles, name=role_name)
            if role:
                ping_text += f"{role.mention} "
        
        if ping_text:
            ping_embed = discord.Embed(
                description=f"🔔 {ping_text}\n\n📩 **New {category} ticket** from {interaction.user.mention}\n📁 Channel: {channel.mention}",
                color=cfg["color"]
            )
            await channel.send(embed=ping_embed)
        
        # Send confirmation that resets the dropdown
        await interaction.followup.send(
            f"✅ Ticket created: {channel.mention}\n\n"
            f"*The dropdown has been reset - you can create another ticket if needed.*",
            ephemeral=True
        )

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="rename", description="✏️ Rename this ticket channel (Staff only)")
    @app_commands.describe(new_name="New name for the channel")
    @is_staff()
    async def rename(self, interaction: discord.Interaction, new_name: str):
        if not (interaction.channel.name.startswith("ticket-") or interaction.channel.name.startswith("claimed-")):
            await interaction.response.send_message("❌ Use this in a ticket channel!", ephemeral=True)
            return
        
        clean_name = new_name.lower().replace(" ", "-")[:50]
        old_name = interaction.channel.name
        
        if old_name.startswith("claimed-"):
            parts = old_name.split("-", 2)
            prefix = f"claimed-{parts[1]}-" if len(parts) >= 2 else "claimed-"
            new_channel_name = f"{prefix}{clean_name}"
        else:
            new_channel_name = f"ticket-{clean_name}"
        
        try:
            await interaction.channel.edit(name=new_channel_name)
            await interaction.response.send_message(f"✅ Renamed to **{new_channel_name}**")
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
    
    @app_commands.command(name="add", description="➕ Add a user to this ticket")
    @app_commands.describe(member="User to add")
    @is_staff()
    async def add(self, interaction: discord.Interaction, member: discord.Member):
        if not (interaction.channel.name.startswith("ticket-") or interaction.channel.name.startswith("claimed-")):
            await interaction.response.send_message("❌ Use this in a ticket channel!", ephemeral=True)
            return
        await interaction.channel.set_permissions(member, read_messages=True, send_messages=True)
        await interaction.response.send_message(f"✅ {member.mention} added by {interaction.user.mention}")
    
    @app_commands.command(name="remove", description="➖ Remove a user from this ticket")
    @app_commands.describe(member="User to remove")
    @is_staff()
    async def remove(self, interaction: discord.Interaction, member: discord.Member):
        if not (interaction.channel.name.startswith("ticket-") or interaction.channel.name.startswith("claimed-")):
            await interaction.response.send_message("❌ Use this in a ticket channel!", ephemeral=True)
            return
        if member == interaction.user:
            await interaction.response.send_message("❌ Cannot remove yourself!", ephemeral=True)
            return
        await interaction.channel.set_permissions(member, read_messages=False, send_messages=False)
        await interaction.response.send_message(f"✅ {member.mention} removed by {interaction.user.mention}")
    
    @app_commands.command(name="close", description="🔒 Close this ticket")
    async def close(self, interaction: discord.Interaction):
        if not (interaction.channel.name.startswith("ticket-") or interaction.channel.name.startswith("claimed-")):
            await interaction.response.send_message("❌ Use this in a ticket channel!", ephemeral=True)
            return
        
        has_perm = False
        all_roles = [STAFF_ROLE, BASE_BUYING_ROLE, BEDROCK_ROLE, SPAWNER_ROLE, BUILDING_ROLE]
        for rn in all_roles:
            r = discord.utils.get(interaction.guild.roles, name=rn)
            if r and r in interaction.user.roles:
                has_perm = True
                break
        
        creator_name = interaction.channel.name.replace("ticket-", "").replace("claimed-", "")
        if interaction.user.name.lower() == creator_name.lower():
            has_perm = True
        
        if not has_perm:
            await interaction.response.send_message("❌ No permission!", ephemeral=True)
            return
        
        # Transcript
        transcript = io.BytesIO()
        content = f"Ticket: {interaction.channel.name}\n"
        content += f"Closed by: {interaction.user}\n"
        content += f"Date: {datetime.utcnow()}\n"
        content += "=" * 50 + "\n\n"
        
        async for msg in interaction.channel.history(limit=None, oldest_first=True):
            content += f"[{msg.created_at}] {msg.author}: {msg.content}\n"
            if msg.attachments:
                for att in msg.attachments:
                    content += f"[Attachment: {att.url}]\n"
            content += "\n"
        
        transcript.write(content.encode())
        transcript.seek(0)
        
        creator_name = interaction.channel.name.replace("ticket-", "").replace("claimed-", "")
        for member in interaction.guild.members:
            if member.name.lower() == creator_name.lower():
                try:
                    await member.send(f"📝 Transcript from {interaction.guild.name}", file=discord.File(transcript, filename="transcript.txt"))
                except:
                    pass
                break
        
        await interaction.response.send_message("🔒 Closing in 5 seconds...")
        await asyncio.sleep(5)
        await interaction.channel.delete()
    
    @app_commands.command(name="ticketpanel", description="📋 Create the ticket panel (Admin only)")
    @app_commands.default_permissions(administrator=True)
    async def ticketpanel(self, interaction: discord.Interaction):
        async for msg in interaction.channel.history(limit=20):
            if msg.author == self.bot.user:
                try:
                    await msg.delete()
                except:
                    pass
        
        embed = discord.Embed(
            title="🎫 Support Tickets",
            description="### Need assistance? Select a category below!\n\n"
                       "Our team will assist you as soon as possible.",
            color=0x2b2d31
        )
        
        embed.add_field(
            name="📋 Categories",
            value="🏠 **Base Buying** — Purchase a base\n"
                  "🕳️ **Bedrock Hole Buying** — Buy bedrock holes\n"
                  "🔄 **Spawner Trading** — Buy/sell spawners\n"
                  "🏗️ **Building** — Building services\n"
                  "❓ **General Support** — Help & questions\n"
                  "⚠️ **Scam Report** — Report scams",
            inline=False
        )
        
        embed.set_footer(text="Select a category from the dropdown below ✨")
        
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        
        view = discord.ui.View(timeout=None)
        view.add_item(CategorySelect())
        
        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Tickets(bot))