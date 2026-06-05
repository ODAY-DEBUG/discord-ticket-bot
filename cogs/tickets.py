import discord
from discord.ext import commands
import asyncio

# ================= CONFIG =================
STAFF_ROLE = "Staff"
BASE_BUYING_ROLE = "Base Seller"
BEDROCK_ROLE = "Bedrock Seller"
SPAWNER_ROLE = "Spawner Trader"
BUILDING_ROLE = "Builder"
# =========================================


# ================= HELPERS =================
def get_role(guild, name):
    return discord.utils.get(guild.roles, name=name)


def user_has_role(member, role_names):
    return any(get_role(member.guild, r) in member.roles for r in role_names)


def make_ticket_name(user_id: int):
    return f"ticket-{user_id}"


def make_claimed_name(user_id: int):
    return f"claimed-{user_id}"
# ==========================================


# ================= TICKET VIEW =================
class TicketView(discord.ui.View):
    def __init__(self, allowed_roles):
        super().__init__(timeout=None)
        self.allowed_roles = allowed_roles

    # -------- CLOSE --------
    @discord.ui.button(
        label="Close",
        style=discord.ButtonStyle.red,
        custom_id="ticket_close_v2"
    )
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Closing ticket in 5 seconds...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

    # -------- CLAIM --------
    @discord.ui.button(
        label="Claim",
        style=discord.ButtonStyle.green,
        custom_id="ticket_claim_v2"
    )
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):

        # permission check
        if not any(get_role(interaction.guild, r) in interaction.user.roles for r in self.allowed_roles):
            await interaction.response.send_message("No permission to claim this ticket.", ephemeral=True)
            return

        # already claimed
        if interaction.channel.topic and "claimed_by=" in interaction.channel.topic:
            await interaction.response.send_message("Already claimed.", ephemeral=True)
            return

        # set claim
        new_topic = f"{interaction.channel.topic or ''} | claimed_by={interaction.user.id}"
        await interaction.channel.edit(
            name=f"claimed-{interaction.user.id}",
            topic=new_topic
        )

        await interaction.response.send_message(
            f"Ticket claimed by {interaction.user.mention}"
        )

    # -------- UNCLAIM --------
    @discord.ui.button(
        label="Unclaim",
        style=discord.ButtonStyle.gray,
        custom_id="ticket_unclaim_v2"
    )
    async def unclaim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):

        topic = interaction.channel.topic or ""

        if "claimed_by=" not in topic:
            await interaction.response.send_message("This ticket is not claimed.", ephemeral=True)
            return

        claimed_id = topic.split("claimed_by=")[-1].split()[0]

        staff_role = get_role(interaction.guild, STAFF_ROLE)
        is_staff = staff_role in interaction.user.roles

        is_claimer = str(interaction.user.id) == claimed_id

        if not is_staff and not is_claimer:
            await interaction.response.send_message(
                "Only the claimer or staff can unclaim this ticket.",
                ephemeral=True
            )
            return

        # restore ticket
        base_topic = topic.replace(f"claimed_by={claimed_id}", "").strip()

        await interaction.channel.edit(
            name=f"ticket-{claimed_id}",
            topic=base_topic
        )

        await interaction.response.send_message("Ticket unclaimed.")
# ===============================================


# ================= CATEGORY SELECT =================
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

        super().__init__(
            placeholder="Select ticket category...",
            options=options,
            custom_id="ticket_select_v2"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id

        # prevent duplicates
        for ch in interaction.guild.channels:
            if ch.name == f"ticket-{user_id}" or ch.name == f"claimed-{user_id}":
                await interaction.followup.send(
                    f"You already have a ticket: {ch.mention}",
                    ephemeral=True
                )
                return

        configs = {
            "General Support": {
                "cat": "General Support",
                "ping": [STAFF_ROLE],
                "claim": [STAFF_ROLE],
                "color": discord.Color.blue()
            },
            "Base Buying": {
                "cat": "Base Buying",
                "ping": [STAFF_ROLE, BASE_BUYING_ROLE],
                "claim": [STAFF_ROLE, BASE_BUYING_ROLE],
                "color": discord.Color.green()
            },
            "Bedrock Hole Buying": {
                "cat": "Bedrock Holes",
                "ping": [STAFF_ROLE, BEDROCK_ROLE],
                "claim": [STAFF_ROLE, BEDROCK_ROLE],
                "color": discord.Color.dark_gray()
            },
            "Spawner Trading": {
                "cat": "Spawner Trading",
                "ping": [STAFF_ROLE, SPAWNER_ROLE],
                "claim": [STAFF_ROLE, SPAWNER_ROLE],
                "color": discord.Color.gold()
            },
            "Building": {
                "cat": "Building",
                "ping": [STAFF_ROLE, BUILDING_ROLE],
                "claim": [STAFF_ROLE, BUILDING_ROLE],
                "color": discord.Color.purple()
            },
            "Scam Report": {
                "cat": "Scam Reports",
                "ping": [STAFF_ROLE],
                "claim": [STAFF_ROLE],
                "color": discord.Color.red()
            },
        }

        cfg = configs[self.values[0]]

        # category
        category = discord.utils.get(interaction.guild.categories, name=cfg["cat"])
        if not category:
            category = await interaction.guild.create_category(cfg["cat"])
            await category.set_permissions(interaction.guild.default_role, read_messages=False)

        # permissions
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        for rname in cfg["claim"]:
            role = get_role(interaction.guild, rname)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True
                )

        # create ticket
        ch = await interaction.guild.create_text_channel(
            name=f"ticket-{user_id}",
            category=category,
            overwrites=overwrites,
            topic=f"Ticket by {interaction.user.id} | category={self.values[0]}"
        )

        embed = discord.Embed(
            title=f"{self.values[0]} Ticket",
            description=f"Welcome {interaction.user.mention}",
            color=cfg["color"]
        )

        view = TicketView(cfg["claim"])
        await ch.send(embed=embed, view=view)

        # ping roles
        ping_msg = ""
        for rname in cfg["ping"]:
            role = get_role(interaction.guild, rname)
            if role:
                ping_msg += role.mention + " "

        if ping_msg:
            await ch.send(f"{ping_msg}New ticket created!")

        await interaction.followup.send(f"Ticket created: {ch.mention}", ephemeral=True)
# ===============================================


# ================= COG =================
class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ticketpanel")
    @commands.has_permissions(administrator=True)
    async def ticketpanel(self, ctx):
        await ctx.channel.purge(limit=10, check=lambda m: m.author == self.bot.user)

        embed = discord.Embed(
            title="Support Tickets",
            description="Select a category below:",
            color=discord.Color.blue()
        )

        view = discord.ui.View(timeout=None)
        view.add_item(CategorySelect())

        await ctx.send(embed=embed, view=view)


# ================= SETUP =================
async def setup(bot):
    await bot.add_cog(Tickets(bot))