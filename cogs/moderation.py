import discord
from discord.ext import commands
from datetime import timedelta
import json
import os
import asyncio

STAFF_ROLE = "Staff"

def staff_only():
    async def predicate(ctx):
        staff_role = discord.utils.get(ctx.guild.roles, name=STAFF_ROLE)
        if staff_role and staff_role in ctx.author.roles:
            return True
        await ctx.send(f"You need the {STAFF_ROLE} role to use this command")
        return False
    return commands.check(predicate)

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.warnings = {}
        if os.path.exists('warnings.json'):
            with open('warnings.json', 'r') as f:
                self.warnings = json.load(f)
    
    def save_warnings(self):
        with open('warnings.json', 'w') as f:
            json.dump(self.warnings, f)
    
    @commands.command()
    @staff_only()
    async def kick(self, ctx, member: discord.Member, *, reason="No reason"):
        await member.kick(reason=reason)
        await ctx.send(f"Kicked {member.mention} | Reason: {reason}")
    
    @commands.command()
    @staff_only()
    async def ban(self, ctx, member: discord.Member, *, reason="No reason"):
        await member.ban(reason=reason)
        await ctx.send(f"Banned {member.mention} | Reason: {reason}")
    
    @commands.command()
    @staff_only()
    async def unban(self, ctx, *, user):
        banned = [entry async for entry in ctx.guild.bans()]
        for ban_entry in banned:
            if str(ban_entry.user) == user:
                await ctx.guild.unban(ban_entry.user)
                await ctx.send(f"Unbanned {user}")
                return
        await ctx.send(f"{user} not found in bans")
    
    @commands.command()
    @staff_only()
    async def mute(self, ctx, member: discord.Member, minutes: int = 10):
        await member.timeout(timedelta(minutes=minutes))
        await ctx.send(f"Muted {member.mention} for {minutes} minutes")
    
    @commands.command()
    @staff_only()
    async def unmute(self, ctx, member: discord.Member):
        await member.timeout(None)
        await ctx.send(f"Unmuted {member.mention}")
    
    @commands.command()
    @staff_only()
    async def clear(self, ctx, amount: int):
        if amount > 100:
            await ctx.send("Max 100 messages")
            return
        deleted = await ctx.channel.purge(limit=amount + 1)
        msg = await ctx.send(f"Deleted {len(deleted)-1} messages")
        await asyncio.sleep(3)
        await msg.delete()
    
    @commands.command()
    @staff_only()
    async def warn(self, ctx, member: discord.Member, *, reason="No reason"):
        guild_id = str(ctx.guild.id)
        member_id = str(member.id)
        
        if guild_id not in self.warnings:
            self.warnings[guild_id] = {}
        if member_id not in self.warnings[guild_id]:
            self.warnings[guild_id][member_id] = []
        
        self.warnings[guild_id][member_id].append({
            "reason": reason,
            "moderator": str(ctx.author),
            "time": str(ctx.message.created_at)
        })
        self.save_warnings()
        await ctx.send(f"Warned {member.mention} | Reason: {reason}")
    
    @commands.command()
    @staff_only()
    async def warnings(self, ctx, member: discord.Member):
        guild_id = str(ctx.guild.id)
        member_id = str(member.id)
        
        if guild_id in self.warnings and member_id in self.warnings[guild_id]:
            warns = self.warnings[guild_id][member_id]
            embed = discord.Embed(title=f"Warnings for {member.name}", color=discord.Color.yellow())
            for i, w in enumerate(warns, 1):
                embed.add_field(name=f"Warning {i}", value=f"Reason: {w['reason']}\nBy: {w['moderator']}", inline=False)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"{member.mention} has no warnings")

async def setup(bot):
    await bot.add_cog(Moderation(bot))