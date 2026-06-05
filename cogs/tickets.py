import discord
from discord.ext import commands
import asyncio
import io
from datetime import datetime

# ===== CONFIGURATION - CHANGE THESE ROLE NAMES =====
STAFF_ROLE = "Staff"
BASE_BUYING_ROLE = "Base Seller"
BEDROCK_ROLE = "Bedrock Seller"
SPAWNER_ROLE = "Spawner Trader"
BUILDING_ROLE = "Builder"
# ====================================================

class TicketManageView(discord.ui.View):
    def __init__(self, bot, allowed_roles):
        super().__init__(timeout=None)
        self.bot = bot
        self.allowed_roles = allowed_roles
    
    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.red, custom_id="close_ticket_btn")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check permissions
        has_permission = False
        for role_name in self.allowed_roles:
            role = discord.utils.get(interaction.guild.roles, name=role_name)
            if role and role in interaction.user.roles:
                has_permission = True
                break
        
        # Check if ticket creator
        creator_name = interaction.channel.name.split("-")[-1] if "-" in interaction.channel.name else ""
        if interaction.user.name.lower() == creator_name:
            has_permission = True
        
        if not has_permission:
            await interaction.response.send_message("❌ You don't have permission to close this ticket!", ephemeral=True)
            return
        
        # Generate transcript
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
        
        # Send transcript to creator
        creator_name = interaction.channel.name.split("-")[-1] if "-" in interaction.channel.name else ""
        for member in interaction.guild.members:
            if member.name.lower() == creator_name:
                try:
                    await member.send(
                        f"📝 Transcript for {interaction.channel.name}",
                        file=discord.File(transcript, filename=f"transcript-{interaction.channel.name}.txt")
                    )
                except:
                    pass
                break
        
        await interaction.response.send_message("🔒 Closing ticket in 5 seconds...")
        await asyncio.sleep(5)
        await interaction.channel.delete()
    
    @discord.ui.button(label="👤 Claim Ticket", style=discord.ButtonStyle.green, custom_id="claim_ticket_btn")
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user has any allowed role
        has_permission = False
        for role_name in self.allowed_roles:
            role = discord.utils.get(interaction.guild.roles, name=role_name)
            if role and role in interaction.user.roles:
                has_permission = True
                break
        
        if not has_permission:
            role_list = ", ".join(self.allowed_roles)
            await interaction.response.send_message(
                f"❌ You need one of these roles to claim: **{role_list}**", 
                ephemeral=True
            )
            return
        
        # Check if already claimed
        if interaction.channel.name.startswith("claimed-"):
            # Get the current claimer
            parts = interaction.channel.name.split("-")
            if len(parts) >= 2:
                current_claimer = parts[1]
                await interaction.response.send_message(
                    f"❌ This ticket is already claimed by **{current_claimer}**!", 
                    ephemeral=True
                )
            else:
                await interaction.response.send_message("❌ This ticket is already claimed!", ephemeral=True)
            return
        
        # Get ticket creator name
        parts = interaction.channel.name.split("-", 1)
        creator_name = parts[1] if len(parts) > 1 else "unknown"
        
        # Get category from topic
        category = "Support"
        if interaction.channel.topic:
            if "|" in interaction.channel.topic:
                category = interaction.channel.topic.split("|")[-1].strip()
        
        # Create new channel name: claimed-STAFFNAME-category-creatorname
        staff_name = interaction.user.name.lower()
        # Clean category name for channel
        clean_category = category.lower().replace(" ", "-").replace("&", "and")
        new_name = f"claimed-{staff_name}-{clean_category}-{creator_name}"
        
        # Trim to 100 chars (Discord limit)
        if len(new_name) > 100:
            new_name = new_name[:100]
        
        await interaction.channel.edit(name=new_name)
        
        embed = discord.Embed(
            title="✅ Ticket Claimed",
            description=f"This ticket has been claimed by {interaction.user.mention}",
            color=discord.Color.green()
        )
        embed.add_field(name="Claimed By", value=interaction.user.mention)
        embed.set_footer(text=f"Only {interaction.user.name} can unclaim this ticket")
        await interaction.response.send_message(embed=embed)
    
    @discord.ui.button(label="🔓 Unclaim Ticket", style=discord.ButtonStyle.gray, custom_id="unclaim_ticket_btn")
    async def unclaim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if ticket is claimed
        if not interaction.channel.name.startswith("claimed-"):
            await interaction.response.send_message("❌ This ticket hasn't been claimed yet!", ephemeral=True)
            return
        
        # Get claimer from channel name
        # Format: claimed-STAFFNAME-category-creatorname
        parts = interaction.channel.name.split("-", 1)
        if len(parts) < 2:
            await interaction.response.send_message("❌ Cannot determine claimer!", ephemeral=True)
            return
        
        # Get the staff name (everything between claimed- and the next parts)
        name_parts = parts[1].split("-")
        
        # The last part is creator, second-to-last is category, everything else is staff name
        if len(name_parts) >= 3:
            creator_name = name_parts[-1]
            category_name = name_parts[-2]
            claimer_name = "-".join(name_parts[:-2])
        elif len(name_parts) == 2:
            creator_name = name_parts[-1]
            category_name = ""
            claimer_name = name_parts[0]
        else:
            creator_name = name_parts[0]
            category_name = ""
            claimer_name = ""
        
        # Only the claimer can unclaim (or staff if needed)
        is_claimer = interaction.user.name.lower() == claimer_name.lower()
        is_staff = False
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE)
        if staff_role and staff_role in interaction.user.roles:
            is_staff = True
        
        if not is_claimer and not is_staff:
            await interaction.response.send_message(
                f"❌ Only **{claimer_name}** can unclaim this ticket!", 
                ephemeral=True
            )
            return
        
        # Change name back to ticket-creatorname
        new_name = f"ticket-{creator_name}"
        await interaction.channel.edit(name=new_name)
        
        embed = discord.Embed(
            title="🔓 Ticket Unclaimed",
            description=f"This ticket has been unclaimed by {interaction.user.mention}",
            color=discord.Color.orange()
        )
        embed.add_field(name="Unclaimed By", value=interaction.user.mention)
        embed.add_field(name="Status", value="Available for claim")
        await interaction.response.send_message(embed=embed)

class TicketSelect(discord.ui.Select):
    def __init__(self, bot):
        self.bot = bot
        options = [
            discord.SelectOption(label="General Support", description="General help or questions", emoji="❓"),
            discord.SelectOption(label="Base Buying", description="Buying a base from someone", emoji="🏠"),
            discord.SelectOption(label="Bedrock Hole Buying", description="Buying a bedrock hole", emoji="🕳️"),
            discord.SelectOption(label="Spawner Selling & Buying", description="Trading spawners", emoji="🔄"),
            discord.SelectOption(label="Building", description="Request building services", emoji="🏗️"),
            discord.SelectOption(label="Scam Report", description="Report a scam or fraud", emoji="⚠️"),
        ]
        super().__init__(placeholder="Select ticket category...", options=options, custom_id="ticket_category_select")
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        # Check for existing tickets
        existing = None
        for ch in interaction.guild.channels:
            if ch.name.endswith(f"-{interaction.user.name.lower()}"):
                existing = ch
                break
        
        if existing:
            await interaction.followup.send(f"❌ You already have a ticket: {existing.mention}", ephemeral=True)
            return
        
        category_name = self.values[0]
        
        # Category configurations
        configs = {
            "General Support": {
                "discord_category": "General Support",
                "ping_roles": [STAFF_ROLE],
                "claim_roles": [STAFF_ROLE],
                "color": discord.Color.blue(),
                "questions": [
                    "What do you need help with?",
                    "Please provide as much detail as possible"
                ]
            },
            "Base Buying": {
                "discord_category": "Base Buying",
                "ping_roles": [STAFF_ROLE, BASE_BUYING_ROLE],
                "claim_roles": [STAFF_ROLE, BASE_BUYING_ROLE],
                "color": discord.Color.green(),
                "questions": [
                    "What type of base are you looking for?",
                    "What's your budget?",
                    "Any specific requirements?"
                ]
            },
            "Bedrock Hole Buying": {
                "discord_category": "Bedrock Holes",
                "ping_roles": [STAFF_ROLE, BEDROCK_ROLE],
                "claim_roles": [STAFF_ROLE, BEDROCK_ROLE],
                "color": discord.Color.dark_gray(),
                "questions": [
                    "What size bedrock hole do you need?",
                    "What's your budget?",
                    "Do you need it in a specific location?"
                ]
            },
            "Spawner Selling & Buying": {
                "discord_category": "Spawner Trading",
                "ping_roles": [STAFF_ROLE, SPAWNER_ROLE],
                "claim_roles": [STAFF_ROLE, SPAWNER_ROLE],
                "color": discord.Color.gold(),
                "questions": [
                    "Are you buying or selling?",
                    "What type of spawners?",
                    "How many and what price?"
                ]
            },
            "Building": {
                "discord_category": "Building",
                "ping_roles": [STAFF_ROLE, BUILDING_ROLE],
                "claim_roles": [STAFF_ROLE, BUILDING_ROLE],
                "color": discord.Color.purple(),
                "questions": [
                    "What do you need built?",
                    "What's your budget?",
                    "Do you have a deadline?"
                ]
            },
            "Scam Report": {
                "discord_category": "Scam Reports",
                "ping_roles": [STAFF_ROLE],
                "claim_roles": [STAFF_ROLE],
                "color": discord.Color.red(),
                "questions": [
                    "Who scammed you? (Username and Discord ID)",
                    "What were you trying to trade/buy?",
                    "Do you have proof? (Screenshots)"
                ]
            }
        }
        
        config = configs[category_name]
        
        # Get or create Discord category
        discord_category = discord.utils.get(interaction.guild.categories, name=config["discord_category"])
        if not discord_category:
            discord_category = await interaction.guild.create_category(config["discord_category"])
            await discord_category.set_permissions(interaction.guild.default_role, read_messages=False)
        
        # Set permissions
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True)
        }
        
        # Add role permissions for all claim roles
        for role_name in config["claim_roles"]:
            role = discord.utils.get(interaction.guild.roles, name=role_name)
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True)
        
        # Create ticket channel
        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name.lower()}",
            category=discord_category,
            overwrites=overwrites,
            topic=f"Ticket by {interaction.user} | {category_name}"
        )
        
        # Create welcome embed
        embed = discord.Embed(
            title=f"{category_name} Ticket",
            description=f"Welcome {interaction.user.mention}! Please answer these questions:",
            color=config["color"],
            timestamp=datetime.utcnow()
        )
        
        for i, q in enumerate(config["questions"], 1):
            embed.add_field(name=f"Question {i}", value=q, inline=False)
        
        embed.add_field(name="Created By", value=interaction.user.mention, inline=True)
        embed.add_field(name="Category", value=category_name, inline=True)
        embed.set_footer(text=f"Ticket ID: {channel.id}")
        
        # Create view with Close, Claim, and Unclaim buttons
        view = TicketManageView(self.bot, config["claim_roles"])
        await channel.send(embed=embed, view=view)
        
        # PING ALL REQUIRED ROLES
        ping_text = ""
        for role_name in config["ping_roles"]:
            role = discord.utils.get(interaction.guild.roles, name=role_name)
            if role:
                ping_text += f"{role.mention} "
        
        if ping_text:
            await channel.send(f"{ping_text}\n📩 New **{category_name}** ticket from {interaction.user.mention}!")
        
        await interaction.followup.send(f"✅ Ticket created: {channel.mention}", ephemeral=True)

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='ticketpanel')
    @commands.has_permissions(administrator=True)
    async def ticketpanel(self, ctx):
        """Create a new ticket panel"""
        # Delete old panel messages from bot in this channel
        async for message in ctx.channel.history(limit=50):
            if message.author == self.bot.user:
                await message.delete()
        
        embed = discord.Embed(
            title="🎫 Support Tickets",
            description="**Need help? Select a category below to create a ticket!**\n\n"
                       "Our team will assist you as soon as possible.",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📋 Categories",
            value="❓ **General Support** - Help & questions\n"
                  "🏠 **Base Buying** - Purchase a base\n"
                  "🕳️ **Bedrock Hole Buying** - Buy bedrock holes\n"
                  "🔄 **Spawner Trading** - Buy/sell spawners\n"
                  "🏗️ **Building** - Building services\n"
                  "⚠️ **Scam Report** - Report scams",
            inline=False
        )
        
        embed.add_field(
            name="⏱️ Response Time",
            value="Staff typically respond within 24 hours.\n"
                  "Please be patient and provide all information.",
            inline=False
        )
        
        embed.set_footer(text="Select a category from the dropdown below! ✨")
        
        view = discord.ui.View(timeout=None)
        view.add_item(TicketSelect(self.bot))
        
        await ctx.send(embed=embed, view=view)
    
    @commands.command(name='add')
    async def add_user(self, ctx, member: discord.Member):
        """Add a user to the ticket"""
        if not any(ctx.channel.name.startswith(p) for p in ["ticket-", "claimed-"]):
            await ctx.send("❌ Use this in a ticket channel!")
            return
        
        has_perm = False
        
        all_roles = [STAFF_ROLE, BASE_BUYING_ROLE, BEDROCK_ROLE, SPAWNER_ROLE, BUILDING_ROLE]
        for role_name in all_roles:
            role = discord.utils.get(ctx.guild.roles, name=role_name)
            if role and role in ctx.author.roles:
                has_perm = True
                break
        
        # Check if ticket creator
        creator_name = ctx.channel.name.split("-")[-1] if "-" in ctx.channel.name else ""
        if ctx.author.name.lower() == creator_name:
            has_perm = True
        
        if not has_perm:
            await ctx.send("❌ You don't have permission to add users!")
            return
        
        await ctx.channel.set_permissions(member, read_messages=True, send_messages=True)
        await ctx.send(f"✅ {member.mention} added by {ctx.author.mention}")
    
    @commands.command(name='remove')
    async def remove_user(self, ctx, member: discord.Member):
        """Remove a user from the ticket"""
        if not any(ctx.channel.name.startswith(p) for p in ["ticket-", "claimed-"]):
            await ctx.send("❌ Use this in a ticket channel!")
            return
        
        if member == ctx.author:
            await ctx.send("❌ You can't remove yourself!")
            return
        
        has_perm = False
        
        all_roles = [STAFF_ROLE, BASE_BUYING_ROLE, BEDROCK_ROLE, SPAWNER_ROLE, BUILDING_ROLE]
        for role_name in all_roles:
            role = discord.utils.get(ctx.guild.roles, name=role_name)
            if role and role in ctx.author.roles:
                has_perm = True
                break
        
        creator_name = ctx.channel.name.split("-")[-1] if "-" in ctx.channel.name else ""
        if ctx.author.name.lower() == creator_name:
            has_perm = True
        
        if not has_perm:
            await ctx.send("❌ You don't have permission to remove users!")
            return
        
        await ctx.channel.set_permissions(member, read_messages=False, send_messages=False)
        await ctx.send(f"✅ {member.mention} removed by {ctx.author.mention}")
    
    @commands.command(name='close')
    async def close(self, ctx):
        """Close the ticket"""
        if not any(ctx.channel.name.startswith(p) for p in ["ticket-", "claimed-"]):
            await ctx.send("❌ Use this in a ticket channel!")
            return
        
        has_perm = False
        
        all_roles = [STAFF_ROLE, BASE_BUYING_ROLE, BEDROCK_ROLE, SPAWNER_ROLE, BUILDING_ROLE]
        for role_name in all_roles:
            role = discord.utils.get(ctx.guild.roles, name=role_name)
            if role and role in ctx.author.roles:
                has_perm = True
                break
        
        creator_name = ctx.channel.name.split("-")[-1] if "-" in ctx.channel.name else ""
        if ctx.author.name.lower() == creator_name:
            has_perm = True
        
        if not has_perm:
            await ctx.send("❌ You don't have permission to close this ticket!")
            return
        
        # Generate transcript
        transcript = io.BytesIO()
        content = f"Ticket: {ctx.channel.name}\nClosed by: {ctx.author}\nDate: {datetime.utcnow()}\n\n"
        
        async for msg in ctx.channel.history(limit=None, oldest_first=True):
            content += f"[{msg.created_at}] {msg.author}: {msg.content}\n"
            if msg.attachments:
                for att in msg.attachments:
                    content += f"[Attachment: {att.url}]\n"
            content += "\n"
        
        transcript.write(content.encode())
        transcript.seek(0)
        
        # Send transcript
        creator_name = ctx.channel.name.split("-")[-1] if "-" in ctx.channel.name else ""
        for member in ctx.guild.members:
            if member.name.lower() == creator_name:
                try:
                    await member.send(f"📝 Transcript", file=discord.File(transcript, filename=f"transcript.txt"))
                except:
                    pass
                break
        
        await ctx.send("🔒 Closing ticket in 5 seconds...")
        await asyncio.sleep(5)
        await ctx.channel.delete()

async def setup(bot):
    await bot.add_cog(Tickets(bot))