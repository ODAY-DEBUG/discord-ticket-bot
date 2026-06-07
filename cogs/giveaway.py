import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
import random
from typing import Optional, List

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GIVEAWAYS_FILE = "giveaways.json"
STAFF_ROLE = "Staff"

# ---------------------------------------------------------------------------
# Data persistence
# ---------------------------------------------------------------------------

class GiveawayData:
    def __init__(self):
        self.active_giveaways = {}
        self.load_data()
    
    def load_data(self):
        if os.path.exists(GIVEAWAYS_FILE):
            try:
                with open(GIVEAWAYS_FILE, 'r') as f:
                    data = json.load(f)
                    for msg_id, giveaway_data in data.items():
                        giveaway = Giveaway.from_dict(giveaway_data)
                        self.active_giveaways[int(msg_id)] = giveaway
                print(f"✅ Loaded {len(self.active_giveaways)} active giveaways")
            except Exception as e:
                print(f"❌ Failed to load giveaways: {e}")
    
    def save_data(self):
        try:
            data = {}
            for msg_id, giveaway in self.active_giveaways.items():
                data[str(msg_id)] = giveaway.to_dict()
            with open(GIVEAWAYS_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"❌ Failed to save giveaways: {e}")
    
    def add_giveaway(self, message_id: int, giveaway):
        self.active_giveaways[message_id] = giveaway
        self.save_data()
    
    def remove_giveaway(self, message_id: int):
        if message_id in self.active_giveaways:
            del self.active_giveaways[message_id]
            self.save_data()


class Giveaway:
    def __init__(self, channel_id: int, end_time: datetime, prize: str, 
                 winners_count: int, title: str, description: str,
                 host_id: int, message_id: int = None, claim_time_seconds: int = 600):
        self.channel_id = channel_id
        self.end_time = end_time
        self.prize = prize
        self.winners_count = winners_count
        self.title = title
        self.description = description
        self.host_id = host_id
        self.message_id = message_id
        self.claim_time_seconds = claim_time_seconds
        self.entries = []
        self.ended = False
    
    def to_dict(self):
        return {
            'channel_id': self.channel_id,
            'end_time': self.end_time.isoformat(),
            'prize': self.prize,
            'winners_count': self.winners_count,
            'title': self.title,
            'description': self.description,
            'host_id': self.host_id,
            'message_id': self.message_id,
            'entries': self.entries,
            'ended': self.ended,
            'claim_time_seconds': self.claim_time_seconds
        }
    
    @classmethod
    def from_dict(cls, data):
        giveaway = cls(
            channel_id=data['channel_id'],
            end_time=datetime.fromisoformat(data['end_time']),
            prize=data['prize'],
            winners_count=data['winners_count'],
            title=data['title'],
            description=data['description'],
            host_id=data['host_id'],
            message_id=data.get('message_id')
        )
        giveaway.entries = data.get('entries', [])
        giveaway.ended = data.get('ended', False)
        giveaway.claim_time_seconds = data.get('claim_time_seconds', 600)
        return giveaway
    
    def add_entry(self, user_id: int):
        if user_id not in self.entries:
            self.entries.append(user_id)
            return True
        return False
    
    def pick_winners(self) -> List[int]:
        if not self.entries:
            return []
        unique_entries = list(set(self.entries))
        if len(unique_entries) <= self.winners_count:
            return unique_entries
        return random.sample(unique_entries, self.winners_count)


# ---------------------------------------------------------------------------
# Winner Claim View
# ---------------------------------------------------------------------------

class WinnerClaimView(discord.ui.View):
    def __init__(
        self,
        winners: List[int],
        prize: str,
        giveaway_channel_id: int,
        giveaway_message_id: int,
        claim_time_seconds: int = 600
    ):
        super().__init__(timeout=claim_time_seconds)

        self.winners = winners
        self.prize = prize
        self.giveaway_channel_id = giveaway_channel_id
        self.giveaway_message_id = giveaway_message_id
        self.claimed_users = set()
        self.message = None

    @discord.ui.button(
        label="🎁 Claim Prize",
        style=discord.ButtonStyle.green,
        custom_id="claim_prize"
    )
    async def claim_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if interaction.user.id not in self.winners:
            await interaction.response.send_message(
                "❌ You are not one of the giveaway winners!",
                ephemeral=True
            )
            return

        if interaction.user.id in self.claimed_users:
            await interaction.response.send_message(
                "❌ You already claimed your prize!",
                ephemeral=True
            )
            return

        await self.create_claim_ticket(
            interaction,
            interaction.user.id
        )

    async def create_claim_ticket(self, interaction, winner_id):
        guild = interaction.guild
        uname = interaction.user.name.lower()

        # Check for existing claim ticket
        for channel in guild.text_channels:
            if channel.name == f"claim-{uname}":
                await interaction.response.send_message(
                    f"❌ You already have an open claim ticket: {channel.mention}",
                    ephemeral=True
                )
                return

        # ── Same format as tickets.py ──────────────────────────────────
        claim_category = discord.utils.get(guild.categories, name="Claim Tickets")
        if not claim_category:
            claim_category = await guild.create_category("Claim Tickets")
            await claim_category.set_permissions(
                guild.default_role, read_messages=False
            )

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                read_messages=False
            ),
            interaction.user: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
            ),
        }

        staff_role = discord.utils.get(guild.roles, name=STAFF_ROLE)
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
            )

        ticket = await guild.create_text_channel(
            name=f"claim-{uname}",
            category=claim_category,
            overwrites=overwrites,
            topic=f"Ticket by {interaction.user.name} | Prize Claim",
        )

        # Embed styled like tickets.py
        embed = discord.Embed(
            title="🎉 Prize Claim",
            description=(
                f"### Welcome {interaction.user.mention}!\n\n"
                f"**Prize:** {self.prize}\n\n"
                f"Please wait for staff to process your claim.\n\n"
                f"━━━━━━━━━━━━━━━━━━"
            ),
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Claimed By", value=interaction.user.mention, inline=True)
        embed.add_field(name="Category",   value="Prize Claim",            inline=True)
        embed.set_footer(text=f"Channel ID: {ticket.id}")
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        # TicketView gives Request Close + Close Ticket buttons
        from cogs.tickets import TicketView
        view = TicketView()
        await ticket.send(embed=embed, view=view)

        # ── Proof link to original giveaway message ──
        giveaway_link = f"https://discord.com/channels/{guild.id}/{self.giveaway_channel_id}/{self.giveaway_message_id}"
        await ticket.send(
            f"🔗 **Click here to see proof / original giveaway:** [Giveaway Message]({giveaway_link})"
        )

        # Ping staff
        if staff_role:
            await ticket.send(
                f"{staff_role.mention} New giveaway prize claim from "
                f"{interaction.user.mention}!"
            )

        self.claimed_users.add(winner_id)

        await interaction.response.send_message(
            f"✅ Claim ticket created: {ticket.mention}",
            ephemeral=True
        )

    async def on_timeout(self):
        """Fires after claim_time_seconds — removes the Claim Prize button."""
        if not self.message:
            return

        try:
            embed = self.message.embeds[0]
            embed.description = (
                embed.description +
                "\n\n⏰ Claim period has expired."
            )
            embed.color = discord.Color.red()
            # view=None removes the button from the message
            await self.message.edit(embed=embed, view=None)
        except Exception as e:
            print(f"Claim timeout error: {e}")


class GiveawayButton(discord.ui.Button):
    def __init__(self, giveaway_data: GiveawayData, giveaway: Giveaway):
        super().__init__(label="🎉 Enter Giveaway", style=discord.ButtonStyle.primary, custom_id=f"enter_{giveaway.message_id}")
        self.giveaway_data = giveaway_data
        self.giveaway = giveaway
    
    async def callback(self, interaction: discord.Interaction):
        if self.giveaway.ended:
            await interaction.response.send_message("❌ This giveaway has already ended!", ephemeral=True)
            return
        
        if datetime.now(timezone.utc) > self.giveaway.end_time:
            await interaction.response.send_message("❌ This giveaway has already ended!", ephemeral=True)
            return
        
        if self.giveaway.add_entry(interaction.user.id):
            self.giveaway_data.save_data()
            await interaction.response.send_message("✅ You have entered the giveaway! Good luck! 🎉", ephemeral=True)
            try:
                channel = interaction.client.get_channel(self.giveaway.channel_id)
                if channel:
                    msg = await channel.fetch_message(self.giveaway.message_id)
                    if msg.embeds:
                        embed = msg.embeds[0]
                        fields = [(f.name, f.value, f.inline) for f in embed.fields]
                        embed.clear_fields()
                        for name, value, inline in fields:
                            if name == "📊 Total Entries":
                                embed.add_field(name="📊 Total Entries", value=str(len(self.giveaway.entries)), inline=inline)
                            else:
                                embed.add_field(name=name, value=value, inline=inline)
                        await msg.edit(embed=embed)
            except Exception as e:
                print(f"Failed to update entry count: {e}")
        else:
            await interaction.response.send_message("❌ You have already entered this giveaway!", ephemeral=True)


class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_data: GiveawayData, giveaway: Giveaway):
        super().__init__(timeout=None)
        self.add_item(GiveawayButton(giveaway_data, giveaway))


# ---------------------------------------------------------------------------
# Giveaway Cog
# ---------------------------------------------------------------------------

class Giveaways(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.giveaway_data = GiveawayData()
        self.check_giveaways.start()
    
    def cog_unload(self):
        self.check_giveaways.cancel()
    
    @tasks.loop(seconds=30)
    async def check_giveaways(self):
        now = datetime.now(timezone.utc)
        ended_giveaways = []
        
        for msg_id, giveaway in self.giveaway_data.active_giveaways.items():
            if not giveaway.ended and now >= giveaway.end_time:
                ended_giveaways.append((msg_id, giveaway))
        
        for msg_id, giveaway in ended_giveaways:
            await self.end_giveaway(msg_id, giveaway)
    
    async def end_giveaway(self, message_id: int, giveaway: Giveaway):
        giveaway.ended = True
        
        channel = self.bot.get_channel(giveaway.channel_id)
        if not channel:
            print(f"Channel not found for giveaway {message_id}")
            self.giveaway_data.remove_giveaway(message_id)
            return
        
        try:
            original_msg = await channel.fetch_message(message_id)
        except:
            print(f"Original message not found for giveaway {message_id}")
            self.giveaway_data.remove_giveaway(message_id)
            return
        
        winners = giveaway.pick_winners()
        
        results_embed = discord.Embed(
            title=f"🎉 {giveaway.title} - GIVEAWAY ENDED 🎉",
            description=f"{giveaway.description}\n\n**Prize:** {giveaway.prize}",
            color=0xff0000,
            timestamp=datetime.now(timezone.utc)
        )
        
        if winners:
            winner_mentions = [f"<@{w}>" for w in winners]
            results_embed.add_field(
                name=f"🏆 Winners ({len(winners)})",
                value=", ".join(winner_mentions),
                inline=False
            )
            
            await original_msg.edit(embed=results_embed, view=None)
            
            announcement_embed = discord.Embed(
                title="🎉 Giveaway Winners Announced! 🎉",
                description=f"**Giveaway:** {giveaway.title}\n"
                           f"**Prize:** {giveaway.prize}\n\n"
                           f"**Winners:** {', '.join(winner_mentions)}\n\n"
                           f"📝 Click the **Claim Prize** button below to claim your prize!",
                color=0x00ff00,
                timestamp=datetime.now(timezone.utc)
            )
            announcement_embed.set_footer(text="Prize claim is open.")

            claim_view = WinnerClaimView(
                winners, giveaway.prize,
                giveaway.channel_id, message_id,
                giveaway.claim_time_seconds
            )

            announcement_msg = await channel.send(
                content=" ".join(winner_mentions),
                embed=announcement_embed,
                view=claim_view
            )
            claim_view.message = announcement_msg
            
            for winner_id in winners:
                try:
                    user = await self.bot.fetch_user(winner_id)
                    dm_embed = discord.Embed(
                        title="🎉 Congratulations! You won a giveaway! 🎉",
                        description=f"You won **{giveaway.prize}** in **{giveaway.title}**!\n\n"
                                   f"Please go to {channel.mention} and click the "
                                   f"**Claim Prize** button to claim your prize.",
                        color=0x00ff00
                    )
                    await user.send(embed=dm_embed)
                except:
                    pass
        
        else:
            results_embed.add_field(
                name="❌ No Winners",
                value="No one entered this giveaway!",
                inline=False
            )
            await original_msg.edit(embed=results_embed, view=None)
        
        self.giveaway_data.remove_giveaway(message_id)
    
    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    
    @app_commands.command(name="giveaway", description="Create a new giveaway (Admin only)")
    @app_commands.describe(
        channel="Channel to post the giveaway",
        title="Title of the giveaway",
        description="Description of the giveaway",
        prize="What users can win",
        winners="Number of winners",
        duration_minutes="Minutes until giveaway ends",
        duration_seconds="Seconds until giveaway ends",
        claim_time_minutes="Minutes winners have to claim their prize (default 10)",
        claim_time_seconds="Extra seconds for claim time (default 0)"
    )
    async def create_giveaway(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str,
        description: str,
        prize: str,
        winners: int = 1,
        duration_minutes: int = 0,
        duration_seconds: int = 0,
        claim_time_minutes: int = 10,
        claim_time_seconds: int = 0,
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Admin only command!", ephemeral=True)
            return
        
        total_seconds = (duration_minutes * 60) + duration_seconds
        if total_seconds <= 0:
            await interaction.response.send_message("❌ Please specify a duration greater than 0!", ephemeral=True)
            return
        
        end_time = datetime.now(timezone.utc) + timedelta(seconds=total_seconds)
        
        if winners < 1 or winners > 25:
            await interaction.response.send_message("❌ Winners must be between 1 and 25!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"🎉 {title} 🎉",
            description=description,
            color=0x00ff00,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="🎁 Prize", value=prize, inline=False)
        embed.add_field(name="👑 Winners", value=str(winners), inline=True)
        
        end_timestamp = int(end_time.timestamp())
        embed.add_field(name="⏰ Ends", value=f"<t:{end_timestamp}:F> (<t:{end_timestamp}:R>)", inline=True)
        
        embed.add_field(name="📊 Total Entries", value="0", inline=False)
        embed.set_footer(text=f"Hosted by {interaction.user.name}", icon_url=interaction.user.display_avatar.url)
        
        total_claim_seconds = (claim_time_minutes * 60) + claim_time_seconds
        if total_claim_seconds < 30:
            await interaction.response.send_message("❌ Claim time must be at least 30 seconds!", ephemeral=True)
            return

        giveaway = Giveaway(
            channel_id=channel.id,
            end_time=end_time,
            prize=prize,
            winners_count=winners,
            title=title,
            description=description,
            host_id=interaction.user.id,
            claim_time_seconds=total_claim_seconds
        )
        
        await interaction.response.send_message("✅ Creating giveaway...", ephemeral=True)
        
        view = GiveawayView(self.giveaway_data, giveaway)
        message = await channel.send(embed=embed, view=view)
        
        giveaway.message_id = message.id
        self.giveaway_data.add_giveaway(message.id, giveaway)
        
        await interaction.edit_original_response(content=f"✅ Giveaway created in {channel.mention}!")
    
    @app_commands.command(name="endgiveaway", description="Force end a giveaway early (Admin only)")
    @app_commands.describe(message_id="The message ID of the giveaway")
    async def end_giveaway_early(self, interaction: discord.Interaction, message_id: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Admin only command!", ephemeral=True)
            return
        
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.response.send_message("❌ Invalid message ID!", ephemeral=True)
            return
        
        if msg_id not in self.giveaway_data.active_giveaways:
            await interaction.response.send_message("❌ Giveaway not found or already ended!", ephemeral=True)
            return
        
        giveaway = self.giveaway_data.active_giveaways[msg_id]
        await self.end_giveaway(msg_id, giveaway)
        await interaction.response.send_message("✅ Giveaway ended!", ephemeral=True)
    
    @app_commands.command(name="reroll", description="Reroll a giveaway winner (Admin only)")
    @app_commands.describe(message_id="The message ID of the ended giveaway")
    async def reroll_giveaway(self, interaction: discord.Interaction, message_id: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Admin only command!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            msg_id = int(message_id)
        except ValueError:
            await interaction.followup.send("❌ Invalid message ID!", ephemeral=True)
            return
        
        found = False
        for channel in interaction.guild.text_channels:
            try:
                msg = await channel.fetch_message(msg_id)
                if msg.embeds and "GIVEAWAY ENDED" in msg.embeds[0].title:
                    await interaction.followup.send("❌ Reroll feature requires stored entries. Please re-run the giveaway instead.", ephemeral=True)
                    found = True
                    break
            except:
                continue
        
        if not found:
            await interaction.followup.send("❌ Giveaway message not found!")


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaways(bot))