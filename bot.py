import discord
from discord.ext import commands
from config import token  # Import the bot's token from configuration file
import re
import json
import os
from typing import Optional

DATA_DIR = "data"
BADWORDS_FILE = os.path.join(DATA_DIR, "badwords.json")
STRIKES_FILE = os.path.join(DATA_DIR, "strikes.json")
DEFAULT_BADWORDS = ["badword", "kasar1", "kasar2"]

WHITELIST_ROLES = ["Admin", "Moderator"]

BAN_ON_DETECT = False

STRIKES_BEFORE_BAN = 3

MOD_LOG_CHANNEL_NAME = "bot-codding"

intents = discord.Intents.default()
intents.members = True  # Allows the bot to work with users and ban them
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

url_regex = re.compile(r"http[s]?://")
whitelist_domains = ["youtube.com", "youtu.be", "discord.gg"]

def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def load_json(path: str, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)
        return default.copy()
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

ensure_data_dir()
BADWORDS = load_json(BADWORDS_FILE, DEFAULT_BADWORDS)
STRIKES = load_json(STRIKES_FILE, {})

badwords_pattern = re.compile(r"\b(" + "|".join(re.escape(w) for w in BADWORDS) + r")\b", re.IGNORECASE)

def recompile_pattern():
    global badwords_pattern
    if BADWORDS:
        badwords_pattern = re.compile(r"\b(" + "|".join(re.escape(w) for w in BADWORDS) + r")\b", re.IGNORECASE)
    else:
        # match nothing
        badwords_pattern = re.compile(r"(?!x)x")

async def send_mod_log(guild: discord.Guild, content: str):
    ch = discord.utils.get(guild.text_channels, name=MOD_LOG_CHANNEL_NAME)
    if ch is None:
        ch = guild.system_channel
    if ch:
        try:
            await ch.send(content)
        except Exception:
            pass

def user_is_whitelisted(member: discord.Member) -> bool:
    # user has administration perms or has one of whitelist roles
    if member.guild_permissions.administrator or member.guild_permissions.ban_members or member.guild_permissions.manage_messages:
        return True
    for role in member.roles:
        if role.name in WHITELIST_ROLES:
            return True
    return False


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

@bot.command()
async def start(ctx):
    await ctx.send("Hi! I'm a chat manager bot!")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not isinstance(message.author, discord.Member):
        await bot.process_commands(message)
        return

    if message.guild is None:
        await bot.process_commands(message)
        return

    author = message.author

    if user_is_whitelisted(author):
        await bot.process_commands(message)
        return

    content = message.content or ""
    if badwords_pattern.search(content):
        guild = message.guild
        reason = "Mengirim kata-kata kasar/terlarang"

        try:
            if message.channel.permissions_for(guild.me).manage_messages:
                await message.delete()
        except Exception:
            pass

        if BAN_ON_DETECT:
            try:
                await author.ban(reason=reason)
                await send_mod_log(guild, f" {author} ({author.id}) di-BAN otomatis. Alasan: {reason}\nPesan: {content}")
            except discord.Forbidden:
                await send_mod_log(guild, f" Gagal ban {author} — izin tidak cukup.")
            except Exception as e:
                await send_mod_log(guild, f" Error saat ban {author}: {e}")
            finally:
                await bot.process_commands(message)
                return
        uid = str(author.id)
        strikes = STRIKES.get(uid, 0) + 1
        STRIKES[uid] = strikes
        save_json(STRIKES_FILE, STRIKES)

        if strikes >= STRIKES_BEFORE_BAN:
            try:
                await author.ban(reason=f"Terakumulasi {strikes} pelanggaran: kata kotor")
                await send_mod_log(guild, f" {author} ({author.id}) di-BAN setelah mencapai {strikes} strikes. Pesan: {content}")
                STRIKES.pop(uid, None)
                save_json(STRIKES_FILE, STRIKES)
            except discord.Forbidden:
                await send_mod_log(guild, f" Gagal ban {author} — izin tidak cukup.")
            except Exception as e:
                await send_mod_log(guild, f" Error saat ban {author}: {e}")
        else:
            try:
                await message.channel.send(f" {author.mention}, pesanmu mengandung kata yang tidak pantas. Strike {strikes}/{STRIKES_BEFORE_BAN}.")
            except Exception:
                pass
            await send_mod_log(guild, f" {author} ({author.id}) mendapat strike {strikes}/{STRIKES_BEFORE_BAN}. Pesan: {content}")

    await bot.process_commands(message)

@bot.command(name="listbad")
@commands.has_permissions(administrator=True)
async def list_bad(ctx):
    if not BADWORDS:
        await ctx.send("Daftar kata terlarang kosong.")
    else:
        await ctx.send("Kata terlarang:\n" + ", ".join(BADWORDS))

@bot.command(name="addbad")
@commands.has_permissions(administrator=True)
async def add_bad(ctx, *, word: str):
    word = word.strip().lower()
    if not word:
        await ctx.send("Masukkan kata yang valid.")
        return
    if word in BADWORDS:
        await ctx.send(f"'{word}' sudah ada di daftar.")
        return
    BADWORDS.append(word)
    save_json(BADWORDS_FILE, BADWORDS)
    recompile_pattern()
    await ctx.send(f"Menambahkan '{word}' ke daftar kata terlarang.")

@bot.command(name="rmbad")
@commands.has_permissions(administrator=True)
async def rm_bad(ctx, *, word: str):
    word = word.strip().lower()
    if word not in BADWORDS:
        await ctx.send(f"'{word}' tidak ditemukan.")
        return
    BADWORDS.remove(word)
    save_json(BADWORDS_FILE, BADWORDS)
    recompile_pattern()
    await ctx.send(f"Menghapus '{word}' dari daftar kata terlarang.")

@bot.command(name="setstrikes")
@commands.has_permissions(administrator=True)
async def set_strikes(ctx, n: int):
    global STRIKES_BEFORE_BAN
    if n < 1:
        await ctx.send("Nilai minimal 1.")
        return
    STRIKES_BEFORE_BAN = n
    await ctx.send(f"Jumlah strikes sebelum ban diset ke {n}.")

@bot.command(name="clearstrikes")
@commands.has_permissions(administrator=True)
async def clear_strikes(ctx, member: Optional[discord.Member] = None):
    if member is None:
        STRIKES.clear()
        save_json(STRIKES_FILE, STRIKES)
        await ctx.send("Semua strikes direset.")
    else:
        uid = str(member.id)
        if uid in STRIKES:
            STRIKES.pop(uid, None)
            save_json(STRIKES_FILE, STRIKES)
            await ctx.send(f"Strikes {member} direset.")
        else:
            await ctx.send(f"{member} tidak punya strikes.")

@bot.command(name="banon")
@commands.has_permissions(administrator=True)
async def ban_on(ctx):
    global BAN_ON_DETECT
    BAN_ON_DETECT = True
    await ctx.send("Mode: langsung BAN aktif.")

@bot.command(name="banoff")
@commands.has_permissions(administrator=True)
async def ban_off(ctx):
    global BAN_ON_DETECT
    BAN_ON_DETECT = False
    await ctx.send("Mode: langsung BAN dimatikan. Menggunakan sistem strikes.")


@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member = None):
    if member:
        if ctx.author.top_role <= member.top_role:
            await ctx.send("It is not possible to ban a user with equal or higher rank!")
        else:
            await ctx.guild.ban(member)
            await ctx.send(f"User {member.name} was banned.")
    else:
        await ctx.send("This command should point to the user you want to ban. For example: `!ban @user`")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if url_regex.search(message.content):
        if any(domain in message.content for domain in whitelist_domains):
            return
        try:
            await message.author.ban(reason="Mengirim link URL dilarang")
            await message.channel.send(
                f" {message.author.mention} telah di-ban karena mengirim link URL!"
            )
        except Exception as e:
            await message.channel.send(f" Gagal nge-ban {message.author}. Error: {str(e)}")

    await bot.process_commands(message)

@ban.error
async def ban_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have sufficient permissions to execute this command.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("User not found.")

bot.run(token)