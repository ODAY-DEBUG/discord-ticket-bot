import discord
from discord.ext import commands
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

class TicketManageView(discord.ui.View):
    def __init__(self, bot, allowed_roles):
        super().__init__(timeout=None)
        self.bot = bot
        self.allowed_roles = allowed_roles
    
    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="v2_close_ticket")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        has_permission = False
        for role_name in self.allowed_roles:
            role = discord.utils.get(interaction.guild.roles, name=role_name)
            if role and role in interaction.user.roles:
                has_permission = True
                break
        
        channel_name = interaction.channel.name
        creator_name = ""
        if channel_name.startswith("ticket-"):
            creator_name = channel_name.replace("ticket-", "")
        elif channel_name.startswith("claimed-"):
            parts = channel_name.split("-")
            if len(parts) >= 2:
                creator_name = parts[-1]
        
        if interaction.user.name.lower() == creator_name.lower():
            has_permission = True
        
        if not has_permission:
            await interaction.response.send_message("You don't have permission to close this ticket!", ephemeral=True)
            return
        
        await interaction.response.send_message("Closing ticket in 5 seconds...")
        await asyncio.sleep(5)
        await interaction.channel.delete()
    
    @discord.ui.button(label="Claim Ticket", style=discord.ButtonStyle.green, custom_id="v2_claim_ticket")
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        has_permission = False
        for role_name in self.allowed_roles:
            role = discord.utils.get(interaction.guild.roles, name=role_name)
            if role and role in interaction.user.roles:
                has_permission = True
                break
        
        if not has_permission:
            role_list = ", ".join(self.allowed_roles)
            await interaction.response.send_message(f"You need one of these roles: {role_list}", ephemeral=True)
            return
        
        if interaction.channel.name.startswith("claimed-"):
            # Find who claimed it
            parts = interaction.channel.name.replace("claimed-", "").split("-")
            if parts:
                claimer = parts[0]
                await interaction.response.send_message(f"Already claimed by {claimer}!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        # Get creator from channel name
        creator_name = interaction.channel.name.replace("ticket-", "")
        
        # Get category from topic
        category = "Support"
        if interaction.channel.topic and "|" in interaction.channel.topic:
            category = interaction.channel.topic.split("|")[-1].strip()
        
        # Create new name
        staff_name = interaction.user.name.lower()
        clean_cat = category.lower().replace(" ", "-").replace("&", "and")
        new_name = f"claimed-{staff_name}-{clean_cat}-{creator_name}"
        if len(new_name) > 100:
            new_name = new_name[:100]
        
        try:
            await interaction.channel.edit(name=new_name)
            embed = discord.Embed(
                title="Ticket Claimed",
                description=f"Claimed by {interaction.user.mention}",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"Error: {e}", ephemeral=True)
    
    @discord.ui.button(label="Unclaim Ticket", style=discord.ButtonStyle.gray, custom_id="v2_unclaim_ticket")
    async def unclaim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel.name.startswith("claimed-"):
            await interaction.response.send_message("Ticket is not claimed!", ephemeral=True)
            return
        
        # Parse channel name: claimed-STAFF-category-creator
        parts = interaction.channel.name.replace("claimed-", "")
        dash_parts = parts.split("-")
        
        # Last part is creator
        creator_name = dash_parts[-1] if dash_parts else ""
        
        # First part(s) before category is staff name
        # We need to find where category starts
        claimer_name = ""
        if len(dash_parts) >= 3:
            # claimed-staff-base-buying-creator
            # staff is everything except last 2 parts
            claimer_name = "-".join(dash_parts[:-2])
        elif len(dash_parts) == 2:
            claimer_name = dash_parts[0]
        
        is_claimer = interaction.user.name.lower() == claimer_name.lower()
        
        # Check if staff
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE)
        is_staff = staff_role and staff_role in interaction.user.roles
        
        if not is_claimer and not is_staff:
            await interaction.response.send_message(f"Only {claimer_name} can unclaim!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        new_name = f"ticket-{creator_name}"
        
        try:
            await interaction.channel.edit(name=new_name)
            embed = discord.Embed(
                title="Ticket Unclaimed",
                description="Available for someone else to claim",
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"Error: {e}", ephemeral=True)

class TicketSelect(discord.ui.Select):
    def __init__(self, bot):
        self.bot = bot
        options = [
            discord.SelectOption(label="General Support", emoji="❓"),
            discord.SelectOption(label="Base Buying", emoji="🏠"),
            discord.SelectOption(label="Bedrock Hole Buying", emoji="🕳️"),
            discord.SelectOption(label="Spawner Trading", emoji="🔄"),
            discord.SelectOption(label="Building", emoji="🏗️"),
            discord.SelectOption(label="Scam Report", emoji="⚠️"),
        ]
        super().__init__(placeholder="Select ticket category...", options=options, custom_id="v2_ticket_select")
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        # Check existing tickets
        has_ticket = False
        for ch in interaction.guild.channels:
            name_lower = ch.name.lower()
            user_lower = interaction.user.name.lower()
            if f"ticket-{user_lower}" == name_lower or (name_lower.startswith("claimed-") and name_lower.endswith(f"-{user_lower}")):
                has_ticket = True
                await interaction.followup.send(f"You already have a ticket: {ch.mention}", ephemeral=True)
                return
        
        if has_ticket:
            return
        
        category_name = self.values[0]
        
        configs = {
            "General Support": {
                "category": "General Support",
                "ping": [STAFF_ROLE],
                "claim": [STAFF_ROLE],
                "color": discord.Color.blue(),
                "questions": ["What do you need help with?", "Please provide details"]
            },
            "Base Buying": {
                "category": "Base Buying",
                "ping": [STAFF_ROLE, BASE_BUYING_ROLE],
                "claim": [STAFF_ROLE, BASE_BUYING_ROLE],
                "color": discord.Color.green(),
                "questions": ["What type of base?", "Your budget?", "Requirements?"]
            },
            "Bedrock Hole Buying": {
                "category": "Bedrock Holes",
                "ping": [STAFF_ROLE, BEDROCK_ROLE],
                "claim": [STAFF_ROLE, BEDROCK_ROLE],
                "color": discord.Color.dark_gray(),
                "questions": ["What size hole?", "Your budget?", "Location?"]
            },
            "Spawner Trading": {
                "category": "Spawner Trading",
                "ping": [STAFF_ROLE, SPAWNER_ROLE],
                "claim": [STAFF_ROLE, SPAWNER_ROLE],
                "color": discord.Color.gold(),
                "questions": ["Buying or selling?", "Type and quantity?", "Price?"]
            },
            "Building": {
                "category": "Building",
                "ping": [STAFF_ROLE, BUILDING_ROLE],
                "claim": [STAFF_ROLE, BUILDING_ROLE],
                "color": discord.Color.purple(),
                "questions": ["What to build?", "Budget?", "Deadline?"]
            },
            "Scam Report": {
                "category": "Scam Reports",
                "ping": [STAFF_ROLE],
                "claim": [STAFF_ROLE],
                "color": discord.Color.red(),
                "questions": ["Who scammed you?", "What happened?", "Proof?"]
            }
        }
        
        config = configs[category_name]
        
        # Get/create category
        dc_category = discord.utils.get(interaction.guild.categories, name=config["category"])
        if not dc_category:
            dc_category = await interaction.guild.create_category(config["category"])
            await dc_category.set_permissions(interaction.guild.default_role, read_messages=False)
        
        # Permissions
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        for role_name in config["claim"]:
            role = discord.utils.get(interaction.guild.roles, name=role_name)
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        # Create channel
        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name.lower()}",
            category=dc_category,
            overwrites=overwrites,
            topic=f"Ticket by {interaction.user} | {category_name}"
        )
        
        # Welcome embed
        embed = discord.Embed(
            title=f"{category_name} Ticket",
            description=f"Welcome {interaction.user.mention}! Please answer:",
            color=config["color"],
            timestamp=datetime.utcnow()
        )
        
        for i, q in enumerate(config["questions"], 1):
            embed.add_field(name=f"Question {i}", value=q, inline=False)
        
        embed.add_field(name="Created By", value=interaction.user.mention, inline=True)
        embed.add_field(name="Category", value=category_name, inline=True)
        
        # Buttons
        view = TicketManageView(self.bot, config["claim"])
        await channel.send(embed=embed, view=view)
        
        # Pings
        ping_text = ""
        for role_name in config["ping"]:
            role = discord.utils.get(interaction.guild.roles, name=role_name)
            if role:
                ping_text += f"{role.mention} "
        
        if ping_text:
            await channel.send(f"{ping_text}New {category_name} ticket from {interaction.user.mention}!")
        
        await interaction.followup.send(f"Ticket created: {channel.mention}", ephemeral=True)

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='ticketpanel')
    @commands.has_permissions(administrator=True)
    async def ticketpanel(self, ctx):
        # Delete old messages
        async for msg in ctx.channel.history(limit=50):
            if msg.author == self.bot.user:
                await msg.delete()
        
        embed = discord.Embed(
            title="Support Tickets",
            description="Select a category below to create a ticket!",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Categories",
            value="❓ General Support\n🏠 Base Buying\n🕳️ Bedrock Hole Buying\n🔄 Spawner Trading\n🏗️ Building\n⚠️ Scam Report",
            inline=False
        )
        embed.set_footer(text="Choose from dropdown below")
        
        view = discord.ui.View(timeout=None)
        view.add_item(TicketSelect(self.bot))
        await ctx.send(embed=embed, view=view)
    
    @commands.command(name='add')
    async def add_user(self, ctx, member: discord.Member):
        if not (ctx.channel.name.startswith("ticket-") or ctx.channel.name.startswith("claimed-")):
            await ctx.send("Use in ticket channel!", delete_after=5)
            return
        
        await ctx.channel.set_permissions(member, read_messages=True, send_messages=True)
        await ctx.send(f"{member.mention} added")
    
    @commands.command(name='remove')
    async def remove_user(self, ctx, member: discord.Member):
        if not (ctx.channel.name.startswith("ticket-") or ctx.channel.name.startswith("claimed-")):
            await ctx.send("Use in ticket channel!", delete_after=5)
            return
        if member == ctx.author:
            await ctx.send("Can't remove yourself!", delete_after=5)
            return
        
        await ctx.channel.set_permissions(member, read_messages=False, send_messages=False)
        await ctx.send(f"{member.mention} removed")
    
    @commands.command(name='close')
    async def close(self, ctx):
        if not (ctx.channel.name.startswith("ticket-") or ctx.channel.name.startswith("claimed-")):
            await ctx.send("Use in ticket channel!", delete_after=5)
            return
        
        await ctx.send("Closing in 5 seconds...")
        await asyncio.sleep(5)
        await ctx.channel.delete()

async def setup(bot):
    await bot.add_cog(Tickets(bot))