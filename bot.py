import discord
from discord.ext import commands, tasks
import re
import asyncio
from collections import defaultdict
import datetime
from dotenv import load_dotenv
import os
import random  # Pour les giveaways

load_dotenv()  # Charge les variables du fichier .env
TOKEN = os.getenv("DISCORD_BOT_TOKEN")  # On récupère le token depuis le fichier .env

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

MOD_LOG_CHANNEL_NAME = "mod-log"
MUTE_ROLE_NAME = "Muted"

SUSPICIOUS_PATTERNS = [
    r"(https?://)?(www\.)?(grabify|iplogger|bit\.ly|tinyurl|discord\.gift)",
    r"free\s+nitro",
    r"token",
    r"airdrop",
    r"claim\s+reward"
]

BANNED_WORDS = ["insulte1", "insulte2", "autremotinterdit"]

warnings = defaultdict(lambda: defaultdict(int))
message_timestamps = defaultdict(lambda: defaultdict(list))

async def log_action(guild, content):
    log_channel = discord.utils.get(guild.text_channels, name=MOD_LOG_CHANNEL_NAME)
    if log_channel:
        await log_channel.send(content)
    else:
        print("[⚠️] Canal #mod-log introuvable.")

async def ensure_mute_role(guild):
    role = discord.utils.get(guild.roles, name=MUTE_ROLE_NAME)
    if role is None:
        role = await guild.create_role(name=MUTE_ROLE_NAME, reason="Role pour mute automatique")
        for channel in guild.channels:
            await channel.set_permissions(role, send_messages=False, speak=False, add_reactions=False)
    return role

async def mute_member(member, duration_seconds=300):
    role = await ensure_mute_role(member.guild)
    await member.add_roles(role, reason="Mute automatique")
    await log_action(member.guild, f"🔇 {member} a été mute pour {duration_seconds} secondes")
    await asyncio.sleep(duration_seconds)
    await member.remove_roles(role, reason="Fin du mute automatique")
    await log_action(member.guild, f"🔈 {member} a été unmute après {duration_seconds} secondes")

def is_mod(member):
    mod_roles = ["Admin", "Modérateur", "Mod"]
    return any(role.name in mod_roles for role in member.roles) or member.guild_permissions.administrator

@bot.event
async def on_ready():
    print(f"[✅] Bot connecté en tant que {bot.user}")

@bot.event
async def on_member_join(member):
    channel = discord.utils.get(member.guild.text_channels, name="arrivees-departs")
    if channel:
        await channel.send(f"👋 {member.mention} a rejoint le serveur !")
    await log_action(member.guild, f"✅ **{member}** a rejoint le serveur.")

@bot.event
async def on_member_remove(member):
    channel = discord.utils.get(member.guild.text_channels, name="arrivees-departs")
    if channel:
        await channel.send(f"😢 {member.name} a quitté le serveur.")
    await log_action(member.guild, f"❌ **{member}** a quitté ou a été kick/ban.")

@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return
    await log_action(message.guild, f"🗑️ Message supprimé de **{message.author}** : `{message.content}`")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    guild_id = message.guild.id
    user_id = message.author.id

    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, message.content, re.IGNORECASE):
            await message.delete()
            await log_action(message.guild, f"🚨 Message suspect supprimé de **{message.author}** dans {message.channel.mention} :\n`{message.content}`")
            return

    for bad_word in BANNED_WORDS:
        if bad_word.lower() in message.content.lower():
            await message.delete()
            warnings[guild_id][user_id] += 1
            await log_action(message.guild, f"⚠️ Message avec mot interdit supprimé de **{message.author}** ({warnings[guild_id][user_id]} warnings).")
            if warnings[guild_id][user_id] == 3:
                await mute_member(message.author, duration_seconds=300)
            elif warnings[guild_id][user_id] >= 5:
                await message.guild.ban(message.author, reason="Trop de warnings")
                await log_action(message.guild, f"🚫 {message.author} a été banni pour trop de warnings.")
            return

    now = datetime.datetime.utcnow()
    message_timestamps[guild_id][user_id].append(now)
    message_timestamps[guild_id][user_id] = [t for t in message_timestamps[guild_id][user_id] if (now - t).total_seconds() < 10]
    if len(message_timestamps[guild_id][user_id]) > 5:
        await message.delete()
        await mute_member(message.author, duration_seconds=300)
        await log_action(message.guild, f"🚨 {message.author} a été mute pour spam.")
        return

    if message.content.lower() in ["salut", "hello", "bonjour"]:
        await message.channel.send(f"Salut {message.author.mention} ! 👋")

    await bot.process_commands(message)

@bot.command()
async def ping(ctx):
    await ctx.send("Pong 🏓")

@bot.command()
async def clear(ctx, amount: int = 5):
    if not is_mod(ctx.author):
        return await ctx.send("❌ Tu n'as pas la permission.")
    deleted = await ctx.channel.purge(limit=amount)
    await ctx.send(f"🧹 {len(deleted)} messages supprimés.", delete_after=5)

@bot.command()
async def mute(ctx, member: discord.Member, duration: int = 5):
    if not is_mod(ctx.author):
        return await ctx.send("❌ Tu n'as pas la permission.")
    await mute_member(member, duration * 60)
    await ctx.send(f"🔇 {member.mention} mute pour {duration} minutes.")

@bot.command()
async def unmute(ctx, member: discord.Member):
    if not is_mod(ctx.author):
        return await ctx.send("❌ Tu n'as pas la permission.")
    role = discord.utils.get(ctx.guild.roles, name=MUTE_ROLE_NAME)
    if role in member.roles:
        await member.remove_roles(role)
        await ctx.send(f"🔈 {member.mention} a été unmute.")
        await log_action(ctx.guild, f"🔈 {member} a été unmute par {ctx.author}.")
    else:
        await ctx.send(f"{member.mention} n'est pas mute.")

@bot.command()
async def warn(ctx, member: discord.Member):
    if not is_mod(ctx.author):
        return await ctx.send("❌ Tu n'as pas la permission.")
    guild_id = ctx.guild.id
    user_id = member.id
    warnings[guild_id][user_id] += 1
    await ctx.send(f"⚠️ {member.mention} a reçu un avertissement. Total : {warnings[guild_id][user_id]}")
    await log_action(ctx.guild, f"⚠️ {member} a reçu un avertissement par {ctx.author}. Total : {warnings[guild_id][user_id]}")
    if warnings[guild_id][user_id] == 3:
        await mute_member(member, duration_seconds=300)
    elif warnings[guild_id][user_id] >= 5:
        await ctx.guild.ban(member, reason="Trop de warnings")
        await log_action(ctx.guild, f"🚫 {member} a été banni pour trop de warnings.")

@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"Info de {member}", color=discord.Color.blue())
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="Pseudo", value=member.display_name, inline=True)
    embed.add_field(name="Compte créé le", value=member.created_at.strftime("%d/%m/%Y %H:%M:%S"), inline=True)
    embed.add_field(name="Rejoint le serveur", value=member.joined_at.strftime("%d/%m/%Y %H:%M:%S"), inline=True)
    roles = ", ".join([role.name for role in member.roles if role.name != "@everyone"])
    embed.add_field(name=f"Rôles ({len(member.roles)-1})", value=roles or "Aucun", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def slowmode(ctx, seconds: int):
    if not is_mod(ctx.author):
        return await ctx.send("❌ Tu n'as pas la permission.")
    await ctx.channel.edit(slowmode_delay=seconds)
    await ctx.send(f"🐢 Slowmode activé à {seconds} secondes.")

@bot.command()
async def giveaway(ctx, duration: int, *, prize: str):
    if not is_mod(ctx.author):
        return await ctx.send("❌ Tu n'as pas la permission.")
    embed = discord.Embed(title="🎉 Giveaway !", description=prize, color=discord.Color.gold())
    embed.set_footer(text=f"Fini dans {duration} minutes.")
    message = await ctx.send(embed=embed)
    await message.add_reaction("🎉")
    await asyncio.sleep(duration * 60)
    message = await ctx.channel.fetch_message(message.id)
    users = set()
    for reaction in message.reactions:
        if str(reaction.emoji) == "🎉":
            async for user in reaction.users():
                if not user.bot:
                    users.add(user)
    if users:
        winner = random.choice(list(users))
        await ctx.send(f"🎊 Félicitations {winner.mention}, tu as gagné : {prize} !")
    else:
        await ctx.send("Personne n'a participé au giveaway.")

@bot.command()
@commands.has_permissions(administrator=True)
async def unban(ctx, *, member):
    banned_users = await ctx.guild.bans()
    try:
        member_name, member_discriminator = member.split('#')
    except ValueError:
        return await ctx.send("❌ Utilise la commande avec le format Pseudo#1234")

    for ban_entry in banned_users:
        user = ban_entry.user
        if (user.name, user.discriminator) == (member_name, member_discriminator):
            await ctx.guild.unban(user)
            await ctx.send(f"✅ {user} a été débanni.")
            await log_action(ctx.guild, f"✅ {user} a été débanni par {ctx.author}.")
            return
    await ctx.send(f"❌ Utilisateur {member} non trouvé dans la liste des bannis.")

@bot.command()
@commands.has_permissions(administrator=True)
async def create_all(ctx):
    guild = ctx.guild
    roles_to_create = [
        {"name": "Admin", "permissions": discord.Permissions(administrator=True)},
        {"name": "Mod", "permissions": discord.Permissions(manage_messages=True, kick_members=True, ban_members=True)},
        {"name": "Fortnite"},
        {"name": "Valorant"},
        {"name": "Rocket League"},
        {"name": "EON"},
        {"name": "NOVA"},
        {"name": "VRM"},
    ]
    for r in roles_to_create:
        existing = discord.utils.get(guild.roles, name=r["name"])
        if not existing:
            perms = r.get("permissions", discord.Permissions.none())
            await guild.create_role(name=r["name"], permissions=perms)
    jeux = ["Fortnite", "Valorant", "Rocket League", "EON", "NOVA", "VRM"]
    types_salon = {
        "textuels": ["discussion", "partage-photos", "idees"],
        "vocaux": ["Vocal 1", "Vocal 2", "Vocal 3"]
    }
    for jeu in jeux:
        cat = discord.utils.get(guild.categories, name=jeu)
        if not cat:
            cat = await guild.create_category(jeu)
        for salon in types_salon["textuels"]:
            chan_name = f"{jeu.lower()}-{salon}"
            if not discord.utils.get(guild.text_channels, name=chan_name):
                await guild.create_text_channel(chan_name, category=cat)
        for vocal in types_salon["vocaux"]:
            chan_name = f"{jeu.lower()}-{vocal.lower().replace(' ', '-')}"
            if not discord.utils.get(guild.voice_channels, name=chan_name):
                await guild.create_voice_channel(chan_name, category=cat)
    await ctx.send("✅ Tous les rôles et salons ont été créés ou étaient déjà présents.")
    await log_action(guild, f"✅ {ctx.author} a lancé la commande !create_all, rôles et salons créés.")

@bot.command()
@commands.has_permissions(administrator=True)
async def arrive(ctx):
    guild = ctx.guild
    channel_name = "arrivees-departs"
    existing_channel = discord.utils.get(guild.text_channels, name=channel_name)

    if existing_channel is None:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(send_messages=False, read_messages=True),
            guild.me: discord.PermissionOverwrite(send_messages=True, read_messages=True)
        }
        channel = await guild.create_text_channel(channel_name, overwrites=overwrites)
        await ctx.send(f"✅ Salon `{channel_name}` créé avec succès.")
        await log_action(guild, f"📢 Salon `{channel_name}` créé par {ctx.author}.")
    else:
        await ctx.send(f"ℹ️ Le salon `{channel_name}` existe déjà.")

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="Aucune raison donnée"):
    await ctx.guild.kick(member, reason=reason)
    await ctx.send(f"👢 {member.mention} a été expulsé. Raison : {reason}")
    await log_action(ctx.guild, f"👢 {member} a été kick par {ctx.author}. Raison : {reason}")

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="Aucune raison donnée"):
    await ctx.guild.ban(member, reason=reason)
    await ctx.send(f"🚫 {member.mention} a été banni. Raison : {reason}")
    await log_action(ctx.guild, f"🚫 {member} a été banni par {ctx.author}. Raison : {reason}")

bot.run(TOKEN)
