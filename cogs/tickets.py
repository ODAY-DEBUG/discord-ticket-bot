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
    
    @discord.ui.button(label="Request Close", style=discord.ButtonStyle.red, custom_id="req_close_v6", emoji="🔒")
    async def request_close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        creator_name = interaction.channel.name.replace("ticket-", "").replace("claimed-", "")
        if interaction.user.name.lower() != creator_name.lower():
            await interaction.response.send_message("Only the ticket creator can request closure!", ephemeral=True)
            return
        
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE)
        if staff_role:
            embed = discord.Embed(
                title="Close Request",
                description=f"{staff_role.mention} **{interaction.user.mention}** has requested to close this ticket!",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed)
    
    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="close_v6", emoji="⛔")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE)
        if not staff_role or staff_role not in interaction.user.roles:
            await interaction.response.send_message("Only staff can close tickets!", ephemeral=True)
            return
        
        await interaction.response.send_message("Closing in 5 seconds...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

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
        super().__init__(placeholder="Select ticket category...", options=options, custom_id="cat_select_v6")
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        for ch in interaction.guild.channels:
            if ch.name.endswith(f"-{interaction.user.name.lower()}") and (ch.name.startswith("ticket-") or ch.name.startswith("claimed-")):
                await interaction.followup.send(f"You already have a ticket: {ch.mention}", ephemeral=True)
                return
        
        category = self.values[0]
        
        configs = {
            "General Support": {"cat": "General Support", "ping": [STAFF_ROLE], "allow": [STAFF_ROLE], "color": 0x3498db, "emoji": "❓"},
            "Base Buying": {"cat": "Base Buying", "ping": [STAFF_ROLE, BASE_BUYING_ROLE], "allow": [STAFF_ROLE, BASE_BUYING_ROLE], "color": 0x2ecc71, "emoji": "🏠"},
            "Bedrock Hole Buying": {"cat": "Bedrock Holes", "ping": [STAFF_ROLE, BEDROCK_ROLE], "allow": [STAFF_ROLE, BEDROCK_ROLE], "color": 0x95a5a6, "emoji": "🕳️"},
            "Spawner Trading": {"cat": "Spawner Trading", "ping": [STAFF_ROLE, SPAWNER_ROLE], "allow": [STAFF_ROLE, SPAWNER_ROLE], "color": 0xf1c40f, "emoji": "🔄"},
            "Building": {"cat": "Building", "ping": [BUILDING_ROLE], "allow": [STAFF_ROLE, BUILDING_ROLE], "color": 0x9b59b6, "emoji": "🏗️"},
            "Scam Report": {"cat": "Scam Reports", "ping": [STAFF_ROLE], "allow": [STAFF_ROLE], "color": 0xe74c3c, "emoji": "⚠️"},
        }
        
        cfg = configs[category]
        
        dc_cat = discord.utils.get(interaction.guild.categories, name=cfg["cat"])
        if not dc_cat:
            dc_cat = await interaction.guild.create_category(cfg["cat"])
            await dc_cat.set_permissions(interaction.guild.default_role, read_messages=False)
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        for rn in cfg["allow"]:
            r = discord.utils.get(interaction.guild.roles, name=rn)
            if r:
                overwrites[r] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name.lower()}",
            category=dc_cat,
            overwrites=overwrites,
            topic=f"Ticket by {interaction.user} | {category}"
        )
        
        embed = discord.Embed(
            title=f"{cfg['emoji']} {category} Ticket",
            description=f"Welcome {interaction.user.mention}!",
            color=cfg["color"]
        )
        embed.add_field(name="Created By", value=interaction.user.mention)
        embed.set_footer(text=f"Ticket ID: {channel.id}")
        
        view = TicketView()
        await channel.send(embed=embed, view=view)
        
        pings = ""
        for rn in cfg["ping"]:
            r = discord.utils.get(interaction.guild.roles, name=rn)
            if r:
                pings += f"{r.mention} "
        if pings:
            await channel.send(f"{pings}New {category} ticket!")
        
        await interaction.followup.send(f"Ticket created: {channel.mention}", ephemeral=True)

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="rename", description="Rename this ticket channel (Staff only)")
    @app_commands.describe(new_name="New name for the channel")
    @is_staff()
    async def rename(self, interaction: discord.Interaction, new_name: str):
        if not (interaction.channel.name.startswith("ticket-") or interaction.channel.name.startswith("claimed-")):
            await interaction.response.send_message("Use this in a ticket channel!", ephemeral=True)
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
            await interaction.response.send_message(f"Renamed to {new_channel_name}")
        except Exception as e:
            await interaction.response.send_message(f"Error: {e}", ephemeral=True)
    
    @app_commands.command(name="add", description="Add a user to this ticket")
    @app_commands.describe(member="User to add")
    @is_staff()
    async def add(self, interaction: discord.Interaction, member: discord.Member):
        if not (interaction.channel.name.startswith("ticket-") or interaction.channel.name.startswith("claimed-")):
            await interaction.response.send_message("Use this in a ticket channel!", ephemeral=True)
            return
        await interaction.channel.set_permissions(member, read_messages=True, send_messages=True)
        await interaction.response.send_message(f"{member.mention} added by {interaction.user.mention}")
    
    @app_commands.command(name="remove", description="Remove a user from this ticket")
    @app_commands.describe(member="User to remove")
    @is_staff()
    async def remove(self, interaction: discord.Interaction, member: discord.Member):
        if not (interaction.channel.name.startswith("ticket-") or interaction.channel.name.startswith("claimed-")):
            await interaction.response.send_message("Use this in a ticket channel!", ephemeral=True)
            return
        if member == interaction.user:
            await interaction.response.send_message("Cannot remove yourself!", ephemeral=True)
            return
        await interaction.channel.set_permissions(member, read_messages=False, send_messages=False)
        await interaction.response.send_message(f"{member.mention} removed by {interaction.user.mention}")
    
    @app_commands.command(name="close", description="Close this ticket")
    async def close(self, interaction: discord.Interaction):
        if not (interaction.channel.name.startswith("ticket-") or interaction.channel.name.startswith("claimed-")):
            await interaction.response.send_message("Use this in a ticket channel!", ephemeral=True)
            return
        
        has_perm = False
        for rn in [STAFF_ROLE, BASE_BUYING_ROLE, BEDROCK_ROLE, SPAWNER_ROLE, BUILDING_ROLE]:
            r = discord.utils.get(interaction.guild.roles, name=rn)
            if r and r in interaction.user.roles:
                has_perm = True
                break
        
        creator_name = interaction.channel.name.replace("ticket-", "").replace("claimed-", "")
        if interaction.user.name.lower() == creator_name.lower():
            has_perm = True
        
        if not has_perm:
            await interaction.response.send_message("No permission!", ephemeral=True)
            return
        
        await interaction.response.send_message("Closing in 5 seconds...")
        await asyncio.sleep(5)
        await interaction.channel.delete()
    
    @app_commands.command(name="ticketpanel", description="Create the ticket panel (Admin only)")
    @app_commands.default_permissions(administrator=True)
    async def ticketpanel(self, interaction: discord.Interaction):
        async for msg in interaction.channel.history(limit=20):
            if msg.author == self.bot.user:
                try:
                    await msg.delete()
                except:
                    pass
        
        embed = discord.Embed(
            title="Support Tickets",
            description="Select a category below to create a ticket!",
            color=0x2b2d31
        )
        embed.add_field(name="Categories", value="❓ Support\n🏠 Base Buying\n🕳️ Bedrock\n🔄 Spawners\n🏗️ Building\n⚠️ Scam Report")
        
        view = discord.ui.View(timeout=None)
        view.add_item(CategorySelect())
        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Tickets(bot))