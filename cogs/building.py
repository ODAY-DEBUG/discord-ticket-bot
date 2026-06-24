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
# Helper: Dashboard command permissions checker
# ---------------------------------------------------------------------------
def has_cmd_perm(interaction: discord.Interaction, command_name: str) -> bool:
    """Checks if the user has permission based on the dashboard config."""
    if interaction.user.guild_permissions.administrator:
        return True
    
    db = interaction.client.db
    doc = db["command_perms"].find_one({"guild_id": interaction.guild.id, "command_name": command_name})
    
    if not doc or not doc.get("roles"):
        return False
        
    allowed_roles = doc["roles"]
    for role in interaction.user.roles:
        if role.name in allowed_roles:
            return True
    return False

# ---------------------------------------------------------------------------
# Modals
# ---------------------------------------------------------------------------
class BuildOrderModal(discord.ui.Modal, title="Place a Build Order"):
    def __init__(self, build: dict):
        super().__init__()
        self.build = build
        self.add_item(discord.ui.TextInput(label="Your IGN", custom_id="ign", required=True))
        self.add_item(discord.ui.TextInput(label="Region (e.g. EU, NA, ASIA)", custom_id="region", required=True))
        self.add_item(discord.ui.TextInput(label="Farm Name", custom_id="farm_name", required=True, style=discord.TextStyle.paragraph))

    async def on_submit(self, interaction: discord.Interaction):
        ign = self.children[0].value.strip()
        region = self.children[1].value.strip()
        farm_name = self.children[2].value.strip()

        await create_build_ticket(interaction, self.build, ign, region, farm_name)


# ---------------------------------------------------------------------------
# Ticket creation flow
# ---------------------------------------------------------------------------
async def create_build_ticket(interaction: discord.Interaction, build: dict, ign: str, region: str, farm_name: str):
    guild = interaction.guild
    buyer = interaction.user
    db = interaction.client.db
    cfg = get_guild_config(db, guild.id)

    trusted_staff_name = cfg.get("TRUSTED_STAFF_ROLE")
    trusted_staff = discord.utils.get(guild.roles, name=trusted_staff_name) if trusted_staff_name else None
    if not trusted_staff:
        return await interaction.response.send_message("❌ Trusted Staff role not found. Check your dashboard config.", ephemeral=True)

    confirmation_role_id = cfg.get("BUILD_TICKET_PING_ROLE_ID")
    confirmation_role = guild.get_role(confirmation_role_id) if confirmation_role_id else None
    if not confirmation_role:
        confirmation_role = discord.utils.get(guild.roles, name="295")
    if not confirmation_role:
        return await interaction.response.send_message("❌ Confirmation role (295) not found. Set BUILD_TICKET_PING_ROLE_ID in the dashboard.", ephemeral=True)

    t1_role = guild.get_role(cfg.get("BUILDER_T1_ROLE_ID")) if cfg.get("BUILDER_T1_ROLE_ID") else None
    t2_role = guild.get_role(cfg.get("BUILDER_T2_ROLE_ID")) if cfg.get("BUILDER_T2_ROLE_ID") else None
    t3_role = guild.get_role(cfg.get("BUILDER_T3_ROLE_ID")) if cfg.get("BUILDER_T3_ROLE_ID") else None

    cat = discord.utils.get(guild.categories, name="Building")
    if not cat:
        cat = await guild.create_category("Building")
        await cat.set_permissions(guild.default_role, read_messages=False)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        buyer: discord.PermissionOverwrite(read_messages=True, send_messages=False),
        trusted_staff: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        confirmation_role: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    if t1_role: overwrites[t1_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
    if t2_role: overwrites[t2_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
    if t3_role: overwrites[t3_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    channel = await guild.create_text_channel(
        name=f"build-{buyer.name.lower()}",
        category=cat,
        overwrites=overwrites,
        topic=f"Build: {build['name']} | Buyer: {buyer.name} | IGN: {ign} | Region: {region} | Farm: {farm_name}"
    )

    order_doc = {
        "guild_id": guild.id,
        "ticket_channel_id": channel.id,
        "buyer_id": buyer.id,
        "ign": ign,
        "region": region,
        "farm_name": farm_name,
        "build_id": build["id"],
        "build_name": build["name"],
        "price": build["price"],
        "status": "unpaid",
        "builder_id": None,
        "order_message_id": None,
        "notes": [],
        "created_at": datetime.now(timezone.utc)
    }
    db["building_orders"].insert_one(order_doc)

    fresh_cfg = db["bot_config"].find_one({"guild_id": guild.id}) or {}
    payment_method = fresh_cfg.get("PAYMENT_METHOD") or "your payment method"
    
    pay_description = f"**Pay {build['price']}** to `{payment_method}`\n\n" \
                      f"**IGN:** {ign}\n**Region:** {region}\n**Farm Name:** {farm_name}\n\n" \
                      "After paying, click the **Paid** button."
    pay_embed = discord.Embed(
        title=f"🧾 Payment Required – {build['name']}",
        description=pay_description,
        color=0xf1c40f
    )
    pay_embed.set_footer(text=f"Order ID: {channel.id}")
    
    view = PaymentView(buyer.id, channel.id, confirmation_role)
    await channel.send(embed=pay_embed, view=view)

    close_view = TicketView()
    await channel.send("\n**Staff Controls**", view=close_view)

    await channel.send(f"{confirmation_role.mention} A new build ticket has been opened!", delete_after=10)
    if t3_role:
        await channel.send(f"{t3_role.mention} New build order! Please review and claim once payment is confirmed.")

    await interaction.response.send_message(f"✅ Build ticket created: {channel.mention}", ephemeral=True)


# ---------------------------------------------------------------------------
# Payment views
# ---------------------------------------------------------------------------
class PaymentView(discord.ui.View):
    def __init__(self, buyer_id: int, channel_id: int, confirmation_role: discord.Role):
        super().__init__(timeout=None)
        self.buyer_id = buyer_id
        self.channel_id = channel_id
        self.confirmation_role_id = confirmation_role.id if confirmation_role else None

        paid_btn = discord.ui.Button(label="💰 Paid", style=discord.ButtonStyle.green, custom_id=f"paid_{channel_id}")
        close_btn = discord.ui.Button(label="🔒 Close Ticket", style=discord.ButtonStyle.grey, custom_id=f"close_ticket_{channel_id}")
        paid_btn.callback = self.paid_callback
        close_btn.callback = self.close_callback
        self.add_item(paid_btn)
        self.add_item(close_btn)

    async def paid_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.buyer_id:
            return await interaction.response.send_message("❌ Only the order owner can mark this as paid.", ephemeral=True)
        confirmation_role = interaction.guild.get_role(self.confirmation_role_id) if self.confirmation_role_id else None
        confirm_view = ConfirmPaymentView(self.buyer_id, self.channel_id, confirmation_role)
        embed = discord.Embed(
            title="🔐 Confirm Payment",
            description=f"{interaction.user.mention} has marked the order as paid.\nClick **Received** if payment arrived, or **Didn't Receive** to go back.",
            color=0x3498db
        )
        await interaction.response.edit_message(embed=embed, view=confirm_view)

    async def close_callback(self, interaction: discord.Interaction):
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            return await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
        confirmation_role = interaction.guild.get_role(self.confirmation_role_id) if self.confirmation_role_id else None
        is_buyer = interaction.user.id == self.buyer_id
        is_staff = interaction.user.guild_permissions.administrator or (confirmation_role and confirmation_role in interaction.user.roles)
        if not is_buyer and not is_staff:
            return await interaction.response.send_message("❌ Only the ticket owner or staff can close this.", ephemeral=True)
        await interaction.response.send_message("🔒 Closing ticket in 5 seconds...", ephemeral=True)
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Build ticket closed by {interaction.user}")
        except discord.HTTPException as e:
            print(f"Failed to delete build ticket channel: {e}")


class ConfirmPaymentView(discord.ui.View):
    def __init__(self, buyer_id: int, channel_id: int, confirmation_role: discord.Role):
        super().__init__(timeout=None)
        self.buyer_id = buyer_id
        self.channel_id = channel_id
        self.confirmation_role_id = confirmation_role.id if confirmation_role else None

        self.received_btn = discord.ui.Button(label="✅ Received", style=discord.ButtonStyle.green, custom_id=f"confirm_received_{channel_id}")
        self.deny_btn = discord.ui.Button(label="❌ Didn't Receive", style=discord.ButtonStyle.red, custom_id=f"confirm_deny_{channel_id}")
        self.received_btn.callback = self.received_callback
        self.deny_btn.callback = self.deny_callback
        self.add_item(self.received_btn)
        self.add_item(self.deny_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        confirmation_role = interaction.guild.get_role(self.confirmation_role_id) if self.confirmation_role_id else None
        if confirmation_role not in interaction.user.roles and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only the 295 role can confirm payment.", ephemeral=True)
            return False
        return True

    async def received_callback(self, interaction: discord.Interaction):
        channel = interaction.guild.get_channel(self.channel_id)
        if not channel:
            return await interaction.response.send_message("❌ Ticket channel not found.", ephemeral=True)

        buyer = interaction.guild.get_member(self.buyer_id)
        if buyer:
            current_overwrites = channel.overwrites_for(buyer)
            current_overwrites.send_messages = True
            current_overwrites.read_messages = True
            try:
                await channel.set_permissions(buyer, overwrite=current_overwrites)
            except discord.Forbidden:
                return await interaction.response.send_message("❌ I lack permission to update the buyer.", ephemeral=True)

        db = interaction.client.db
        db["building_orders"].update_one({"ticket_channel_id": self.channel_id}, {"$set": {"status": "confirmed"}})

        success_embed = discord.Embed(title="✅ Payment Confirmed", description="The buyer can now talk. Please proceed with the build.", color=0x2ecc71)
        await interaction.response.edit_message(embed=success_embed, view=None)

        try:
            await post_order_to_builder_channel(interaction, self.channel_id)
        except Exception as e:
            print(f"❌ Error posting to builder-orders: {e}")

    async def deny_callback(self, interaction: discord.Interaction):
        confirmation_role = interaction.guild.get_role(self.confirmation_role_id) if self.confirmation_role_id else None
        pay_view = PaymentView(self.buyer_id, self.channel_id, confirmation_role)
        
        db = interaction.client.db
        order = db["building_orders"].find_one({"ticket_channel_id": self.channel_id})
        price = order["price"] if order else "Unknown"
        
        embed = discord.Embed(title="🧾 Payment Required", description=f"The payment was not received. Please pay `{price}` and click Paid again.", color=0xf1c40f)
        await interaction.response.edit_message(embed=embed, view=pay_view)


# ---------------------------------------------------------------------------
# Post order to builder-orders channel
# ---------------------------------------------------------------------------
async def post_order_to_builder_channel(interaction: discord.Interaction, ticket_channel_id: int):
    guild = interaction.guild
    db = interaction.client.db
    order = db["building_orders"].find_one({"ticket_channel_id": ticket_channel_id})
    if not order: return

    orders_channel_id = get_guild_config(db, guild.id).get("BUILDER_ORDERS_CHANNEL_ID")
    if not orders_channel_id: return

    orders_channel = guild.get_channel(orders_channel_id)
    if not orders_channel: return

    # Safe channel name lookup — avoid AttributeError if channel was deleted
    ticket_channel = guild.get_channel(ticket_channel_id)
    ticket_channel_name = ticket_channel.name if ticket_channel else f"deleted-{ticket_channel_id}"

    embed = discord.Embed(title=f"🛠️ New Build Order – {order['build_name']}", color=0xf39c12, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="IGN", value=order["ign"], inline=True)
    embed.add_field(name="Region", value=order["region"], inline=True)
    embed.add_field(name="Farm Name", value=order.get("farm_name", "N/A"), inline=True)
    embed.add_field(name="Price", value=order["price"], inline=True)
    embed.set_footer(text=f"Ticket: {ticket_channel_name}")

    view = BuilderClaimView(order)
    msg = await orders_channel.send(embed=embed, view=view)
    db["building_orders"].update_one({"ticket_channel_id": ticket_channel_id}, {"$set": {"order_message_id": msg.id}})

    fresh_cfg = db["bot_config"].find_one({"guild_id": guild.id}) or {}
    ping_role_id = fresh_cfg.get("BUILD_ORDER_PING_ROLE_ID")
    ping_role = guild.get_role(ping_role_id) if ping_role_id else None
    if not ping_role:
        t3_role_id = fresh_cfg.get("BUILDER_T3_ROLE_ID")
        ping_role = guild.get_role(t3_role_id) if t3_role_id else None
    if ping_role:
        await orders_channel.send(f"{ping_role.mention} New build order available! ⬆️")


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
        # Always use fresh data from DB — don't trust stale self.order
        current = db["building_orders"].find_one({"ticket_channel_id": self.order["ticket_channel_id"]})
        if not current:
            return await interaction.response.send_message("❌ Order not found in database.", ephemeral=True)
        if current.get("builder_id"):
            return await interaction.response.send_message("❌ This order has already been claimed.", ephemeral=True)

        ticket_ch = interaction.guild.get_channel(current["ticket_channel_id"])
        if not ticket_ch:
            return await interaction.response.send_message("❌ Ticket channel not found.", ephemeral=True)

        await ticket_ch.set_permissions(interaction.user, read_messages=True, send_messages=True)
        db["building_orders"].update_one(
            {"ticket_channel_id": current["ticket_channel_id"]},
            {"$set": {"builder_id": interaction.user.id, "status": "claimed"}}
        )

        embed = interaction.message.embeds[0]
        embed.add_field(name="Claimed By", value=interaction.user.mention, inline=False)
        embed.color = discord.Color.green()
        await interaction.message.edit(embed=embed, view=None)

        await interaction.response.send_message(f"✅ Order claimed by {interaction.user.mention}.", ephemeral=True)
        await ticket_ch.send(f"🔨 {interaction.user.mention} has claimed this build order. You can now coordinate.")


# ---------------------------------------------------------------------------
# Build Panel View & Dropdown & Custom Button
# ---------------------------------------------------------------------------
class BuildPanelView(discord.ui.View):
    def __init__(self, builds: list):
        super().__init__(timeout=None)
        
        if builds:
            options = [
                discord.SelectOption(
                    label=b["name"], 
                    description=f"Price: {b['price']}", 
                    value=b["id"],
                    emoji=b.get("emoji", "🧱")
                ) for b in builds
            ]
            self.add_item(BuildDropdown(options, builds))
            
        self.add_item(CustomBuildButton())


class BuildDropdown(discord.ui.Select):
    def __init__(self, options: list, builds: list):
        super().__init__(
            placeholder="Choose a build package...",
            min_values=1,
            max_values=1,
            options=options
        )
        self.builds = {b["id"]: b for b in builds}

    async def callback(self, interaction: discord.Interaction):
        build = self.builds.get(self.values[0])
        if not build:
            return await interaction.response.send_message("❌ Build not found.", ephemeral=True)
        modal = BuildOrderModal(build)
        await interaction.response.send_modal(modal)


class CustomBuildButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Custom Build",
            style=discord.ButtonStyle.success,
            custom_id="custom_build_btn",
            emoji="🪄"
        )
        self.custom_build_dict = {
            "id": "custom",
            "name": "Custom Build",
            "price": "Quote Pending",
            "emoji": "🪄"
        }

    async def callback(self, interaction: discord.Interaction):
        modal = BuildOrderModal(self.custom_build_dict)
        await interaction.response.send_modal(modal)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------
class Building(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Fix 1: Use cog_load instead of registering on_ready inside __init__
    # to avoid duplicate listeners on cog reload
    async def cog_load(self):
        # restore_panel_views needs the bot to be ready and db to be set.
        # Schedule it to run after on_ready fires instead of running it immediately.
        self.bot.loop.create_task(self._restore_when_ready())

    async def _restore_when_ready(self):
        await self.bot.wait_until_ready()
        if not hasattr(self.bot, 'db') or self.bot.db is None:
            print("❌ Building cog: db not available, skipping view restore")
            return
        await self.restore_panel_views()

    async def restore_panel_views(self):
        for doc in self.bot.db["building_panels"].find():
            guild_id = doc["guild_id"]
            builds = doc.get("builds", [])
            view = BuildPanelView(builds)
            self.bot.add_view(view)
            print(f"✅ Restored build panel view for guild {guild_id}")

        # Fix 2: Re-register PaymentView and ConfirmPaymentView for all open orders
        # so their buttons survive restarts
        for order in self.bot.db["building_orders"].find({"status": {"$in": ["unpaid", "confirmed", "claimed"]}}):
            guild = self.bot.get_guild(order["guild_id"])
            if not guild:
                continue

            cfg = self.bot.db["bot_config"].find_one({"guild_id": guild.id}) or {}
            confirmation_role_id = cfg.get("BUILD_TICKET_PING_ROLE_ID")
            confirmation_role = guild.get_role(confirmation_role_id) if confirmation_role_id else None

            if order["status"] == "unpaid":
                view = PaymentView(order["buyer_id"], order["ticket_channel_id"], confirmation_role)
                self.bot.add_view(view)
            elif order["status"] in ("confirmed", "claimed"):
                view = BuilderClaimView(order)
                self.bot.add_view(view)

        # Fix 3: Only iterate channels with active DB orders instead of all channels
        # to avoid slow boot on large servers
        active_channel_ids = set(
            doc["ticket_channel_id"]
            for doc in self.bot.db["building_orders"].find(
                {"status": {"$in": ["unpaid", "confirmed", "claimed"]}},
                {"ticket_channel_id": 1, "guild_id": 1}
            )
        )

        for guild in self.bot.guilds:
            cfg = self.bot.db["bot_config"].find_one({"guild_id": guild.id}) or {}
            trusted_staff_name = cfg.get("TRUSTED_STAFF_ROLE")
            trusted_staff = discord.utils.get(guild.roles, name=trusted_staff_name) if trusted_staff_name else None
            t1_role = guild.get_role(cfg.get("BUILDER_T1_ROLE_ID")) if cfg.get("BUILDER_T1_ROLE_ID") else None

            for channel in guild.text_channels:
                if channel.id not in active_channel_ids:
                    continue
                try:
                    if trusted_staff: await channel.set_permissions(trusted_staff, read_messages=True, send_messages=True)
                    if t1_role: await channel.set_permissions(t1_role, read_messages=True, send_messages=True)
                except discord.Forbidden:
                    pass

    @app_commands.command(name="buildpanel", description="Post/update the build ordering panel")
    @admin_only()
    async def buildpanel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)

        db = self.bot.db
        panel = db["building_panels"].find_one({"guild_id": interaction.guild.id})
        if not panel or not panel.get("builds"):
            return await interaction.edit_original_response(content="❌ No builds configured. Set them up in the dashboard first.")

        builds = panel["builds"]
        
        desc_lines = ["Select a build from the dropdown below to place your order.\n\n**Available Builds:**\n"]
        for b in builds:
            emoji = b.get("emoji", "🧱")
            desc_lines.append(f"{emoji} **{b['name']}** - `{b['price']}`")
        desc_lines.append(f"\n🪄 **Custom Build** - `Quote Pending` (Select the custom button)")
        
        embed = discord.Embed(
            title="🏗️ Build Orders",
            description="\n".join(desc_lines),
            color=0x5865F2
        )
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)

        original_msg = await interaction.original_response()
        async for msg in interaction.channel.history(limit=20):
            if msg.author == self.bot.user and msg.id != original_msg.id:
                try: await msg.delete()
                except discord.HTTPException: pass

        view = BuildPanelView(builds)
        await interaction.edit_original_response(content=None, embed=embed, view=view)

    # -----------------------------------------------------------------------
    # SLASH COMMANDS
    # -----------------------------------------------------------------------
    
    build_group = app_commands.Group(name="build", description="Manage build tickets", guild_only=True)

    @build_group.command(name="paid", description="Mark a build ticket as paid (bypasses button)")
    async def build_paid(self, interaction: discord.Interaction):
        if not has_cmd_perm(interaction, "build paid"):
            return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
        
        db = interaction.client.db
        order = db["building_orders"].find_one({"ticket_channel_id": interaction.channel.id})
        if not order:
            return await interaction.response.send_message("❌ This is not a valid build ticket channel.", ephemeral=True)
        if order["status"] != "unpaid":
            return await interaction.response.send_message("❌ This order is not awaiting payment.", ephemeral=True)

        buyer = interaction.guild.get_member(order["buyer_id"])
        if buyer:
            overwrites = interaction.channel.overwrites_for(buyer)
            overwrites.send_messages = True
            await interaction.channel.set_permissions(buyer, overwrite=overwrites)

        db["building_orders"].update_one({"ticket_channel_id": interaction.channel.id}, {"$set": {"status": "confirmed"}})
        
        embed = discord.Embed(title="✅ Payment Manually Confirmed", description="Order is now confirmed and buyer can speak.", color=0x2ecc71)
        await interaction.response.send_message(embed=embed)
        
        try:
            await post_order_to_builder_channel(interaction, interaction.channel.id)
        except Exception as e:
            print(f"Error posting to builder channel: {e}")

    @build_group.command(name="money", description="Set the money owed on a ticket")
    @app_commands.describe(amount="The new price/amount owed (e.g. '500k' or '$10')")
    async def build_money(self, interaction: discord.Interaction, amount: str):
        # Fix 4: command name matches the HTML key "build money" (was "build money set")
        if not has_cmd_perm(interaction, "build money"):
            return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
            
        db = interaction.client.db
        order = db["building_orders"].find_one({"ticket_channel_id": interaction.channel.id})
        if not order:
            return await interaction.response.send_message("❌ This is not a valid build ticket channel.", ephemeral=True)

        db["building_orders"].update_one({"ticket_channel_id": interaction.channel.id}, {"$set": {"price": amount}})
        await interaction.response.send_message(f"💰 Price updated to `{amount}` for this order.")

    @build_group.command(name="claim", description="Claim a build ticket for yourself")
    async def build_claim(self, interaction: discord.Interaction):
        if not has_cmd_perm(interaction, "build claim"):
            return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
            
        db = interaction.client.db
        order = db["building_orders"].find_one({"ticket_channel_id": interaction.channel.id})
        if not order:
            return await interaction.response.send_message("❌ This is not a valid build ticket channel.", ephemeral=True)
        if order.get("builder_id"):
            return await interaction.response.send_message("❌ This order is already claimed.", ephemeral=True)

        await interaction.channel.set_permissions(interaction.user, read_messages=True, send_messages=True)
        db["building_orders"].update_one({"ticket_channel_id": interaction.channel.id}, {"$set": {"builder_id": interaction.user.id, "status": "claimed"}})
        await interaction.response.send_message(f"🔨 {interaction.user.mention} has claimed this build order.")

    @build_group.command(name="complete", description="Mark a build ticket as completed")
    async def build_complete(self, interaction: discord.Interaction):
        if not has_cmd_perm(interaction, "build complete"):
            return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
            
        db = interaction.client.db
        order = db["building_orders"].find_one({"ticket_channel_id": interaction.channel.id})
        if not order:
            return await interaction.response.send_message("❌ This is not a valid build ticket channel.", ephemeral=True)

        db["building_orders"].update_one({"ticket_channel_id": interaction.channel.id}, {"$set": {"status": "completed"}})
        embed = discord.Embed(title="🎉 Build Completed", description="This order has been marked as completed. Closing in 5 seconds...", color=0x2ecc71)
        await interaction.response.send_message(embed=embed)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason="Build completed")
        except Exception: pass

    @build_group.command(name="cancel", description="Cancel and close a build ticket")
    async def build_cancel(self, interaction: discord.Interaction):
        if not has_cmd_perm(interaction, "build cancel"):
            return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
            
        db = interaction.client.db
        order = db["building_orders"].find_one({"ticket_channel_id": interaction.channel.id})
        if not order:
            return await interaction.response.send_message("❌ This is not a valid build ticket channel.", ephemeral=True)

        db["building_orders"].update_one({"ticket_channel_id": interaction.channel.id}, {"$set": {"status": "cancelled"}})
        await interaction.response.send_message("❌ Ticket cancelled. Closing in 3 seconds...")
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete(reason="Build cancelled")
        except Exception: pass

    @build_group.command(name="addnote", description="Add a staff note to the build ticket")
    @app_commands.describe(note="The note to add to the ticket logs")
    async def build_addnote(self, interaction: discord.Interaction, note: str):
        if not has_cmd_perm(interaction, "build addnote"):
            return await interaction.response.send_message("❌ You do not have permission to use this command.", ephemeral=True)
            
        db = interaction.client.db
        order = db["building_orders"].find_one({"ticket_channel_id": interaction.channel.id})
        if not order:
            return await interaction.response.send_message("❌ This is not a valid build ticket channel.", ephemeral=True)

        note_doc = {
            "author": interaction.user.display_name,
            "content": note,
            "at": datetime.now(timezone.utc)
        }
        db["building_orders"].update_one({"ticket_channel_id": interaction.channel.id}, {"$push": {"notes": note_doc}})
        
        embed = discord.Embed(title="📝 Note Added", description=note, color=0x5865F2, timestamp=note_doc["at"])
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        cfg = self.bot.db["bot_config"].find_one({"guild_id": after.guild.id}) or {}
        t1_role_id = cfg.get("BUILDER_T1_ROLE_ID")
        t1_role = after.guild.get_role(t1_role_id) if t1_role_id else None
        trusted_staff_name = cfg.get("TRUSTED_STAFF_ROLE")
        trusted_staff = discord.utils.get(after.guild.roles, name=trusted_staff_name) if trusted_staff_name else None

        gained_t1 = t1_role and t1_role in after.roles and t1_role not in before.roles
        gained_trusted = trusted_staff and trusted_staff in after.roles and trusted_staff not in before.roles

        if gained_t1 or gained_trusted:
            for ch in after.guild.text_channels:
                if ch.name.startswith("build-"):
                    try: await ch.set_permissions(after, read_messages=True, send_messages=True)
                    except Exception: pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Building(bot))