import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
from cogs.config import TRUSTED_STAFF_ROLE

# ---------------------------------------------------------------------------
# Application Views
# ---------------------------------------------------------------------------

class ApplyButton(discord.ui.Button):
    def __init__(self, app_id: str, app_name: str):
        super().__init__(
            label=f"Apply for {app_name}",
            style=discord.ButtonStyle.primary,
            custom_id=f"apply_{app_id}",
            emoji="📝"
        )
        self.app_id = app_id
        self.app_name = app_name

    async def callback(self, interaction: discord.Interaction):
        app_config = interaction.client.db["applications_config"].find_one({"guild_id": interaction.guild.id, "app_id": self.app_id})
        
        if not app_config or not app_config.get("is_open", False):
            return await interaction.response.send_message("❌ This application is closed right now.", ephemeral=True)

        try:
            dm_channel = await interaction.user.create_dm()
            start_view = StartAppView(self.app_id, self.app_name, app_config.get("questions", []))
            await dm_channel.send(f"**{self.app_name}**\nClick the button below to start your application.", view=start_view)
            await interaction.response.send_message("✅ Check your DMs to start the application!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I couldn't DM you! Please enable DMs from server members.", ephemeral=True)

class ApplyPanelView(discord.ui.View):
    def __init__(self, app_id: str, app_name: str):
        super().__init__(timeout=None)
        self.add_item(ApplyButton(app_id, app_name))

class StartAppView(discord.ui.View):
    def __init__(self, app_id: str, app_name: str, questions: list):
        super().__init__(timeout=None)
        self.app_id = app_id
        self.app_name = app_name
        self.questions = questions

        btn = discord.ui.Button(label="Start Application", style=discord.ButtonStyle.green, custom_id=f"start_{app_id}", emoji="✍️")
        btn.callback = self.start_callback
        self.add_item(btn)

    async def start_callback(self, interaction: discord.Interaction):
        modal = ApplicationModal(self.app_id, self.app_name, self.questions)
        await interaction.response.send_modal(modal)

class ApplicationModal(discord.ui.Modal):
    def __init__(self, app_id: str, app_name: str, questions: list):
        super().__init__(title=f"{app_name} Application")
        self.app_id = app_id
        self.app_name = app_name
        
        for i, q in enumerate(questions[:5]):
            setattr(self, f"q{i+1}", discord.ui.TextInput(label=q[:45], style=discord.TextStyle.paragraph, required=True))
            self.add_item(getattr(self, f"q{i+1}"))

    async def on_submit(self, interaction: discord.Interaction):
        app_config = interaction.client.db["applications_config"].find_one({"app_id": self.app_id})
        if not app_config: return await interaction.response.send_message("❌ Error finding application.", ephemeral=True)

        submitted_channel = interaction.client.get_channel(app_config.get("submitted_channel_id"))
        if not submitted_channel: return await interaction.response.send_message("❌ Submission channel not found.", ephemeral=True)

        embed = discord.Embed(title=f"📄 New {self.app_name} Application", color=0x2b2d31, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="Applicant", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        questions = app_config.get("questions", [])
        for i, q in enumerate(questions[:5]):
            answer = getattr(self, f"q{i+1}", None)
            if answer:
                val = answer.value
                if len(val) > 1024: val = val[:1021] + "..."
                embed.add_field(name=q[:45], value=val, inline=False)

        view = ApplicationActionView(self.app_id, interaction.user.id, app_config)
        await submitted_channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Application submitted successfully!", ephemeral=True)

class ApplicationActionView(discord.ui.View):
    def __init__(self, app_id: str, applicant_id: int, app_config: dict):
        super().__init__(timeout=None)
        self.app_id = app_id
        self.applicant_id = applicant_id
        self.app_config = app_config

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.green, custom_id="app_accept")
    async def accept_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Admins only.", ephemeral=True)

        accepted_ch = interaction.client.get_channel(self.app_config.get("accepted_channel_id"))
        if accepted_ch:
            new_embed = interaction.message.embeds[0]
            new_embed.color = discord.Color.green()
            new_embed.title = f"✅ Accepted {self.app_config.get('app_name')} Application"
            new_embed.add_field(name="Accepted By", value=interaction.user.mention, inline=False)
            await accepted_ch.send(embed=new_embed)

        try:
            user = await interaction.client.fetch_user(self.applicant_id)
            await user.send(f"🎉 Congratulations! Your **{self.app_config.get('app_name')}** application has been accepted!")
        except: pass

        await interaction.message.edit(view=None, content="✅ Application Accepted.")
        await interaction.response.defer()

    @discord.ui.button(label="❌ Deny", style=discord.ButtonStyle.red, custom_id="app_deny")
    async def deny_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Admins only.", ephemeral=True)

        denied_ch = interaction.client.get_channel(self.app_config.get("denied_channel_id"))
        if denied_ch:
            new_embed = interaction.message.embeds[0]
            new_embed.color = discord.Color.red()
            new_embed.title = f"❌ Denied {self.app_config.get('app_name')} Application"
            new_embed.add_field(name="Denied By", value=interaction.user.mention, inline=False)
            await denied_ch.send(embed=new_embed)

        try:
            user = await interaction.client.fetch_user(self.applicant_id)
            await user.send(f"❌ Your **{self.app_config.get('app_name')}** application has been denied.")
        except: pass

        await interaction.message.edit(view=None, content="❌ Application Denied.")
        await interaction.response.defer()

    @discord.ui.button(label="🎫 Open Ticket", style=discord.ButtonStyle.grey, custom_id="app_ticket")
    async def ticket_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Admins only.", ephemeral=True)

        guild = interaction.guild
        applicant = guild.get_member(self.applicant_id) or await guild.fetch_member(self.applicant_id)
        uname = applicant.name.lower()

        cat = discord.utils.get(guild.categories, name="Application Tickets")
        if not cat:
            cat = await guild.create_category("Application Tickets")
            await cat.set_permissions(guild.default_role, read_messages=False)

        trusted_role = discord.utils.get(guild.roles, name=TRUSTED_STAFF_ROLE)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            applicant: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True, attach_files=True),
        }
        if trusted_role:
            overwrites[trusted_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True, attach_files=True)

        channel = await guild.create_text_channel(name=f"app-{uname}", category=cat, overwrites=overwrites, topic=f"Ticket by {applicant.name} | Application")

        from cogs.tickets_base import TicketView
        embed = discord.Embed(title="🎫 Application Ticket", description=f"### Discussion with {applicant.mention}\n\n━━━━━━━━━━━━━━━━━━", color=0x2b2d31, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="Applicant", value=applicant.mention, inline=True)
        embed.add_field(name="Category", value="Application", inline=True)
        embed.set_footer(text=f"Channel ID: {channel.id}")

        view = TicketView()
        await channel.send(embed=embed, view=view)

        button.disabled = True
        button.label = "Ticket Opened"
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"✅ Ticket created: {channel.mention}", ephemeral=True)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class Applications(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # --- CRITICAL: Load buttons from DB so clicks don't fail ---
        try:
            for app in bot.db["applications_config"].find():
                bot.add_view(ApplyPanelView(app["app_id"], app["app_name"]))
            print("✅ Loaded Application Panel views.")
        except Exception as e:
            print(f"❌ Failed to load application views: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Applications(bot))