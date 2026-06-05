import discord
from discord.ext import commands
import asyncio
import io
from datetime import datetime

STAFF_ROLE = "Staff"

class TicketView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
    
    @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.green, custom_id="create_ticket")
    async def create_ticket_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        existing = discord.utils.get(interaction.guild.channels, name=f"ticket-{interaction.user.name.lower()}")
        if not existing:
            existing = discord.utils.get(interaction.guild.channels, name=f"claimed-{interaction.user.name.lower()}")
        
        if existing:
            await interaction.response.send_message(f"You already have a ticket: {existing.mention}", ephemeral=True)
            return
        
        tickets_cog = self.bot.get_cog('Tickets')
        if tickets_cog:
            await tickets_cog.create_ticket(interaction)

class TicketManageView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
    
    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.channel.name.startswith("ticket-") and not interaction.channel.name.startswith("claimed-"):
            return
        
        tickets_cog = self.bot.get_cog('Tickets')
        if tickets_cog:
            await tickets_cog.close_ticket(interaction)

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
        super().__init__(placeholder="Select ticket type...", options=options, custom_id="ticket_select")
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        existing = discord.utils.get(interaction.guild.channels, name=f"ticket-{interaction.user.name.lower()}")
        if not existing:
            existing = discord.utils.get(interaction.guild.channels, name=f"claimed-{interaction.user.name.lower()}")
        
        if existing:
            await interaction.followup.send(f"You already have a ticket: {existing.mention}", ephemeral=True)
            return
        
        tickets_cog = self.bot.get_cog('Tickets')
        if tickets_cog:
            category = discord.utils.get(interaction.guild.categories, name="Tickets")
            if not category:
                category = await interaction.guild.create_category("Tickets")
                await category.set_permissions(interaction.guild.default_role, read_messages=False)
            
            staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE)
            
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            if staff_role:
                overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
            channel = await interaction.guild.create_text_channel(
                name=f"ticket-{interaction.user.name.lower()}",
                category=category,
                overwrites=overwrites,
                topic=f"Ticket by {interaction.user} | {self.values[0]}"
            )
            
            questions = {
                "General Support": ["What do you need help with?"],
                "Base Buying": ["What type of base?", "Your budget?"],
                "Bedrock Hole Buying": ["What size?", "Your budget?"],
                "Spawner Trading": ["Buying or selling?", "Type and quantity?", "Price?"],
                "Building": ["What to build?", "Your budget?", "Deadline?"],
                "Scam Report": ["Who scammed you?", "What happened?", "Proof?"],
            }
            
            embed = discord.Embed(
                title=f"{self.values[0]} Ticket",
                description=f"Welcome {interaction.user.mention}! Please answer:",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            
            for i, q in enumerate(questions.get(self.values[0], ["Describe your issue"]), 1):
                embed.add_field(name=f"Question {i}", value=q, inline=False)
            
            embed.set_footer(text=f"Ticket ID: {channel.id}")
            
            view = TicketManageView(self.bot)
            await channel.send(embed=embed, view=view)
            
            if staff_role:
                await channel.send(f"{staff_role.mention} New {self.values[0]} ticket from {interaction.user.mention}")
            
            await interaction.followup.send(f"Ticket created: {channel.mention}", ephemeral=True)

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    async def create_ticket(self, interaction):
        category = discord.utils.get(interaction.guild.categories, name="Tickets")
        if not category:
            category = await interaction.guild.create_category("Tickets")
            await category.set_permissions(interaction.guild.default_role, read_messages=False)
        
        staff_role = discord.utils.get(interaction.guild.roles, name=STAFF_ROLE)
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name.lower()}",
            category=category,
            overwrites=overwrites
        )
        
        embed = discord.Embed(
            title="Support Ticket",
            description=f"Welcome {interaction.user.mention}! Describe your issue.",
            color=discord.Color.green()
        )
        
        view = TicketManageView(self.bot)
        await channel.send(embed=embed, view=view)
        
        if staff_role:
            await channel.send(f"{staff_role.mention} New ticket")
        
        await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)
    
    async def close_ticket(self, interaction):
        transcript = io.BytesIO()
        content = f"Ticket: {interaction.channel.name}\nClosed by: {interaction.user}\n\n"
        
        async for msg in interaction.channel.history(limit=None, oldest_first=True):
            content += f"[{msg.created_at}] {msg.author}: {msg.content}\n"
        
        transcript.write(content.encode())
        transcript.seek(0)
        
        # Send transcript to ticket creator
        creator_name = interaction.channel.name.replace("ticket-", "").replace("claimed-", "")
        for member in interaction.guild.members:
            if member.name.lower() == creator_name:
                try:
                    await member.send(f"Transcript for {interaction.channel.name}", file=discord.File(transcript, filename="transcript.txt"))
                except:
                    pass
                break
        
        await interaction.response.send_message("Closing in 5 seconds...")
        await asyncio.sleep(5)
        await interaction.channel.delete()
    
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def ticketpanel(self, ctx):
        embed = discord.Embed(
            title="Support Tickets",
            description="Select a category below to create a ticket",
            color=discord.Color.blue()
        )
        embed.add_field(name="Categories", value="❓ General Support\n🏠 Base Buying\n🕳️ Bedrock Hole\n🔄 Spawner Trading\n🏗️ Building\n⚠️ Scam Report")
        
        view = discord.ui.View(timeout=None)
        view.add_item(TicketSelect(self.bot))
        await ctx.send(embed=embed, view=view)
    
    @commands.command()
    async def close(self, ctx):
        if not ctx.channel.name.startswith("ticket-") and not ctx.channel.name.startswith("claimed-"):
            await ctx.send("Use this in a ticket channel")
            return
        
        # Check if user is staff or ticket creator
        staff_role = discord.utils.get(ctx.guild.roles, name=STAFF_ROLE)
        is_staff = staff_role and staff_role in ctx.author.roles
        is_creator = ctx.channel.name.replace("ticket-", "").replace("claimed-", "") == ctx.author.name.lower()
        
        if not is_staff and not is_creator:
            await ctx.send("Only staff or ticket creator can close tickets")
            return
        
        transcript = io.BytesIO()
        content = f"Ticket: {ctx.channel.name}\n\n"
        
        async for msg in ctx.channel.history(limit=None, oldest_first=True):
            content += f"[{msg.created_at}] {msg.author}: {msg.content}\n"
        
        transcript.write(content.encode())
        transcript.seek(0)
        
        creator_name = ctx.channel.name.replace("ticket-", "").replace("claimed-", "")
        for member in ctx.guild.members:
            if member.name.lower() == creator_name:
                try:
                    await member.send(f"Transcript", file=discord.File(transcript, filename="transcript.txt"))
                except:
                    pass
                break
        
        await ctx.send("Closing in 5 seconds...")
        await asyncio.sleep(5)
        await ctx.channel.delete()

async def setup(bot):
    await bot.add_cog(Tickets(bot))