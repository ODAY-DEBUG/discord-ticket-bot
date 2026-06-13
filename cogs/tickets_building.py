import discord
from discord.ext import commands
from datetime import datetime, timezone
from cogs.config import OWNER_ROLE, BUILDING_ROLE, get_guild_config
from cogs.tickets_base import TicketView

# ---------------------------------------------------------------------------
# Builder Order Views
# ---------------------------------------------------------------------------

class OrderClaimButton(discord.ui.Button):
    def __init__(self, ticket_channel_id: int, creator_id: int, order_message_id: int = None, order_channel_id: int = None):
        super().__init__(
            label="🔨 Claim Order",
            style=discord.ButtonStyle.green,
            custom_id=f"b_claim_{ticket_channel_id}"
        )
        self.ticket_channel_id = ticket_channel_id
        self.creator_id = creator_id
        self.order_message_id = order_message_id
        self.order_channel_id = order_channel_id

    async def callback(self, interaction: discord.Interaction):
        # 1. Check if user has Builder role
        builder_role = discord.utils.get(interaction.guild.roles, name=BUILDING_ROLE)
        if not builder_role or builder_role not in interaction.user.roles:
            await interaction.response.send_message("❌ Only Builders can claim orders!", ephemeral=True)
            return

        ticket_channel = interaction.guild.get_channel(self.ticket_channel_id)
        if not ticket_channel:
            await interaction.response.send_message("❌ Ticket channel not found.", ephemeral=True)
            return

        # 2. Strict "Apply Once" check using the embed footer
        async for msg in ticket_channel.history(limit=50):
            if msg.author == interaction.guild.me and msg.embeds:
                for embed in msg.embeds:
                    if embed.footer and embed.footer.text == f"Applicant ID: {interaction.user.id}":
                        await interaction.response.send_message("❌ You have already applied for this order! (Even if denied, you cannot re-apply)", ephemeral=True)
                        return

        # 3. Send application to the ticket channel
        embed = discord.Embed(
            title="🛠️ Builder Application",
            description=f"{interaction.user.mention} wants to take this order!",
            color=0x2ecc71
        )
        # Hide their ID in the footer so we can enforce the "apply once" rule
        embed.set_footer(text=f"Applicant ID: {interaction.user.id}")
        
        view = BuilderAcceptView(self.ticket_channel_id, interaction.user.id, self.creator_id, self.order_message_id, self.order_channel_id)
        await ticket_channel.send(embed=embed, view=view)

        await interaction.response.send_message("✅ Your application has been sent to the ticket!", ephemeral=True)


class OrderClaimView(discord.ui.View):
    def __init__(self, ticket_channel_id: int, creator_id: int, order_message_id: int = None, order_channel_id: int = None):
        super().__init__(timeout=None)
        self.add_item(OrderClaimButton(ticket_channel_id, creator_id, order_message_id, order_channel_id))


class BuilderAcceptView(discord.ui.View):
    def __init__(self, ticket_channel_id: int, builder_id: int, creator_id: int, order_message_id: int = None, order_channel_id: int = None):
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
        self.order_message_id = order_message_id
        self.order_channel_id = order_channel_id
        
    async def accept_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.creator_id:
            return await interaction.response.send_message("❌ Only the ticket creator can accept!", ephemeral=True)
            
        await interaction.response.defer()
            
        ticket_channel = interaction.guild.get_channel(self.ticket_channel_id)
        builder = interaction.guild.get_member(self.builder_id)
        
        if ticket_channel and builder:
            # Add builder to the ticket channel
            await ticket_channel.set_permissions(builder, read_messages=True, send_messages=True, read_message_history=True, attach_files=True)
            await ticket_channel.send(f"✅ {builder.mention} has been accepted for this order!")
            
            # Edit ALL other builder applications in this ticket to "Order Claimed"
            async for msg in ticket_channel.history(limit=50):
                if msg.author == interaction.guild.me and msg.id != interaction.message.id:
                    if msg.embeds and msg.components:
                        for row in msg.components:
                            for child in row.children:
                                if hasattr(child, 'custom_id') and child.custom_id and child.custom_id.startswith(f"b_accept_{self.ticket_channel_id}_"):
                                    new_embed = msg.embeds[0]
                                    new_embed.color = discord.Color.dark_grey()
                                    new_embed.title = "🛠️ Application (Order Claimed)"
                                    try: await msg.edit(embed=new_embed, view=None)
                                    except: pass
                                    break

            # Edit the accepted application message
            try:
                new_embed = interaction.message.embeds[0]
                new_embed.color = discord.Color.green()
                new_embed.title = "✅ Builder Accepted"
                await interaction.message.edit(embed=new_embed, view=None)
            except: pass

            # Edit the ORIGINAL message in the Builder Orders channel
            if self.order_channel_id and self.order_message_id:
                orders_channel = interaction.guild.get_channel(self.order_channel_id)
                if orders_channel:
                    try:
                        order_msg = await orders_channel.fetch_message(self.order_message_id)
                        new_order_embed = order_msg.embeds[0] if order_msg.embeds else discord.Embed()
                        new_order_embed.color = discord.Color.green()
                        new_order_embed.title = "🛠️ Order Claimed"
                        new_order_embed.add_field(name="Claimed By", value=builder.mention, inline=False)
                        
                        builder_role = discord.utils.get(interaction.guild.roles, name=BUILDING_ROLE)
                        mention_str = builder_role.mention if builder_role else ""
                        
                        # Edit the message, remove the button, and ping @Builder
                        await order_msg.edit(embed=new_order_embed, view=None, content=f"{mention_str} {builder.mention} claimed this order!")
                    except: pass

    async def deny_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.creator_id:
            return await interaction.response.send_message("❌ Only the ticket creator can deny!", ephemeral=True)
        
        await interaction.response.defer()
            
        # Edit the message to show denied, DO NOT delete so they can't re-apply
        try:
            new_embed = interaction.message.embeds[0]
            new_embed.color = discord.Color.red()
            new_embed.title = "❌ Builder Denied"
            await interaction.message.edit(embed=new_embed, view=None)
        except: pass


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
    orders_channel_id = get_guild_config(interaction.client.db, guild.id).get("BUILDER_ORDERS_CHANNEL_ID")
    orders_channel = guild.get_channel(orders_channel_id) if orders_channel_id else None
    if orders_channel:
        ign = answers.get("What is your IGN?", "N/A")
        budget = answers.get("What is your budget?", "N/A")
        base_type = answers.get("What base do you need?", "N/A")
        requirements = answers.get("Specific requirements?", "None")
        how_soon = answers.get("How soon do you need the base?", "N/A")
        
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
        
        # Create view, send message, then update view with the message ID
        claim_view = OrderClaimView(channel.id, interaction.user.id)
        order_msg = await orders_channel.send(embed=order_embed, view=claim_view)
        
        # Pass the order message ID to the buttons so they can edit this message on accept
        for item in claim_view.children:
            if isinstance(item, OrderClaimButton):
                item.order_message_id = order_msg.id
                item.order_channel_id = orders_channel.id
                
        # Update the message with the fully configured view
        await order_msg.edit(view=claim_view)

        # Ping @Builder to alert them of the new order
        builder_role = discord.utils.get(guild.roles, name=BUILDING_ROLE)
        if builder_role:
            await orders_channel.send(f"{builder_role.mention} New order available above! ⬆️")
            
    elif orders_channel_id:
        print(f"❌ Builder Orders channel {orders_channel_id} not found!")


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class TicketsBuilding(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsBuilding(bot))