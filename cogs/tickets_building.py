import discord
from discord.ext import commands
from datetime import datetime, timezone
from cogs.config import OWNER_ROLE, BUILDING_ROLE, BUILDER_ORDERS_CHANNEL_ID
from cogs.tickets_base import TicketView

# ---------------------------------------------------------------------------
# Builder Order Views
# ---------------------------------------------------------------------------

class OrderClaimButton(discord.ui.Button):
    def __init__(self, ticket_channel_id: int, creator_id: int):
        super().__init__(
            label="🔨 Claim Order",
            style=discord.ButtonStyle.green,
            custom_id=f"b_claim_{ticket_channel_id}"
        )
        self.ticket_channel_id = ticket_channel_id
        self.creator_id = creator_id

    async def callback(self, interaction: discord.Interaction):
        builder_role = discord.utils.get(interaction.guild.roles, name=BUILDING_ROLE)
        if not builder_role or builder_role not in interaction.user.roles:
            await interaction.response.send_message("❌ Only Builders can claim orders!", ephemeral=True)
            return

        ticket_channel = interaction.guild.get_channel(self.ticket_channel_id)
        if not ticket_channel:
            await interaction.response.send_message("❌ Ticket channel not found.", ephemeral=True)
            return

        # Check if builder already applied
        async for msg in ticket_channel.history(limit=50):
            if msg.components:
                for row in msg.components:
                    for child in row.children:
                        if hasattr(child, 'custom_id') and child.custom_id == f"b_accept_{self.ticket_channel_id}_{interaction.user.id}":
                            await interaction.response.send_message("❌ You have already applied for this order!", ephemeral=True)
                            return

        # Send application to the ticket channel
        embed = discord.Embed(
            title="🛠️ Builder Application",
            description=f"{interaction.user.mention} wants to take this order!",
            color=0x2ecc71
        )
        view = BuilderAcceptView(self.ticket_channel_id, interaction.user.id, self.creator_id)
        await ticket_channel.send(embed=embed, view=view)

        await interaction.response.send_message("✅ Your application has been sent to the ticket!", ephemeral=True)


class OrderClaimView(discord.ui.View):
    def __init__(self, ticket_channel_id: int, creator_id: int):
        super().__init__(timeout=None)
        self.add_item(OrderClaimButton(ticket_channel_id, creator_id))


class BuilderAcceptView(discord.ui.View):
    def __init__(self, ticket_channel_id: int, builder_id: int, creator_id: int):
        super().__init__(timeout=None)
        
        accept_btn = discord.ui.Button(
            label="✅ Accept Builder",
            style=discord.ButtonStyle.green,
            custom_id=f"b_accept_{ticket_channel_id}_{builder_id}"
        )
        deny_btn = discord.ui.Button(
            label="❌ Deny Builder",
            style=discord.ButtonStyle.red,
            custom_id=f"b_deny_{ticket_channel_id}_{builder_id}"
        )
        
        accept_btn.callback = self.accept_callback
        deny_btn.callback = self.deny_callback
        
        self.add_item(accept_btn)
        self.add_item(deny_btn)
        
        self.ticket_channel_id = ticket_channel_id
        self.builder_id = builder_id
        self.creator_id = creator_id
        
    async def accept_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.creator_id:
            return await interaction.response.send_message("❌ Only the ticket creator can accept!", ephemeral=True)
        
        # Acknowledge the button click to prevent "Interaction Failed"
        await interaction.response.defer()
            
        ticket_channel = interaction.guild.get_channel(self.ticket_channel_id)
        builder = interaction.guild.get_member(self.builder_id)
        
        if ticket_channel and builder:
            await ticket_channel.set_permissions(builder, read_messages=True, send_messages=True, read_message_history=True, attach_files=True)
            await ticket_channel.send(f"✅ {builder.mention} has been accepted for this order!")
            
            # Delete all other builder application messages in this channel
            async for msg in ticket_channel.history(limit=50):
                if msg.author == interaction.guild.me and msg.id != interaction.message.id:
                    if msg.components:
                        for row in msg.components:
                            for child in row.children:
                                if hasattr(child, 'custom_id') and child.custom_id and child.custom_id.startswith(f"b_accept_{self.ticket_channel_id}_"):
                                    try: 
                                        await msg.delete()
                                    except: 
                                        pass
                                    break

        # Delete the accepted application message
        try:
            await interaction.message.delete()
        except:
            pass

    async def deny_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.creator_id:
            return await interaction.response.send_message("❌ Only the ticket creator can deny!", ephemeral=True)
        
        # Acknowledge the button click to prevent "Interaction Failed"
        await interaction.response.defer()
            
        # Delete the denied application message
        try:
            await interaction.message.delete()
        except:
            pass


# ---------------------------------------------------------------------------
# Custom Builder Ticket Creation
# ---------------------------------------------------------------------------

async def create_builder_ticket(interaction: discord.Interaction, answers: dict):
    uname = interaction.user.name.lower()
    guild = interaction.guild
    
    # Check for existing ticket
    for ch in guild.text_channels:
        if ch.name.endswith(f"-{uname}") and ch.name.startswith("ticket-"):
            return await interaction.followup.send(f"❌ You already have an open ticket: {ch.mention}", ephemeral=True)

    # Create category if it doesn't exist
    cat_name = "Building"
    dc_cat = discord.utils.get(guild.categories, name=cat_name)
    if not dc_cat:
        dc_cat = await guild.create_category(cat_name)
        await dc_cat.set_permissions(guild.default_role, read_messages=False)

    owner_role = discord.utils.get(guild.roles, name=OWNER_ROLE)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True, attach_files=True),
    }
    
    # Only add Owner role initially
    if owner_role:
        overwrites[owner_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True, attach_files=True)

    channel = await guild.create_text_channel(
        name=f"ticket-{uname}",
        category=dc_cat,
        overwrites=overwrites,
        topic=f"Ticket by {interaction.user.name} | Building",
    )

    # Send ticket embed
    embed = discord.Embed(
        title="🏗️ Building Ticket",
        description=f"### Welcome {interaction.user.mention}!\n\n━━━━━━━━━━━━━━━━━━",
        color=0x9b59b6,
        timestamp=datetime.now(timezone.utc),
    )
    for question, answer in answers.items():
        embed.add_field(name=question, value=answer or "*No answer provided*", inline=False)
    embed.add_field(name="Created By", value=interaction.user.mention, inline=True)
    embed.add_field(name="Category", value="Building", inline=True)
    embed.set_footer(text=f"Channel ID: {channel.id}")
    if guild.icon: embed.set_thumbnail(url=guild.icon.url)

    view = TicketView()
    await channel.send(embed=embed, view=view)

    if owner_role:
        await channel.send(f"{owner_role.mention}\nNew **Building** ticket from {interaction.user.mention}!")

    await interaction.followup.send(f"✅ Ticket created: {channel.mention}", ephemeral=True)

    # --- SEND ORDER TO ORDERS CHANNEL ---
    orders_channel = guild.get_channel(BUILDER_ORDERS_CHANNEL_ID)
    if orders_channel:
        ign = answers.get("What is your IGN?", "N/A")
        budget = answers.get("What is your budget?", "N/A")
        base_type = answers.get("What type of base do you need?", "N/A")
        requirements = answers.get("Do you have any specific requirements?", "None")
        how_soon = answers.get("How soon do you need the base? (ASAP/Week/No rush)", "N/A")
        
        order_embed = discord.Embed(
            title="🛠️ New Builder Order",
            color=0xf1c40f,
            timestamp=datetime.now(timezone.utc)
        )
        order_embed.add_field(name="IGN", value=ign, inline=True)
        order_embed.add_field(name="Budget", value=budget, inline=True)
        order_embed.add_field(name="Base Needed", value=base_type, inline=False)
        order_embed.add_field(name="Specific Requirements", value=requirements, inline=False)
        order_embed.add_field(name="How Soon?", value=how_soon, inline=True)
        order_embed.set_footer(text=f"Ticket: {channel.name}")
        
        claim_view = OrderClaimView(channel.id, interaction.user.id)
        await orders_channel.send(embed=order_embed, view=claim_view)
    else:
        print(f"❌ Builder Orders channel {BUILDER_ORDERS_CHANNEL_ID} not found!")


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class TicketsBuilding(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsBuilding(bot))