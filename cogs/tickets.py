import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import io
from datetime import datetime

STAFF_ROLE = "Staff"
BASE_BUYING_ROLE = "Base Seller"
BEDROCK_ROLE = "Bedrock Seller"
SPAWNER_ROLE = "Spawner Trader"
BUILDING_ROLE = "Builder"

def is_staff():
    async def predicate(interaction: discord.Interaction):
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE)
        if staff_role and staff_role in interaction.user.roles:
            return True
        await interaction.response.send_message("❌ Staff only!", ephemeral=True)
        return False
    return app_commands.check(predicate)

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Request Close", style=discord.ButtonStyle.red, custom_id="req_close_v12")
    async def request_close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        creator_name = ""
        if interaction.channel.topic and "by " in interaction.channel.topic:
            creator_name = interaction.channel.topic.split("by ")[1].split(" |")[0].strip().lower()
        else:
            creator_name = interaction.channel.name.replace("ticket-", "").replace("claimed-", "").lower()
        
        if interaction.user.name.lower() != creator_name:
            await interaction.response.send_message("❌ Only ticket creator can request close!", ephemeral=True)
            return
        
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE)
        if staff_role:
            await interaction.response.send_message(f"🔒 {staff_role.mention}\n**{interaction.user.mention}** requested to close this ticket!")
        else:
            await interaction.response.send_message("✅ Close requested!", ephemeral=True)
    
    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="close_v12")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE)
        if not staff_role or staff_role not in interaction.user.roles:
            await interaction.response.send_message("❌ Staff only!", ephemeral=True)
            return
        
        await interaction.response.send_message("🔒 Closing in 5 seconds...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

class CategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="🏠 Base Buying", description="Purchase a base", emoji="🏠"),
            discord.SelectOption(label="🕳️ Bedrock Hole", description="Buy a bedrock hole", emoji="🕳️"),
            discord.SelectOption(label="🔄 Spawner Trade", description="Buy/sell spawners", emoji="🔄"),
            discord.SelectOption(label="🏗️ Building", description="Building services", emoji="🏗️"),
            discord.SelectOption(label="❓ Support", description="General help", emoji="❓"),
            discord.SelectOption(label="⚠️ Scam Report", description="Report a scam", emoji="⚠️"),
        ]
        super().__init__(placeholder="🎫 Select ticket category...", options=options, custom_id="cat_select_v12")
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        for ch in interaction.guild.channels:
            if ch.name.endswith(f"-{interaction.user.name.lower()}") and (
                ch.name.startswith("ticket-") or ch.name.startswith("claimed-")
            ):
                await interaction.followup.send(f"❌ You already have a ticket: {ch.mention}", ephemeral=True)
                return
        
        category_map = {
            "🏠 Base Buying": "Base Buying",
            "🕳️ Bedrock Hole": "Bedrock Hole Buying",
            "🔄 Spawner Trade": "Spawner Trading",
            "🏗️ Building": "Building",
            "❓ Support": "General Support",
            "⚠️ Scam Report": "Scam Report",
        }
        
        category = category_map[self.values[0]]
        
        configs = {
            "Base Buying": {
                "cat": "🏠 Base Buying", "ping": [STAFF_ROLE, BASE_BUYING_ROLE], "allow": [STAFF_ROLE, BASE_BUYING_ROLE],
                "color": 0x2ecc71, "emoji": "🏠",
                "q": ["**What type of base?**", "**Budget?**", "**Requirements?**"]
            },
            "Bedrock Hole Buying": {
                "cat": "🕳️ Bedrock Holes", "ping": [STAFF_ROLE, BEDROCK_ROLE], "allow": [STAFF_ROLE, BEDROCK_ROLE],
                "color": 0x95a5a6, "emoji": "🕳️",
                "q": ["**What size hole?**", "**Budget?**", "**Location?**"]
            },
            "Spawner Trading": {
                "cat": "🔄 Spawner Trading", "ping": [STAFF_ROLE, SPAWNER_ROLE], "allow": [STAFF_ROLE, SPAWNER_ROLE],
                "color": 0xf1c40f, "emoji": "🔄",
                "q": ["**Buying or selling?**", "**Type?**", "**Quantity/Price?**"]
            },
            "Building": {
                "cat": "🏗️ Building", "ping": [BUILDING_ROLE], "allow": [STAFF_ROLE, BUILDING_ROLE],
                "color": 0x9b59b6, "emoji": "🏗️",
                "q": ["**What to build?**", "**Budget?**", "**Deadline?**"]
            },
            "General Support": {
                "cat": "❓ General Support", "ping": [STAFF_ROLE], "allow": [STAFF_ROLE],
                "color": 0x3498db, "emoji": "❓",
                "q": ["**What do you need help with?**", "**Provide details**"]
            },
            "Scam Report": {
                "cat": "⚠️ Scam Reports", "ping": [STAFF_ROLE], "allow": [STAFF_ROLE],
                "color": 0xe74c3c, "emoji": "⚠️",
                "q": ["**Who scammed you?**", "**What happened?**", "**Proof?**"]
            }
        }
        
        cfg = configs[category]
        
        dc_cat = discord.utils.get(interaction.guild.categories, name=cfg["cat"])
        if not dc_cat:
            dc_cat = await interaction.guild.create_category(cfg["cat"])
            await dc_cat.set_permissions(interaction.guild.default_role, read_messages=False)
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True, attach_files=True)
        }
        for rn in cfg["allow"]:
            r = discord.utils.get(interaction.guild.roles, name=rn)
            if r:
                overwrites[r] = discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True, attach_files=True)
        
        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name.lower()}",
            category=dc_cat,
            overwrites=overwrites,
            topic=f"🎫 {category} | Created by {interaction.user.name}"
        )
        
        embed = discord.Embed(
            title=f"{cfg['emoji']} {category} Ticket",
            description=f"### Welcome {interaction.user.mention}!\n\nAnswer the questions below:\n\n━━━━━━━━━━━━━━━━━━",
            color=cfg["color"],
            timestamp=datetime.utcnow()
        )
        for i, q in enumerate(cfg["q"], 1):
            embed.add_field(name=f"📋 Q{i}", value=q, inline=False)
        embed.add_field(name="👤 Created By", value=interaction.user.mention, inline=True)
        embed.add_field(name="📂 Category", value=category, inline=True)
        embed.set_footer(text=f"ID: {channel.id}")
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        
        view = TicketView()
        await channel.send(embed=embed, view=view)
        
        ping_msg = ""
        for rn in cfg["ping"]:
            r = discord.utils.get(interaction.guild.roles, name=rn)
            if r:
                ping_msg += f"{r.mention} "
        if ping_msg:
            await channel.send(f"{ping_msg}\n📩 New {category} ticket from {interaction.user.mention}!")
        
        await interaction.followup.send(f"✅ {channel.mention}", ephemeral=True)

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="ticketpanel", description="Create ticket panel (Admin)")
    @app_commands.default_permissions(administrator=True)
    async def ticketpanel(self, interaction: discord.Interaction):
        async for msg in interaction.channel.history(limit=20):
            if msg.author == self.bot.user:
                try: await msg.delete()
                except: pass
        
        embed = discord.Embed(title="🎫 Support Tickets", description="### Select a category below!", color=0x2b2d31)
        embed.add_field(name="Categories", value="🏠 Base Buying\n🕳️ Bedrock Hole\n🔄 Spawner Trade\n🏗️ Building\n❓ Support\n⚠️ Scam Report")
        if interaction.guild.icon: embed.set_thumbnail(url=interaction.guild.icon.url)
        
        view = discord.ui.View(timeout=None)
        view.add_item(CategorySelect())
        await interaction.response.send_message(embed=embed, view=view)
    
    @app_commands.command(name="rename", description="Rename ticket channel (Staff)")
    @app_commands.describe(new_name="New channel name")
    @is_staff()
    async def rename(self, interaction: discord.Interaction, new_name: str):
        if not (interaction.channel.name.startswith("ticket-") or interaction.channel.name.startswith("claimed-")):
            await interaction.response.send_message("❌ Ticket channels only!", ephemeral=True)
            return
        clean = new_name.lower().replace(" ", "-")[:50]
        try:
            await interaction.channel.edit(name=f"ticket-{clean}")
            await interaction.response.send_message(f"✅ Renamed!")
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
    
    @app_commands.command(name="add", description="Add user to ticket")
    @app_commands.describe(member="User to add")
    @is_staff()
    async def add(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.channel.set_permissions(member, read_messages=True, send_messages=True)
        await interaction.response.send_message(f"✅ {member.mention} added")
    
    @app_commands.command(name="remove", description="Remove user from ticket")
    @app_commands.describe(member="User to remove")
    @is_staff()
    async def remove(self, interaction: discord.Interaction, member: discord.Member):
        if member == interaction.user:
            await interaction.response.send_message("❌ Can't remove yourself!", ephemeral=True)
            return
        await interaction.channel.set_permissions(member, read_messages=False, send_messages=False)
        await interaction.response.send_message(f"✅ {member.mention} removed")
    
    @app_commands.command(name="close", description="Close ticket")
    async def close(self, interaction: discord.Interaction):
        if not (interaction.channel.name.startswith("ticket-") or interaction.channel.name.startswith("claimed-")):
            await interaction.response.send_message("❌ Ticket channels only!", ephemeral=True)
            return
        
        has_perm = False
        for rn in [STAFF_ROLE, BASE_BUYING_ROLE, BEDROCK_ROLE, SPAWNER_ROLE, BUILDING_ROLE]:
            r = discord.utils.get(interaction.guild.roles, name=rn)
            if r and r in interaction.user.roles:
                has_perm = True
                break
        
        creator = interaction.channel.name.replace("ticket-", "").replace("claimed-", "")
        if interaction.user.name.lower() == creator.lower():
            has_perm = True
        
        if not has_perm:
            await interaction.response.send_message("❌ No permission!", ephemeral=True)
            return
        
        await interaction.response.send_message("🔒 Closing in 5s...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

async def setup(bot):
    await bot.add_cog(Tickets(bot))