import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
from cogs.config import admin_only, get_guild_config
from cogs.tickets_base import TicketView
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

    # Trusted Staff role – can see the ticket but NOT confirm payment
    trusted_staff_name = cfg["TRUSTED_STAFF_ROLE"]
    trusted_staff = discord.utils.get(guild.roles, name=trusted_staff_name)
    if not trusted_staff:
        return await interaction.response.send_message("❌ Trusted Staff role not found. Check your dashboard config.", ephemeral=True)

    # The 295 role – can confirm payment (and also see the ticket)
    confirmation_role_id = cfg.get("BUILD_TICKET_PING_ROLE_ID")
    confirmation_role = guild.get_role(confirmation_role_id) if confirmation_role_id else None
    if not confirmation_role:
        # Fallback to a role named "295"
        confirmation_role = discord.utils.get(guild.roles, name="295")
    if not confirmation_role:
        return await interaction.response.send_message("❌ Confirmation role (295) not found. Set BUILD_TICKET_PING_ROLE_ID in the dashboard.", ephemeral=True)

    # T1 Builder role – can see ticket (and claim orders later)
    t1_role = guild.get_role(cfg.get("BUILDER_T1_ROLE_ID")) if cfg.get("BUILDER_T1_ROLE_ID") else None

    # Category
    cat = discord.utils.get(guild.categories, name="Building")
    if not cat:
        cat = await guild.create_category("Building")
        await cat.set_permissions(guild.default_role, read_messages=False)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        buyer: discord.PermissionOverwrite(read_messages=True, send_messages=False),  # read-only
        trusted_staff: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        confirmation_role: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    if t1_role:
        overwrites[t1_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    channel = await guild.create_text_channel(
        name=f"build-{buyer.name.lower()}",
        category=cat,
        overwrites=overwrites,
        topic=f"Build: {build['name']} | Buyer: {buyer.name} | IGN: {ign} | Region: {region}"
    )

    # Save order to DB (price is now a string)
    order_doc = {
        "guild_id": guild.id,
        "ticket_channel_id": channel.id,
        "buyer_id": buyer.id,
        "ign": ign,
        "region": region,
        "build_id": build["id"],
        "build_name": build["name"],
        "price": build["price"],          # string
        "status": "unpaid",
        "builder_id": None,
        "order_message_id": None,
        "created_at": datetime.now(timezone.utc)
    }
    db["building_orders"].insert_one(order_doc)

    # Payment embed
    payment_method = cfg.get("PAYMENT_METHOD", "your payment method")
    pay_description = f"**Pay {build['price']}** to `{payment_method}`\n\n" \
                      f"**IGN:** {ign}\n**Region:** {region}\n\n" \
                      "After paying, click the **Paid** button."
    pay_embed = discord.Embed(
        title=f"🧾 Payment Required – {build['name']}",
        description=pay_description,
        color=0xf1c40f
    )
    pay_embed.set_footer(text=f"Order ID: {channel.id}")
    view = PaymentView(buyer.id, channel.id, confirmation_role)  # <-- pass the 295 role
    await channel.send(embed=pay_embed, view=view)

    # Add the standard close button view
    close_view = TicketView()
    await channel.send("\n**Staff Controls**", view=close_view)

    # Ping the 295 role (or configured ping role)
    await channel.send(f"{confirmation_role.mention} A new build ticket has been opened!", delete_after=10)

    await interaction.response.send_message(f"✅ Build ticket created: {channel.mention}", ephemeral=True)


# ---------------------------------------------------------------------------
# Payment views
# ---------------------------------------------------------------------------
class PaymentView(discord.ui.View):
    def __init__(self, buyer_id: int, channel_id: int, confirmation_role: discord.Role):
        super().__init__(timeout=None)
        self.buyer_id = buyer_id
        self.channel_id = channel_id
        self.confirmation_role = confirmation_role

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
        confirm_view = ConfirmPaymentView(self.buyer_id, self.channel_id, self.confirmation_role)
        embed = discord.Embed(
            title="🔐 Confirm Payment",
            description=f"{interaction.user.mention} has marked the order as paid.\n"
                        "Click **Received** if payment arrived, or **Didn't Receive** to go back.",
            color=0x3498db
        )
        await interaction.response.edit_message(embed=embed, view=confirm_view)

    async def close_callback(self, interaction: discord.Interaction):
        mention = self.confirmation_role.mention if self.confirmation_role else "@295"
        await interaction.response.send_message(f"{mention} {interaction.user.mention} wants to close this ticket.", ephemeral=False)


class ConfirmPaymentView(discord.ui.View):
    def __init__(self, buyer_id: int, channel_id: int, confirmation_role: discord.Role):
        super().__init__(timeout=None)
        self.buyer_id = buyer_id
        self.channel_id = channel_id
        self.confirmation_role = confirmation_role

        self.received_btn = discord.ui.Button(label="✅ Received", style=discord.ButtonStyle.green, custom_id=f"confirm_received_{channel_id}")
        self.deny_btn = discord.ui.Button(label="❌ Didn't Receive", style=discord.ButtonStyle.red, custom_id=f"confirm_deny_{channel_id}")
        self.received_btn.callback = self.received_callback
        self.deny_btn.callback = self.deny_callback
        self.add_item(self.received_btn)
        self.add_item(self.deny_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only the 295 role (confirmation_role) can confirm payment
        if self.confirmation_role not in interaction.user.roles and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only the 295 role can confirm payment.", ephemeral=True)
            return False
        return True

    async def received_callback(self, interaction: discord.Interaction):
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            return await interaction.response.send_message("❌ Ticket channel not found.", ephemeral=True)

        # Unmute buyer safely
        buyer = interaction.guild.get_member(self.buyer_id)
        if buyer:
            current_overwrites = channel.overwrites_for(buyer)
            current_overwrites.send_messages = True
            current_overwrites.read_messages = True
            try:
                await channel.set_permissions(buyer, overwrite=current_overwrites)
            except discord.Forbidden:
                await interaction.response.send_message("❌ I lack permission to update the buyer.", ephemeral=True)
                return
        else:
            await interaction.response.send_message("⚠️ Buyer is no longer in the server. Continuing...", ephemeral=True)

        # Update DB
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
        try:
            await post_order_to_builder_channel(interaction, self.channel_id)
        except Exception as e:
            print(f"❌ Error posting to builder-orders: {e}")
            await interaction.followup.send("⚠️ Order posted, but failed to ping builders.", ephemeral=True)
            return

        await interaction.followup.send("✅ Payment confirmed and order sent to builders.", ephemeral=True)

    async def deny_callback(self, interaction: discord.Interaction):
        pay_view = PaymentView(self.buyer_id, self.channel_id, self.confirmation_role)
        embed = discord.Embed(
            title="🧾 Payment Required",
            description="The payment was not received. Please pay and click Paid again.",
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
    embed.add_field(name="Price", value=order["price"], inline=True)   # already string
    embed.set_footer(text=f"Ticket: {guild.get_channel(ticket_channel_id).name}")

    view = BuilderClaimView(order)
    msg = await orders_channel.send(embed=embed, view=view)
    db["building_orders"].update_one(
        {"ticket_channel_id": ticket_channel_id},
        {"$set": {"order_message_id": msg.id}}
    )

    # Ping the configured builder ping role (or T3)
    cfg = get_guild_config(db, guild.id)
    ping_role_id = cfg.get("BUILD_ORDER_PING_ROLE_ID")
    ping_role = guild.get_role(ping_role_id) if ping_role_id else None
    if not ping_role:
        # Fallback to T3 builder role
        t3_role_id = cfg.get("BUILDER_T3_ROLE_ID")
        ping_role = guild.get_role(t3_role_id) if t3_role_id else None
    if ping_role:
        await orders_channel.send(f"{ping_role.mention} New build order available! ⬆️")   # no delete_after


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
        current = db["building_orders"].find_one({"ticket_channel_id": self.order["ticket_channel_id"]})
        if not current or current.get("builder_id"):
            return await interaction.response.send_message("❌ This order has already been claimed.", ephemeral=True)

        ticket_ch = interaction.guild.get_channel(self.order["ticket_channel_id"])
        if not ticket_ch:
            return await interaction.response.send_message("❌ Ticket channel not found.", ephemeral=True)

        await ticket_ch.set_permissions(interaction.user, read_messages=True, send_messages=True)
        db["building_orders"].update_one(
            {"ticket_channel_id": self.order["ticket_channel_id"]},
            {"$set": {"builder_id": interaction.user.id, "status": "claimed"}}
        )

        embed = interaction.message.embeds[0]
        embed.add_field(name="Claimed By", value=interaction.user.mention, inline=False)
        embed.color = discord.Color.green()
        await interaction.message.edit(embed=embed, view=None)

        await interaction.response.send_message(f"✅ Order claimed by {interaction.user.mention}.", ephemeral=True)
        await ticket_ch.send(f"🔨 {interaction.user.mention} has claimed this build order. You can now coordinate.")


# ---------------------------------------------------------------------------
# Build Panel View & Button
# ---------------------------------------------------------------------------
class BuildPanelView(discord.ui.View):
    def __init__(self, builds: list):
        super().__init__(timeout=None)
        for b in builds:
            self.add_item(BuildButton(b))


class BuildButton(discord.ui.Button):
    def __init__(self, build: dict):
        raw_emoji = build.get("emoji", "🧱")
        try:
            if not raw_emoji or not isinstance(raw_emoji, str):
                emoji = "🧱"
            elif raw_emoji.startswith("<") and raw_emoji.endswith(">"):
                emoji = discord.PartialEmoji.from_str(raw_emoji)
            elif len(raw_emoji) == 1:
                emoji = raw_emoji
            else:
                raise ValueError("Invalid emoji format")
        except Exception:
            emoji = "🧱"
            print(f"⚠️ Invalid emoji for build '{build.get('name')}': {raw_emoji!r} – using default")

        super().__init__(
            label=build["name"],
            style=discord.ButtonStyle.primary,
            custom_id=f"build_{build['id']}",
            emoji=emoji
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

        @bot.event
        async def on_ready():
            await self.restore_panel_views()

    async def restore_panel_views(self):
        for doc in self.bot.db["building_panels"].find():
            guild_id = doc["guild_id"]
            builds = doc.get("builds", [])
            if builds:
                view = BuildPanelView(builds)
                self.bot.add_view(view)
                print(f"✅ Restored build panel view for guild {guild_id}")

    @app_commands.command(name="buildpanel", description="Post/update the build ordering panel")
    @admin_only()
    async def buildpanel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)

        db = self.bot.db
        panel = db["building_panels"].find_one({"guild_id": interaction.guild.id})
        if not panel or not panel.get("builds"):
            return await interaction.edit_original_response(
                content="❌ No builds configured. Set them up in the dashboard first."
            )

        builds = panel["builds"]
        embed = discord.Embed(
            title="🏗️ Build Orders",
            description="Select a build below to place your order.",
            color=0x5865F2
        )
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)

        original_msg = await interaction.original_response()
        async for msg in interaction.channel.history(limit=20):
            if msg.author == self.bot.user and msg.id != original_msg.id:
                try:
                    await msg.delete()
                except discord.HTTPException:
                    pass

        view = BuildPanelView(builds)
        await interaction.edit_original_response(content=None, embed=embed, view=view)

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
            for ch in after.guild.text_channels:
                if ch.name.startswith("build-"):
                    try:
                        await ch.set_permissions(after, read_messages=True, send_messages=True)
                    except Exception as e:
                        print(f"Failed to add T1 to {ch.name}: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Building(bot))