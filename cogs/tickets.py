import discord
from discord.ext import commands
import asyncio
from datetime import datetime

# ===== ROLES =====
STAFF_ROLE = "Staff"
BASE_BUYING_ROLE = "Base Seller"
BEDROCK_ROLE = "Bedrock Seller"
SPAWNER_ROLE = "Spawner Trader"
BUILDING_ROLE = "Builder"
# =================

class TicketView(discord.ui.View):
    def __init__(self, allowed_roles):
        super().__init__(timeout=None)
        self.allowed_roles = allowed_roles
    
    @discord.ui.button(label="Close", style=discord.ButtonStyle.red, custom_id="btn_close_new")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Closing in 5 seconds...")
        await asyncio.sleep(5)
        await interaction.channel.delete()
    
    @discord.ui.button(label="Claim", style=discord.ButtonStyle.green, custom_id="btn_claim_new")
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check role permission
        has_role = False
        for role_name in self.allowed_roles:
            role = discord.utils.get(interaction.guild.roles, name=role_name)
            if role and role in interaction.user.roles:
                has_role = True
                break
        
        if not has_role:
            await interaction.response.send_message("No permission!", ephemeral=True)
            return
        
        # Check if already claimed
        if interaction.channel.name.startswith("claimed-"):
            await interaction.response.send_message("Already claimed!", ephemeral=True)
            return
        
        # Change name
        new_name = f"claimed-{interaction.user.name.lower()}"
        try:
            await interaction.channel.edit(name=new_name)
            await interaction.response.send_message(f"Claimed by {interaction.user.mention}")
        except Exception as e:
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)
    
    @discord.ui.button(label="Unclaim", style=discord.ButtonStyle.gray, custom_id="btn_unclaim_new")
    async def unclaim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel.name.startswith("claimed-"):
            await interaction.response.send_message("Not claimed!", ephemeral=True)
            return
        
        # Get original name
        claimed_name = interaction.channel.name.replace("claimed-", "")
        
        # Check if this user claimed it
        is_claimer = claimed_name.startswith(interaction.user.name.lower())
        
        # Check if staff
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE)
        is_staff = staff_role and staff_role in interaction.user.roles
        
        if not is_claimer and not is_staff:
            await interaction.response.send_message("Only claimer or staff can unclaim!", ephemeral=True)
            return
        
        # Get creator from topic
        creator_name = "user"
        if interaction.channel.topic and "by " in interaction.channel.topic:
            creator_name = interaction.channel.topic.split("by ")[1].split(" |")[0].lower()
        
        new_name = f"ticket-{creator_name}"
        try:
            await interaction.channel.edit(name=new_name)
            await interaction.response.send_message("Ticket unclaimed!")
        except Exception as e:
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)

class CategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="General Support", emoji="❓"),
            discord.SelectOption(label="Base Buying", emoji="🏠"),
            discord.SelectOption(label="Bedrock Hole Buying", emoji="🕳️"),
            discord.SelectOption(label="Spawner Trading", emoji="🔄"),
            discord.SelectOption(label="Building", emoji="🏗️"),
            discord.SelectOption(label="Scam Report", emoji="⚠️"),
        ]
        super().__init__(placeholder="Select category...", options=options, custom_id="select_new")
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        # Check existing
        for ch in interaction.guild.channels:
            if ch.name.endswith(interaction.user.name.lower()) and (ch.name.startswith("ticket-") or ch.name.startswith("claimed-")):
                await interaction.followup.send(f"Already have ticket: {ch.mention}", ephemeral=True)
                return
        
        category = self.values[0]
        
        # Simple config
        configs = {
            "General Support": {"cat": "General Support", "ping": [STAFF_ROLE], "claim": [STAFF_ROLE], "color": discord.Color.blue()},
            "Base Buying": {"cat": "Base Buying", "ping": [STAFF_ROLE, BASE_BUYING_ROLE], "claim": [STAFF_ROLE, BASE_BUYING_ROLE], "color": discord.Color.green()},
            "Bedrock Hole Buying": {"cat": "Bedrock Holes", "ping": [STAFF_ROLE, BEDROCK_ROLE], "claim": [STAFF_ROLE, BEDROCK_ROLE], "color": discord.Color.dark_gray()},
            "Spawner Trading": {"cat": "Spawner Trading", "ping": [STAFF_ROLE, SPAWNER_ROLE], "claim": [STAFF_ROLE, SPAWNER_ROLE], "color": discord.Color.gold()},
            "Building": {"cat": "Building", "ping": [STAFF_ROLE, BUILDING_ROLE], "claim": [STAFF_ROLE, BUILDING_ROLE], "color": discord.Color.purple()},
            "Scam Report": {"cat": "Scam Reports", "ping": [STAFF_ROLE], "claim": [STAFF_ROLE], "color": discord.Color.red()},
        }
        
        cfg = configs[category]
        
        # Category
        dc_cat = discord.utils.get(interaction.guild.categories, name=cfg["cat"])
        if not dc_cat:
            dc_cat = await interaction.guild.create_category(cfg["cat"])
            await dc_cat.set_permissions(interaction.guild.default_role, read_messages=False)
        
        # Perms
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        for rn in cfg["claim"]:
            r = discord.utils.get(interaction.guild.roles, name=rn)
            if r:
                overwrites[r] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        # Channel
        ch = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name.lower()}",
            category=dc_cat,
            overwrites=overwrites,
            topic=f"Ticket by {interaction.user} | {category}"
        )
        
        embed = discord.Embed(
            title=f"{category} Ticket",
            description=f"Welcome {interaction.user.mention}!",
            color=cfg["color"]
        )
        
        view = TicketView(cfg["claim"])
        await ch.send(embed=embed, view=view)
        
        # Pings
        pings = ""
        for rn in cfg["ping"]:
            r = discord.utils.get(interaction.guild.roles, name=rn)
            if r:
                pings += f"{r.mention} "
        if pings:
            await ch.send(f"{pings}New ticket!")
        
        await interaction.followup.send(f"Created: {ch.mention}", ephemeral=True)

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='ticketpanel')
    @commands.has_permissions(administrator=True)
    async def ticketpanel(self, ctx):
        await ctx.channel.purge(limit=10, check=lambda m: m.author == self.bot.user)
        
        embed = discord.Embed(title="Support Tickets", description="Select a category:", color=discord.Color.blue())
        embed.add_field(name="Categories", value="❓ Support\n🏠 Base Buying\n🕳️ Bedrock\n🔄 Spawners\n🏗️ Building\n⚠️ Scam Report")
        
        view = discord.ui.View(timeout=None)
        view.add_item(CategorySelect())
        await ctx.send(embed=embed, view=view)
    
    @commands.command(name='add')
    async def add_user(self, ctx, member: discord.Member):
        await ctx.channel.set_permissions(member, read_messages=True, send_messages=True)
        await ctx.send(f"Added {member.mention}")
    
    @commands.command(name='remove')
    async def remove_user(self, ctx, member: discord.Member):
        if member != ctx.author:
            await ctx.channel.set_permissions(member, read_messages=False, send_messages=False)
            await ctx.send(f"Removed {member.mention}")
    
    @commands.command(name='close')
    async def close(self, ctx):
        await ctx.send("Closing...")
        await asyncio.sleep(5)
        await ctx.channel.delete()

async def setup(bot):
    await bot.add_cog(Tickets(bot))