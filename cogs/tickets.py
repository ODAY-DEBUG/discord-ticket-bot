class CategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="🎫 Select a category...", description="Choose from below", emoji="📋", default=True),
            discord.SelectOption(label="🏠 Base Buying", description="Purchase a base", emoji="🏠"),
            discord.SelectOption(label="🕳️ Bedrock Hole", description="Buy a bedrock hole", emoji="🕳️"),
            discord.SelectOption(label="🔄 Spawner Trade", description="Buy/sell spawners", emoji="🔄"),
            discord.SelectOption(label="🏗️ Building", description="Building services", emoji="🏗️"),
            discord.SelectOption(label="❓ Support", description="General help", emoji="❓"),
            discord.SelectOption(label="⚠️ Scam Report", description="Report a scam", emoji="⚠️"),
        ]
        super().__init__(placeholder="Choose a category...", options=options, custom_id="cat_select_v10")
    
    async def callback(self, interaction: discord.Interaction):
        # If the default option is selected, just reset and do nothing
        if self.values[0] == "🎫 Select a category...":
            await interaction.response.defer()
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Check existing tickets
        for ch in interaction.guild.channels:
            if ch.name.endswith(f"-{interaction.user.name.lower()}") and (
                ch.name.startswith("ticket-") or ch.name.startswith("claimed-")
            ):
                await interaction.followup.send(f"❌ You already have a ticket: {ch.mention}", ephemeral=True)
                return
        
        # Map labels to full names
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
                "discord_category": "🏠 Base Buying",
                "ping_roles": [STAFF_ROLE, BASE_BUYING_ROLE],
                "allowed_roles": [STAFF_ROLE, BASE_BUYING_ROLE],
                "color": 0x2ecc71,
                "emoji": "🏠",
                "questions": [
                    "**What type of base are you looking for?**",
                    "**What is your budget?**",
                    "**Any specific requirements?**"
                ]
            },
            "Bedrock Hole Buying": {
                "discord_category": "🕳️ Bedrock Holes",
                "ping_roles": [STAFF_ROLE, BEDROCK_ROLE],
                "allowed_roles": [STAFF_ROLE, BEDROCK_ROLE],
                "color": 0x95a5a6,
                "emoji": "🕳️",
                "questions": [
                    "**What size bedrock hole?**",
                    "**What is your budget?**",
                    "**Location requirements?**"
                ]
            },
            "Spawner Trading": {
                "discord_category": "🔄 Spawner Trading",
                "ping_roles": [STAFF_ROLE, SPAWNER_ROLE],
                "allowed_roles": [STAFF_ROLE, SPAWNER_ROLE],
                "color": 0xf1c40f,
                "emoji": "🔄",
                "questions": [
                    "**Buying or selling?**",
                    "**What type of spawners?**",
                    "**How many and what price?**"
                ]
            },
            "Building": {
                "discord_category": "🏗️ Building",
                "ping_roles": [BUILDING_ROLE],
                "allowed_roles": [STAFF_ROLE, BUILDING_ROLE],
                "color": 0x9b59b6,
                "emoji": "🏗️",
                "questions": [
                    "**What do you need built?**",
                    "**What is your budget?**",
                    "**Do you have a deadline?**"
                ]
            },
            "General Support": {
                "discord_category": "❓ General Support",
                "ping_roles": [STAFF_ROLE],
                "allowed_roles": [STAFF_ROLE],
                "color": 0x3498db,
                "emoji": "❓",
                "questions": [
                    "**What do you need help with?**",
                    "**Please provide as much detail as possible**"
                ]
            },
            "Scam Report": {
                "discord_category": "⚠️ Scam Reports",
                "ping_roles": [STAFF_ROLE],
                "allowed_roles": [STAFF_ROLE],
                "color": 0xe74c3c,
                "emoji": "⚠️",
                "questions": [
                    "**Who scammed you?** (Username + ID)",
                    "**What were you trading/buying?**",
                    "**Do you have proof?** (Screenshots)"
                ]
            }
        }
        
        cfg = configs[category]
        
        # Get or create Discord category
        dc_cat = discord.utils.get(interaction.guild.categories, name=cfg["discord_category"])
        if not dc_cat:
            dc_cat = await interaction.guild.create_category(cfg["discord_category"])
            await dc_cat.set_permissions(interaction.guild.default_role, read_messages=False)
        
        # Permissions
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True, attach_files=True)
        }
        
        for role_name in cfg["allowed_roles"]:
            role = discord.utils.get(interaction.guild.roles, name=role_name)
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True, attach_files=True)
        
        # Create channel
        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.name.lower()}",
            category=dc_cat,
            overwrites=overwrites,
            topic=f"🎫 {category} | Created by {interaction.user.name}"
        )
        
        # Beautiful embed
        embed = discord.Embed(
            title=f"{cfg['emoji']} {category} Ticket",
            description=f"### Welcome {interaction.user.mention}!\n\n"
                       f"Thank you for creating a ticket. Please answer the questions below.\n\n"
                       f"━━━━━━━━━━━━━━━━━━━━━━━",
            color=cfg["color"],
            timestamp=datetime.utcnow()
        )
        
        for i, q in enumerate(cfg["questions"], 1):
            embed.add_field(name=f"📋 Question {i}", value=q, inline=False)
        
        embed.add_field(name="\u200b", value="━━━━━━━━━━━━━━━━━━━━━━━", inline=False)
        embed.add_field(name="👤 Created By", value=interaction.user.mention, inline=True)
        embed.add_field(name="📂 Category", value=category, inline=True)
        embed.set_footer(text=f"Ticket ID: {channel.id}")
        
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        
        # Send embed with buttons
        view = TicketView()
        await channel.send(embed=embed, view=view)
        
        # PING ROLES - Normal message so pings work
        ping_message = ""
        for role_name in cfg["ping_roles"]:
            role = discord.utils.get(interaction.guild.roles, name=role_name)
            if role:
                ping_message += f"{role.mention} "
        
        if ping_message:
            await channel.send(f"{ping_message}\n📩 **New {category} ticket** from {interaction.user.mention}!")
        
        await interaction.followup.send(f"✅ Ticket created: {channel.mention}", ephemeral=True)