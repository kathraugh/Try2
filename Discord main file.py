# main.py

import os
import random
from datetime import datetime, timedelta

import discord
from discord.ext import commands

# ------------- CONFIG -------------

# Read token from environment (Railway: DISCORD_TOKEN variable)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Katie’s IDs — fully inserted
GATE_ROLE_ID = 1444877012350013572
UNVERIFIED_ROLE_ID = 1444877103270199338
VERIFIED_ROLE_ID = 1442356268491604050
LEADERSHIP_ROLE_ID = 1317529054123130911

VERIFY_LOGS_CHANNEL_ID = 1444880450719055943
VERIFICATION_CHANNEL_ID = 1442241968032845834

# Captcha settings
MAX_ATTEMPTS = 3
TIME_LIMIT_MINUTES = 10
# ----------------------------------

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# member.id -> captcha info
pending_captchas: dict[int, dict] = {}
# member.id -> verification info
verification_data: dict[int, dict] = {}


def create_math_captcha():
    a = random.randint(2, 9)
    b = random.randint(2, 9)
    return f"What is {a} + {b}?", a + b


async def log_message(guild: discord.Guild, text: str):
    channel = guild.get_channel(VERIFY_LOGS_CHANNEL_ID)
    if channel:
        await channel.send(text)


async def send_captcha(member: discord.Member):
    try:
        question, answer = create_math_captcha()
        pending_captchas[member.id] = {
            "answer": answer,
            "attempts": 0,
            "expires_at": datetime.utcnow() + timedelta(minutes=TIME_LIMIT_MINUTES),
            "guild_id": member.guild.id,
        }

        await member.send(
            f"Hey {member.mention} 👋\n\n"
            "**Welcome to 1 Nation.** This is the kingdom people migrate **to**, not from.\n\n"
            "Before we let you through the gates, I need to make sure you’re an actual human "
            "and not a spam goblin.\n\n"
            f"🧮 **Solve this:**\n**{question}**\n\n"
            f"You’ve got **{TIME_LIMIT_MINUTES} minutes** and **{MAX_ATTEMPTS} attempts**.\n"
            "_Loyalty • Honor • Respect_"
        )

    except discord.Forbidden:
        print(f"⚠️ Could not DM {member} for captcha.")


@bot.event
async def on_ready():
    print("🔥 Bot online")
    print(f"User: {bot.user} (ID: {bot.user.id})")


@bot.event
async def on_member_join(member: discord.Member):
    gate_role = member.guild.get_role(GATE_ROLE_ID)
    if gate_role:
        await member.add_roles(gate_role, reason="Joined — awaiting captcha")

    verification_data[member.id] = {
        "status": "captcha_pending",
        "ign": None,
        "screenshot_link": None,
        "joined_at": datetime.utcnow(),
        "verified_at": None,
        "verified_by": None,
    }

    await send_captcha(member)
    await log_message(member.guild, f"📥 New member joined: {member.mention} — awaiting captcha.")


@bot.event
async def on_message(message: discord.Message):
    # Ignore bot messages
    if message.author.bot:
        return

    # Handle DMs for captcha
    if isinstance(message.channel, discord.DMChannel):
        await handle_captcha(message)
        return

    # Handle screenshot submission in #verification
    if (
        message.guild
        and message.channel.id == VERIFICATION_CHANNEL_ID
        and message.attachments
    ):
        user_id = message.author.id
        data = verification_data.get(user_id)
        if data:
            data["status"] = "pending"
            data["screenshot_link"] = message.jump_url

            await log_message(
                message.guild,
                f"🧾 Verification submitted by {message.author.mention}\nScreenshot: {message.jump_url}"
            )

            await message.channel.send(
                f"✅ Got your screenshot, {message.author.mention}.\n\n"
                "You’re officially **pending** review. Leadership will unlock the server once everything matches.\n"
                "Welcome to **3701** — you’re almost in."
            )

    # Make sure prefix commands still work
    await bot.process_commands(message)


async def handle_captcha(msg: discord.Message):
    user_id = msg.author.id
    data = pending_captchas.get(user_id)
    if not data:
        return

    guild = bot.get_guild(data["guild_id"])
    if guild is None:
        return

    member = guild.get_member(user_id)

    # Timeout check
    if datetime.utcnow() > data["expires_at"]:
        await try_kick(member, "⏰ Time’s up, love.\nYou didn’t answer the captcha.")
        pending_captchas.pop(user_id, None)
        return

    content = msg.content.strip()

    # Must be numeric
    if not content.isdigit():
        data["attempts"] += 1
        remaining = MAX_ATTEMPTS - data["attempts"]

        if remaining <= 0:
            await try_kick(member, "❌ You used all attempts on the human test.")
            pending_captchas.pop(user_id, None)
        else:
            await msg.channel.send(
                f"Mmm… that wasn’t it.\nTry again — **{remaining}** attempt(s) left."
            )
        return

    # Check correct answer
    if int(content) == data["answer"]:
        await captcha_pass(member)
        pending_captchas.pop(user_id, None)
    else:
        data["attempts"] += 1
        remaining = MAX_ATTEMPTS - data["attempts"]

        if remaining <= 0:
            await try_kick(member, "❌ Wrong again — and that was your last attempt.")
            pending_captchas.pop(user_id, None)
        else:
            await msg.channel.send(
                f"That’s not correct.\nTry again — **{remaining}** attempts left."
            )


async def try_kick(member: discord.Member | None, reason_text: str):
    if not member:
        return

    try:
        await member.send(
            f"{reason_text}\n\nYou can rejoin anytime.\n_Loyalty • Honor • Respect_"
        )
    except Exception:
        pass

    await log_message(member.guild, f"❌ {member.mention} failed captcha and was kicked.")
    await member.kick(reason="Failed captcha")


async def captcha_pass(member: discord.Member):
    guild = member.guild

    gate_role = guild.get_role(GATE_ROLE_ID)
    unverified_role = guild.get_role(UNVERIFIED_ROLE_ID)

    if gate_role and gate_role in member.roles:
        await member.remove_roles(gate_role)

    if unverified_role and unverified_role not in member.roles:
        await member.add_roles(unverified_role)

    if member.id not in verification_data:
        verification_data[member.id] = {}

    verification_data[member.id]["status"] = "unverified"

    verification_channel = guild.get_channel(VERIFICATION_CHANNEL_ID)

    try:
        await member.send(
            "**Look at you, using your brain and everything!** 🎉\n\n"
            "You passed the captcha — welcome inside the walls.\n\n"
            f"Next step:\n"
            f"1️⃣ Go to {verification_channel.mention if verification_channel else '#verification'}\n"
            "2️⃣ Post your in-game profile screenshot\n"
            "3️⃣ Set your Discord nickname to your **exact** IGN\n\n"
            "Leadership will unlock full access after review.\n"
            "_Loyalty • Honor • Respect_"
        )
    except Exception:
        pass

    await log_message(guild, f"✅ {member.mention} passed captcha — now unverified.")


def is_lead(ctx: commands.Context) -> bool:
    return discord.utils.get(ctx.author.roles, id=LEADERSHIP_ROLE_ID) is not None


@bot.command()
async def verify(ctx: commands.Context, member: discord.Member, *, ign=None):
    if not is_lead(ctx):
        return

    guild = ctx.guild
    data = verification_data.get(member.id)

    if not data:
        await ctx.send("I don’t have any verification info for that user.")
        return

    unverified = guild.get_role(UNVERIFIED_ROLE_ID)
    verified = guild.get_role(VERIFIED_ROLE_ID)

    if unverified and unverified in member.roles:
        await member.remove_roles(unverified)

    if verified and verified not in member.roles:
        await member.add_roles(verified)

    data["status"] = "verified"
    data["ign"] = ign or data["ign"]
    data["verified_at"] = datetime.utcnow()
    data["verified_by"] = ctx.author.id

    try:
        await member.send(
            "🎉 **You are now verified in 1 Nation!**\n"
            f"Verified by: **{ctx.author.display_name}**\n"
            f"IGN on record: **{data['ign']}**\n\n"
            "Welcome home. We’re glad you’re here.\n"
            "_Loyalty • Honor • Respect_"
        )
    except Exception:
        pass

    await ctx.send(f"✅ {member.mention} is now verified. Welcome to the kingdom. ⚔️")
    await log_message(guild, f"✅ {member.mention} verified by {ctx.author.mention}")


@bot.command()
async def reject(ctx: commands.Context, member: discord.Member, *, reason="No reason provided"):
    if not is_lead(ctx):
        return

    data = verification_data.get(member.id)
    if data:
        data["status"] = "rejected"

    try:
        await member.send(
            "❌ Your verification has been rejected.\n"
            f"Reason: **{reason}**\n\n"
            "Fix the issue and try again anytime.\n"
            "_Loyalty • Honor • Respect_"
        )
    except Exception:
        pass

    await ctx.send(f"❌ Verification rejected for {member.mention} — **{reason}**")
    await log_message(ctx.guild, f"❌ {member.mention} rejected — {reason}")


@bot.command()
async def pending(ctx: commands.Context):
    if not is_lead(ctx):
        return

    out = []
    for m in ctx.guild.members:
        d = verification_data.get(m.id)
        if d and d.get("status") == "pending":
            joined = d.get("joined_at")
            joined_str = joined.strftime('%Y-%m-%d') if joined else "unknown"
            out.append(f"- {m.mention} (joined {joined_str})")

    if not out:
        await ctx.send("Everyone’s behaving. No pending verifications right now.")
    else:
        await ctx.send("⏳ **Pending Verifications:**\n" + "\n".join(out))


@bot.command()
async def kickunverified(ctx: commands.Context, days: int = 7):
    if not is_lead(ctx):
        return

    guild = ctx.guild
    role = guild.get_role(UNVERIFIED_ROLE_ID)
    cutoff = datetime.utcnow() - timedelta(days=days)

    kicked = []
    for m in guild.members:
        if role and role in m.roles and m.joined_at and m.joined_at.replace(tzinfo=None) < cutoff:
            try:
                await m.send(
                    f"⏰ Removed for not verifying within **{days} days**.\n"
                    "Rejoin anytime.\n_Loyalty • Honor • Respect_"
                )
            except Exception:
                pass

            await m.kick(reason="Too long unverified")
            kicked.append(m)

    if not kicked:
        await ctx.send("No unverified stragglers to remove.")
    else:
        await ctx.send(
            f"❌ Removed **{len(kicked)}** unverified members.\n"
            "Gates reopen if they return ready to verify."
        )


@bot.command()
async def checkname(ctx: commands.Context, member: discord.Member):
    if not is_lead(ctx):
        return

    d = verification_data.get(member.id, {})
    nickname = member.nick or member.name

    joined = d.get("joined_at")
    joined_str = joined.strftime('%Y-%m-%d %H:%M') if joined else "unknown"

    msg = (
        f"🧾 **Verification Check for {member.mention}:**\n"
        f"• Nickname: `{nickname}`\n"
        f"• Status: `{d.get('status', 'unknown')}`\n"
        f"• IGN: `{d.get('ign', 'not recorded')}`\n"
        f"• Screenshot: {d.get('screenshot_link', 'none')}\n"
        f"• Joined: `{joined_str}`"
    )

    await ctx.send(msg)


@bot.command()
async def verifyinfo(ctx: commands.Context):
    await ctx.send(
        "📌 **Verification Required**\n\n"
        f"1️⃣ Post a screenshot of your in-game profile in <#{VERIFICATION_CHANNEL_ID}>\n"
        "2️⃣ Set your nickname to your **exact** IGN\n\n"
        "Leadership will unlock full access after review.\n"
        "_Loyalty • Honor • Respect_"
    )


# ------------ ENTRYPOINT FOR RAILWAY ------------

def main():
    if not DISCORD_TOKEN:
        raise RuntimeError(
            "DISCORD_TOKEN environment variable is not set.\n"
            "On Railway: Project → Variables → add DISCORD_TOKEN = your bot token."
        )

    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
