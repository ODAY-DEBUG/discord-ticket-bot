import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
from cogs.config import admin_only, get_guild_config
from cogs.tickets_base import TicketView  # reuse close button from base
import asyncio

# ---------------------------------------------------------------------------
# Helper: permission check for builder roles (T1/T2/T3)
# ---------------------------------------------------------------------------
def is_builder(interaction: discord.Interaction) -> bool:
    cfg = get_guild_config(interaction.client.db, interaction.guild.id)
    t1 = interaction.guild.get_role(cfg.get("BUILDER_T1_ROLE_ID"))
    t2 = interaction.guild.get_role(cfg.get("BUILDER_T2_ROLE_ID"))
    t3 = interaction.guild.get_role(cfg.get("BUILDER_T3_ROLE_ID"))
    for role in (t1, t2, t3):
        if role and role in interaction.user.roles:
            return True
    return interaction.user.guild_permissions.administrator


# ---------------------------------------------------------------------------
# Modals
# ---------------------------------------------------------------------------
class BuildOrderModal(discord.ui.Modal, title="Place a Build Order"):
    def __init__(self, build: dict):
        super().__init__()
        self.build = build
        self.add_item(discord.ui.TextInput(label="Your IGN", custom_id="ign", required=True))
        self.add_item(discord.ui.TextInput(label="Region (e.g. EU, NA, ASIA)", custom_id="region", required=True))

    async def on_submit(self, interaction: discord.Interaction):
        ign = self.children[0].value.strip()
        region = self.children[1].value.strip()

        # Check for existing build ticket
        for ch in interaction.guild.text_channels:
            if ch.name.endswith(f"-{interaction.user.name.lower()}") and ch.name.startswith("build-"):
                await interaction.response.send_message(f"❌ You already have an open build ticket: {ch.mention}", ephemeral=True)
                return

        await create_build_ticket(interaction, self.build, ign, region)


# ---------------------------------------------------------------------------
# Ticket creation flow
# ---------------------------------------------------------------------------
async def create_build_ticket(interaction: discord.Interaction, build: dict, ign: str, region: str):
    guild = interaction.guild
    buyer = interaction.user
    db = interaction.client.db
    cfg = get_guild_config(db, guild.id)

    # Owner role – use whatever role is marked as staff (or a dedicated owner role)
    owner_role = discord.utils.get(guild.roles, name=cfg["STAFF_ROLE"])
    if not owner_role:
        return await interaction.response.send_message("❌ Staff role not found. Please set up roles in the dashboard.", ephemeral=True)

    # Category
    cat = discord.utils.get(guild.categories, name="Building")
    if not cat:
        cat = await guild.create_category("Building")
        await cat.set_permissions(guild.default_role, read_messages=False)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        buyer: discord.PermissionOverwrite(read_messages=True, send_messages=False),  # can see, can't talk
        owner_role: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    channel = await guild.create_text_channel(
        name=f"build-{buyer.name.lower()}",
        category=cat,
        overwrites=overwrites,
        topic=f"Build: {build['name']} | Buyer: {buyer.name} | IGN: {ign} | Region: {region}"
    )

    # Save order to DB
    order_doc = {
        "guild_id": guild.id,
        "ticket_channel_id": channel.id,
        "buyer_id": buyer.id,
        "ign": ign,
        "region": region,
        "build_id": build["id"],
        "build_name": build["name"],
        "price": build["price"],
        "status": "unpaid",            # unpaid → paid → confirmed → closed
        "builder_id": None,
        "order_message_id": None,
        "created_at": datetime.now(timezone.utc)
    }
    db["building_orders"].insert_one(order_doc)

    # Payment embed
    pay_embed = discord.Embed(
        title=f"🧾 Payment Required – {build['name']}",
        description=f"**Pay ${build['price']}** to `YOUR_PAYMENT_METHOD`\n\n"
                    f"**IGN:** {ign}\n**Region:** {region}\n\n"
                    "After paying, click the **Paid** button.",
        color=0xf1c40f
    )
    pay_embed.set_footer(text=f"Order ID: {channel.id}")
    view = PaymentView(buyer.id, channel.id, owner_role)
    await channel.send(embed=pay_embed, view=view)

    # Also add the standard close button view (so staff can close later)
    close_view = TicketView()
    await channel.send("\n**Staff Controls**", view=close_view)

    await interaction.response.send_message(f"✅ Build ticket created: {channel.mention}", ephemeral=True)


# ---------------------------------------------------------------------------
# Payment views
# ---------------------------------------------------------------------------
class PaymentView(discord.ui.View):
    def __init__(self, buyer_id: int, channel_id: int, owner_role: discord.Role):
        super().__init__(timeout=None)
        self.buyer_id = buyer_id
        self.channel_id = channel_id
        self.owner_role = owner_role

        paid_btn = discord.ui.Button(label="💰 Paid", style=discord.ButtonStyle.green, custom_id=f"paid_{channel_id}")
        close_btn = discord.ui.Button(label="🔒 Close Ticket", style=discord.ButtonStyle.grey, custom_id=f"close_ticket_{channel_id}")
        paid_btn.callback = self.paid_callback
        close_btn.callback = self.close_callback
        self.add_item(paid_btn)
        self.add_item(close_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.buyer_id:
            await interaction.response.send_message("❌ Only the order owner can use this.", ephemeral=True)
            return False
        return True

    async def paid_callback(self, interaction: discord.Interaction):
        # Switch to confirmation view
        confirm_view = ConfirmPaymentView(self.buyer_id, self.channel_id, self.owner_role)
        embed = discord.Embed(
            title="🔐 Confirm Payment",
            description=f"{interaction.user.mention} has marked the order as paid.\n"
                        "Please click **Received** if payment arrived, or **Didn't Receive** to go back.",
            color=0x3498db
        )
        await interaction.response.edit_message(embed=embed, view=confirm_view)

    async def close_callback(self, interaction: discord.Interaction):
        # Buyer can request close – staff must approve via TicketView.
        staff_role = self.owner_role
        mention = staff_role.mention if staff_role else "@Staff"
        await interaction.response.send_message(f"{mention} {interaction.user.mention} wants to close this ticket.", ephemeral=False)
        # Optionally add a reaction or let TicketView handle it


class ConfirmPaymentView(discord.ui.View):
    def __init__(self, buyer_id: int, channel_id: int, owner_role: discord.Role):
        super().__init__(timeout=None)
        self.buyer_id = buyer_id
        self.channel_id = channel_id
        self.owner_role = owner_role

        self.received_btn = discord.ui.Button(label="✅ Received", style=discord.ButtonStyle.green, custom_id=f"confirm_received_{channel_id}")
        self.deny_btn = discord.ui.Button(label="❌ Didn't Receive", style=discord.ButtonStyle.red, custom_id=f"confirm_deny_{channel_id}")
        self.received_btn.callback = self.received_callback
        self.deny_btn.callback = self.deny_callback
        self.add_item(self.received_btn)
        self.add_item(self.deny_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only staff/owner can confirm
        if self.owner_role not in interaction.user.roles and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only staff can confirm payment.", ephemeral=True)
            return False
        return True

    async def received_callback(self, interaction: discord.Interaction):
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            return await interaction.response.send_message("❌ Channel not found.", ephemeral=True)

        # Unmute buyer
        buyer = interaction.guild.get_member(self.buyer_id)
        if buyer:
            await channel.set_permissions(buyer, send_messages=True)

        # Update order in DB
        db = interaction.client.db
        db["building_orders"].update_one(
            {"ticket_channel_id": self.channel_id},
            {"$set": {"status": "confirmed"}}
        )

        # Success embed
        success_embed = discord.Embed(
            title="✅ Payment Confirmed",
            description="The buyer can now talk. Please proceed with the build.",
            color=0x2ecc71
        )
        await interaction.response.edit_message(embed=success_embed, view=None)

        # Post order to builder-orders channel
        await post_order_to_builder_channel(interaction, self.channel_id)

    async def deny_callback(self, interaction: discord.Interaction):
        # Revert to original payment view
        pay_view = PaymentView(self.buyer_id, self.channel_id, self.owner_role)
        embed = discord.Embed(
            title="🧾 Payment Required",
            description=interaction.message.embeds[0].description.replace("🔐 Confirm Payment", "🧾 Payment Required"),
            color=0xf1c40f
        )
        await interaction.response.edit_message(embed=embed, view=pay_view)


# ---------------------------------------------------------------------------
# Post order to builder-orders channel
# ---------------------------------------------------------------------------
async def post_order_to_builder_channel(interaction: discord.Interaction, ticket_channel_id: int):
    guild = interaction.guild
    db = interaction.client.db
    order = db["building_orders"].find_one({"ticket_channel_id": ticket_channel_id})
    if not order:
        return

    orders_channel_id = get_guild_config(db, guild.id).get("BUILDER_ORDERS_CHANNEL_ID")
    if not orders_channel_id:
        return

    orders_channel = guild.get_channel(orders_channel_id)
    if not orders_channel:
        return

    embed = discord.Embed(
        title=f"🛠️ New Build Order – {order['build_name']}",
        color=0xf39c12,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="IGN", value=order["ign"], inline=True)
    embed.add_field(name="Region", value=order["region"], inline=True)
    embed.add_field(name="Price", value=f"${order['price']}", inline=True)
    embed.set_footer(text=f"Ticket: {guild.get_channel(ticket_channel_id).name}")

    view = BuilderClaimView(order)
    msg = await orders_channel.send(embed=embed, view=view)
    db["building_orders"].update_one(
        {"ticket_channel_id": ticket_channel_id},
        {"$set": {"order_message_id": msg.id}}
    )

    # Ping builder role
    cfg = get_guild_config(db, guild.id)
    for rid in [cfg.get("BUILDER_T1_ROLE_ID"), cfg.get("BUILDER_T2_ROLE_ID"), cfg.get("BUILDER_T3_ROLE_ID")]:
        role = guild.get_role(rid)
        if role:
            await orders_channel.send(f"{role.mention} New order available! ⬆️", delete_after=5)


# ---------------------------------------------------------------------------
# Builder claim view
# ---------------------------------------------------------------------------
class BuilderClaimView(discord.ui.View):
    def __init__(self, order: dict):
        super().__init__(timeout=None)
        self.order = order
        claim_btn = discord.ui.Button(label="🔨 Claim Order", style=discord.ButtonStyle.green, custom_id=f"claim_{order['ticket_channel_id']}")
        claim_btn.callback = self.claim_callback
        self.add_item(claim_btn)

    async def claim_callback(self, interaction: discord.Interaction):
        if not is_builder(interaction):
            return await interaction.response.send_message("❌ Only builders can claim orders.", ephemeral=True)

        db = interaction.client.db
        # Check if already claimed
        current = db["building_orders"].find_one({"ticket_channel_id": self.order["ticket_channel_id"]})
        if not current or current.get("builder_id"):
            return await interaction.response.send_message("❌ This order has already been claimed.", ephemeral=True)

        ticket_ch = interaction.guild.get_channel(self.order["ticket_channel_id"])
        if not ticket_ch:
            return await interaction.response.send_message("❌ Ticket channel not found.", ephemeral=True)

        # Assign builder and update permissions
        await ticket_ch.set_permissions(interaction.user, read_messages=True, send_messages=True)
        db["building_orders"].update_one(
            {"ticket_channel_id": self.order["ticket_channel_id"]},
            {"$set": {"builder_id": interaction.user.id, "status": "claimed"}}
        )

        # Update order message
        embed = interaction.message.embeds[0]
        embed.add_field(name="Claimed By", value=interaction.user.mention, inline=False)
        embed.color = discord.Color.green()
        await interaction.message.edit(embed=embed, view=None)

        await interaction.response.send_message(f"✅ Order claimed by {interaction.user.mention}.", ephemeral=True)
        await ticket_ch.send(f"🔨 {interaction.user.mention} has claimed this build order. You can now coordinate.")


# ---------------------------------------------------------------------------
# Build Panel View & Command
# ---------------------------------------------------------------------------
class BuildPanelView(discord.ui.View):
    def __init__(self, builds: list):
        super().__init__(timeout=None)
        for b in builds:
            self.add_item(BuildButton(b))


class BuildButton(discord.ui.Button):
    def __init__(self, build: dict):
        super().__init__(
            label=build["name"],
            style=discord.ButtonStyle.primary,
            custom_id=f"build_{build['id']}",
            emoji=build.get("emoji", "🧱")
        )
        self.build = build

    async def callback(self, interaction: discord.Interaction):
        modal = BuildOrderModal(self.build)
        await interaction.response.send_modal(modal)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------
class Building(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Restore persistent views for all guilds on startup
        @bot.event
        async def on_ready():
            await self.restore_panel_views()

    async def restore_panel_views(self):
        """Re-register BuildPanelView for any guild that has builds in DB."""
        for doc in self.bot.db["building_panels"].find():
            guild_id = doc["guild_id"]
            builds = doc.get("builds", [])
            if builds:
                view = BuildPanelView(builds)
                # Store a mapping so we can reference later; Discord requires views be registered
                self.bot.add_view(view)
                print(f"✅ Restored build panel view for guild {guild_id}")

    @app_commands.command(name="buildpanel", description="Post/update the build ordering panel")
    @admin_only()
    async def buildpanel(self, interaction: discord.Interaction):
        db = self.bot.db
        panel = db["building_panels"].find_one({"guild_id": interaction.guild.id})
        if not panel or not panel.get("builds"):
            return await interaction.response.send_message("❌ No builds configured. Set them up in the dashboard first.", ephemeral=True)

        builds = panel["builds"]
        embed = discord.Embed(
            title="🏗️ Build Orders",
            description="Select a build below to place your order.",
            color=0x5865F2
        )
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)

        # Clear old bot messages in the channel (optional)
        async for msg in interaction.channel.history(limit=20):
            if msg.author == self.bot.user:
                try:
                    await msg.delete()
                except:
                    pass

        view = BuildPanelView(builds)
        await interaction.response.send_message(embed=embed, view=view)

    # ------------------------------------------------------------------
    # T1 auto-access listener
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        cfg = get_guild_config(self.bot.db, after.guild.id)
        t1_role_id = cfg.get("BUILDER_T1_ROLE_ID")
        if not t1_role_id:
            return
        t1_role = after.guild.get_role(t1_role_id)
        if not t1_role:
            return
        if t1_role in after.roles and t1_role not in before.roles:
            # Give T1 access to all active build tickets
            for ch in after.guild.text_channels:
                if ch.name.startswith("build-"):
                    try:
                        await ch.set_permissions(after, read_messages=True, send_messages=True)
                    except Exception as e:
                        print(f"Failed to add T1 to {ch.name}: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Building(bot))