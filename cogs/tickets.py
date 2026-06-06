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
    """Check if user has staff role"""
    async def predicate(interaction: discord.Interaction):
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE)
        if staff_role and staff_role in interaction.user.roles:
            return True
        await interaction.response.send_message("❌ You need the Staff role to use this command!", ephemeral=True)
        return False
    return app_commands.check(predicate)

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Request Close", style=discord.ButtonStyle.red, custom_id="request_close_v5", emoji="🔒")
    async def request_close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Request ticket closure - only ticket creator can use"""
        creator_name = interaction.channel.name.replace("ticket-", "").replace("claimed-", "")
        
        # Only ticket creator can request close
        if interaction.user.name.lower() != creator_name.lower():
            await interaction.response.send_message("❌ Only the ticket creator can request closure!", ephemeral=True)
            return
        
        # Ping staff
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE)
        if staff_role:
            embed = discord.Embed(
                title="🔒 Close Request",
                description=f"{staff_role.mention} **{interaction.user.mention}** has requested to close this ticket!",
                color=discord.Color.orange()
            )
            embed.set_footer(text="Use /close to close this ticket")
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("✅ Close requested! Staff will review shortly.", ephemeral=True)
    
    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="close_ticket_v5", emoji="⛔")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Close ticket - staff only"""
        # Check if staff
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE)
        if not staff_role or staff_role not in interaction.user.roles:
            await interaction.response.send_message("❌ Only staff can close tickets directly!", ephemeral=True)
            return
        
        await interaction.response.send_message("Closing ticket in 5 seconds...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

class CategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="General Support", description="General help & questions", emoji="❓"),
            discord.SelectOption(label="Base Buying", description="Purchase a base from someone", emoji="🏠"),
            discord.SelectOption(label="Bedrock Hole Buying", description="Buy a bedrock hole", emoji="🕳️"),
            discord.SelectOption(label="Spawner Trading", description="Buy or sell spawners", emoji="🔄"),
            discord.SelectOption(label="Building", description="Request building services", emoji="🏗️"),
            discord.SelectOption(label="Scam Report", description="Report a scam or fraud", emoji="⚠️"),
        ]
        super().__init__(placeholder="🎫 Select ticket category...", options=options, custom_id="category_select_v5")
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Check existing tickets
        for ch in interaction.guild.channels:
            if ch.name.endswith(f"-{interaction.user.name.lower()}") and (
                ch.name.startswith("ticket-") or ch.name.startswith("claimed-")
            ):
                await interaction.followup.send(f"❌ You already have a ticket: {ch.mention}", ephemeral=True)
                return
        
        category = self.values[0]
        
        # Beautiful configurations
        configs = {
            "General Support": {
                "discord_category": "❓ General Support",
                "ping_roles": [STAFF_ROLE],
                "allowed_roles": [STAFF_ROLE],
                "color": 0x3498db,
                "thumbnail": "❓",
                "questions": [
                    "**What do you need help with?**",
                    "Please provide as much detail as possible so we can assist you better."
                ]
            },
            "Base Buying": {
                "discord_category": "🏠 Base Buying",
                "ping_roles": [STAFF_ROLE, BASE_BUYING_ROLE],
                "allowed_roles": [STAFF_ROLE, BASE_BUYING_ROLE],
                "color": 0x2ecc71,
                "thumbnail": "🏠",
                "questions": [
                    "**What type of base are you looking for?**",
                    "**What is your budget?**",
                    "**Any specific requirements?** (Size, location, features)"
                ]
            },
            "Bedrock Hole Buying": {
                "discord_category": "🕳️ Bedrock Holes",
                "ping_roles": [STAFF_ROLE, BEDROCK_ROLE],
                "allowed_roles": [STAFF_ROLE, BEDROCK_ROLE],
                "color": 0x95a5a6,
                "thumbnail": "🕳️",
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
                "thumbnail": "🔄",
                "questions": [
                    "**Are you buying or selling?**",
                    "**What type of spawners?**",
                    "**How many and what price?**"
                ]
            },
            "Building": {
                "discord_category": "🏗️ Building",
                "ping_roles": [BUILDING_ROLE],  # ONLY Builder role, no staff
                "allowed_roles": [STAFF_ROLE, BUILDING_ROLE],  # Staff can still see but not pinged
                "color": 0x9b59b6,
                "thumbnail": "🏗️",
                "questions": [
                    "**What do you need built?**",
                    "**What is your budget?**",
                    "**Do you have a deadline?**"
                ]
            },
            "Scam Report": {
                "discord_category": "⚠️ Scam Reports",
                "ping_roles": [STAFF_ROLE],
                "allowed_roles": [STAFF_ROLE],
                "color": 0xe74c3c,
                "thumbnail": "⚠️",
                "questions": [
                    "**Who scammed you?** (Username and Discord ID)",
                    "**What were you trying to trade/buy?**",
                    "**Do you have proof?** (Please attach screenshots)"
                ]
            }
        }
        
        cfg = configs[category]
        
        # Get or create discord category
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
            topic=f"🎫 {category} | Created by {interaction.user} | {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
        )
        
        # Beautiful welcome embed
        embed = discord.Embed(
            title=f"{cfg['thumbnail']} {category} Ticket",
            description=f"### Welcome {interaction.user.mention}!\n\n"
                       f"Thank you for creating a ticket. Please answer the following questions "
                       f"so our team can assist you as quickly as possible.\n\n"
                       f"━━━━━━━━━━━━━━━━━━━━━━━",
            color=cfg["color"],
            timestamp=datetime.utcnow()
        )
        
        for i, q in enumerate(cfg["questions"], 1):
            embed.add_field(
                name=f"📋 Question {i}",
                value=q,
                inline=False
            )
        
        embed.add_field(
            name="\u200b",
            value="━━━━━━━━━━━━━━━━━━━━━━━",
            inline=False
        )
        
        embed.add_field(name="👤 Created By", value=interaction.user.mention, inline=True)
        embed.add_field(name="📂 Category", value=category, inline=True)
        embed.add_field(name="🕐 Created", value=f"<t:{int(datetime.utcnow().timestamp())}:R>", inline=True)
        
        embed.set_footer(text=f"Ticket ID: {channel.id} • Use /close to close this ticket")
        
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        
        # Send ticket with buttons
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
                description=f"🔔 {ping_text}\n\n"
                           f"📩 **New {category} ticket** from {interaction.user.mention}\n"
                           f"📁 Channel: {channel.mention}",
                color=cfg["color"]
            )
            await channel.send(embed=ping_embed)
        
        await interaction.followup.send(f"✅ Ticket created successfully! {channel.mention}", ephemeral=True)

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="ticketpanel", description="📋 Create the ticket panel (Admin only)")
    @app_commands.default_permissions(administrator=True)
    async def ticketpanel(self, interaction: discord.Interaction):
        """Create ticket panel"""
        async for msg in interaction.channel.history(limit=20):
            if msg.author == self.bot.user:
                try:
                    await msg.delete()
                except:
                    pass
        
        embed = discord.Embed(
            title="🎫 Support Tickets",
            description="### Need assistance? You're in the right place!\n\n"
                       "Select the appropriate category from the dropdown below "
                       "and our team will help you as soon as possible.",
            color=0x2b2d31
        )
        
        embed.add_field(
            name="📋 Available Categories",
            value="> ❓ **General Support** — Help & questions\n"
                  "> 🏠 **Base Buying** — Purchase a base\n"
                  "> 🕳️ **Bedrock Hole Buying** — Buy bedrock holes\n"
                  "> 🔄 **Spawner Trading** — Buy/sell spawners\n"
                  "> 🏗️ **Building** — Building services\n"
                  "> ⚠️ **Scam Report** — Report scams",
            inline=False
        )
        
        embed.add_field(
            name="⏱️ Response Time",
            value="> Our team typically responds within **24 hours**.\n"
                  "> Please be patient and provide all necessary information.",
            inline=False
        )
        
        embed.set_footer(text="Select a category from the dropdown below to begin ✨")
        
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        
        view = discord.ui.View(timeout=None)
        view.add_item(CategorySelect())
        
        await interaction.response.send_message(embed=embed, view=view)
    
    @app_commands.command(name="rename", description="✏️ Rename this ticket channel")
    @app_commands.describe(new_name="The new name for this ticket channel")
    @is_staff()
    async def rename_ticket(self, interaction: discord.Interaction, new_name: str):
        """Rename ticket channel"""
        if not interaction.channel.name.startswith("ticket-") and not interaction.channel.name.startswith("claimed-"):
            await interaction.response.send_message("❌ This command can only be used in ticket channels!", ephemeral=True)
            return
        
        old_name = interaction.channel.name
        
        # Keep the prefix (ticket- or claimed-)
        if interaction.channel.name.startswith("claimed-"):
            # Get claimer part
            parts = old_name.split("-", 2)
            if len(parts) >= 2:
                prefix = f"claimed-{parts[1]}-"
                new_channel_name = f"{prefix}{new_name.lower().replace(' ', '-')}"
            else:
                new_channel_name = f"claimed-{new_name.lower().replace(' ', '-')}"
        else:
            new_channel_name = f"ticket-{new_name.lower().replace(' ', '-')}"
        
        # Trim to 100 chars
        if len(new_channel_name) > 100:
            new_channel_name = new_channel_name[:100]
        
        try:
            await interaction.channel.edit(name=new_channel_name)
            embed = discord.Embed(
                description=f"✅ Channel renamed from **{old_name}** to **{new_channel_name}** by {interaction.user.mention}",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)
    
    @app_commands.command(name="add", description="➕ Add a user to this ticket")
    @app_commands.describe(member="The user to add to the ticket")
    @is_staff()
    async def add_user(self, interaction: discord.Interaction, member: discord.Member):
        """Add user to ticket"""
        if not interaction.channel.name.startswith("ticket-") and not interaction.channel.name.startswith("claimed-"):
            await interaction.response.send_message("❌ This command can only be used in ticket channels!", ephemeral=True)
            return
        
        await interaction.channel.set_permissions(member, read_messages=True, send_messages=True, read_message_history=True)
        
        embed = discord.Embed(
            description=f"✅ {member.mention} has been **added** to the ticket by {interaction.user.mention}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="remove", description="➖ Remove a user from this ticket")
    @app_commands.describe(member="The user to remove from the ticket")
    @is_staff()
    async def remove_user(self, interaction: discord.Interaction, member: discord.Member):
        """Remove user from ticket"""
        if not interaction.channel.name.startswith("ticket-") and not interaction.channel.name.startswith("claimed-"):
            await interaction.response.send_message("❌ This command can only be used in ticket channels!", ephemeral=True)
            return
        
        if member == interaction.user:
            await interaction.response.send_message("❌ You cannot remove yourself!", ephemeral=True)
            return
        
        await interaction.channel.set_permissions(member, read_messages=False, send_messages=False)
        
        embed = discord.Embed(
            description=f"✅ {member.mention} has been **removed** from the ticket by {interaction.user.mention}",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="close", description="🔒 Close this ticket")
    async def close_ticket(self, interaction: discord.Interaction):
        """Close ticket"""
        if not interaction.channel.name.startswith("ticket-") and not interaction.channel.name.startswith("claimed-"):
            await interaction.response.send_message("❌ This command can only be used in ticket channels!", ephemeral=True)
            return
        
        # Check permissions
        has_perm = False
        
        # Staff check
        all_roles = [STAFF_ROLE, BASE_BUYING_ROLE, BEDROCK_ROLE, SPAWNER_ROLE, BUILDING_ROLE]
        for role_name in all_roles:
            role = discord.utils.get(interaction.guild.roles, name=role_name)
            if role and role in interaction.user.roles:
                has_perm = True
                break
        
        # Creator check
        creator_name = interaction.channel.name.replace("ticket-", "").replace("claimed-", "")
        if interaction.user.name.lower() == creator_name.lower():
            has_perm = True
        
        if not has_perm:
            await interaction.response.send_message("❌ You don't have permission to close this ticket!", ephemeral=True)
            return
        
        # Generate transcript
        transcript = io.BytesIO()
        content = f"📝 Ticket Transcript\n"
        content += f"Channel: {interaction.channel.name}\n"
        content += f"Closed by: {interaction.user}\n"
        content += f"Date: {datetime.utcnow()}\n"
        content += "=" * 50 + "\n\n"
        
        async for msg in interaction.channel.history(limit=None, oldest_first=True):
            content += f"[{msg.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {msg.author}: {msg.content}\n"
            if msg.attachments:
                for att in msg.attachments:
                    content += f"📎 Attachment: {att.url}\n"
            content += "\n"
        
        transcript.write(content.encode())
        transcript.seek(0)
        
        # Send transcript to creator
        creator_name = interaction.channel.name.replace("ticket-", "").replace("claimed-", "")
        for member in interaction.guild.members:
            if member.name.lower() == creator_name.lower():
                try:
                    await member.send(
                        f"📝 Here's your ticket transcript from **{interaction.guild.name}**",
                        file=discord.File(transcript, filename=f"transcript-{interaction.channel.name}.txt")
                    )
                except:
                    pass
                break
        
        embed = discord.Embed(
            description="🔒 Closing ticket in **5 seconds**...",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        await asyncio.sleep(5)
        await interaction.channel.delete()

async def setup(bot):
    await bot.add_cog(Tickets(bot))