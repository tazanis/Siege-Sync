# -*- coding: utf-8 -*-
# bot.py
# Requires: pip install -U discord.py pytz
# Python 3.10+ recommended

import os
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import pytz
import logging

from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("attendance-bot")

# ====== CONFIG ======

load_dotenv()

def get_env_var_as_int(name: str) -> int:
    """Gets an environment variable and casts it to an integer, raising an error if it's missing or invalid."""
    val = os.getenv(name)
    if not val or not val.isdigit():
        raise RuntimeError(f"Required environment variable '{name}' is missing or not a valid integer.")
    return int(val)

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Required environment variable 'DISCORD_BOT_TOKEN' is missing.")


GUILD_ID = get_env_var_as_int("GUILD_ID")
ANNOUNCE_CHANNEL_ID = get_env_var_as_int("ANNOUNCE_CHANNEL_ID")
LOG_CHANNEL_ID = get_env_var_as_int("LOG_CHANNEL_ID")
GUILD_CHAT_ID = get_env_var_as_int("GUILD_CHAT_ID")
MENTION_ROLE_ID = get_env_var_as_int("MENTION_ROLE_ID")

# Times (GMT+8 / Asia/Manila)
TZ = pytz.timezone("Asia/Manila")
POST_HOUR = 22
POST_MIN = 0
SUMMARY_HOUR = 21
SUMMARY_MIN = 0

# Roles shown as buttons
ROLES = ["Shot Caller", "Main Ball", "Flex", "Def Team", "Absent"]
MAIN_ROLES = ["Shot Caller", "Main Ball", "Flex", "Def Team"]
ALL_STORED_ROLES = ROLES + ["Reserves"]

# Persistence file
DATA_FILE = Path("attendance_data.json")

# Def Team Limits
DEF_LIMITS = {
    "Hwatcha Rider": 1,
    "Flame Tower Rider": 2,
    "Elephant Rider": 1,
    "Builder": 1
}

# ====== CLASSES ======
CLASSES: Dict[str, Tuple[str, Optional[str]]] = {
    # Flex (formerly Fast)
    "Dead Eye": ("Flex", None),
    "Musa": ("Flex", None),
    "Maehwa": ("Flex", None),
    "Ninja": ("Flex", None),
    "Kunoichi": ("Flex", None),
    "Hashasin": ("Flex", None),
    "Sorceress": ("Flex", None),
 
    # Melee
    "Nova": ("Melee", None),
    "Drakania": ("Melee", None),
    "Dark Knight": ("Melee", None),
    "Guardian": ("Melee", None),
    "Warrior": ("Melee", None),
    "Wukong": ("Melee", None),
    "Seraph": ("Melee", None),
    "Striker": ("Melee", None),
    "Mystic": ("Melee", None),
    "Sage": ("Melee", None),
    "Scholar": ("Melee", None),
    "Tamer": ("Melee", None),
    "Woosa": ("Melee", None),
    "Dusa": ("Melee", None),


    # Range
    "Archer": ("Range", None),
    "Ranger": ("Range", None),
    "Maegu": ("Range", None),
    "Wizard": ("Range", None),
    "Witch": ("Range", None),

    # Special
    "Shai": ("Special", None),
    "Berserker": ("Special", None),
    "Valkyrie": ("Special", None),
     "Corsair": ("Special", None),

    # Defense
    "Hwatcha Rider": ("Defense", "🚀"),
    "Flame Tower Rider": ("Defense", "🔥"),
    "Elephant Rider": ("Defense", "🐘"),
    "Builder": ("Defense", "🔨"),
}

CATEGORY_ORDER = ["Flex", "Melee", "Range", "Special", "Defense"]

CLASS_TYPES: Dict[str, List[Tuple[str, Optional[str]]]] = {}
for cls_name, (cls_type, emoji) in CLASSES.items():
    CLASS_TYPES.setdefault(cls_type, []).append((cls_name, emoji))

ROLE_EMOJIS = {
    "Shot Caller": "⭐",
    "Main Ball": "🔵",
    "Flex": "🟢",
    "Def Team": "🛡️",
    "Absent": "❌",
}

# ====== Persistence ======
attendance_data: Dict[str, Dict] = {}

def load_data() -> None:
    global attendance_data
    if DATA_FILE.exists():
        try:
            raw = DATA_FILE.read_text(encoding="utf-8")
            attendance_data = json.loads(raw) if raw.strip() else {}
            if not isinstance(attendance_data, dict):
                log.warning("attendance_data.json did not contain a dict; resetting.")
                attendance_data = {}
        except Exception as e:
            log.exception("Failed loading data file; starting with empty data: %s", e)
            attendance_data = {}
    else:
        attendance_data = {}

def save_data() -> None:
    try:
        DATA_FILE.write_text(json.dumps(attendance_data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log.exception("Failed saving attendance data: %s", e)

def get_cap(date_str: str, tier: str) -> int:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        wd = dt.weekday() # Mon=0, Sun=6
        
        # Saturday always 100
        if wd == 5:
            return 100
        
        if tier == "T2":
            # Sun(6), Tue(1), Thu(3)
            if wd in (6, 1, 3): return  50
            # Mon(0), Wed(2), Fri(4) 
            return 40
        else: # Default T1
            # Sun(6), Tue(1), Thu(3)
            if wd in (6, 1, 3): return 30
            # Mon(0), Wed(2), Fri(4) 
            return 25
    except Exception:
        return 100

def is_attendance_locked(date_str: str) -> bool:
    """Checks if attendance for a given date is locked (i.e., it's past 9 PM)."""
    try:
        now = datetime.now(TZ)
        lock_time = TZ.localize(datetime.strptime(date_str, "%Y-%m-%d")).replace(
            hour=SUMMARY_HOUR, minute=SUMMARY_MIN, second=0, microsecond=0
        )
        return now >= lock_time
    except Exception:
        return False

def ensure_day(date_str: str) -> None:
    if date_str not in attendance_data:
        attendance_data[date_str] = {role: [] for role in ROLES}
        attendance_data[date_str]["_meta"] = {
            "posted": False,
            "announce_channel_id": None,
            "announce_message_id": None,
            "summarized": False,
            "summary_channel_id": None,
            "summary_message_id": None,
            "tier": "T1",
            "locked": False
        }
    if "Reserves" not in attendance_data[date_str]:
        attendance_data[date_str]["Reserves"] = []
    if "locked" not in attendance_data[date_str].get("_meta", {}):
        attendance_data[date_str]["_meta"]["locked"] = False

def member_mention(user_id_str: str) -> str:
    try:
        guild = bot.get_guild(GUILD_ID)
        if guild:
            member = guild.get_member(int(user_id_str))
            if member:
                return member.display_name
    except Exception:
        pass
    return f"<@{user_id_str}>"

# ====== formatting helpers ======
def _chunk_lines(lines: List[str], max_len: int = 1024) -> List[str]:
    if not lines:
        return []
    chunks: List[str] = []
    cur_lines: List[str] = []
    cur_len = 0
    for ln in lines:
        ln_len = len(ln) + 1
        if cur_lines and (cur_len + ln_len) > max_len:
            chunks.append("\n".join(cur_lines))
            cur_lines = []
            cur_len = 0
        if ln_len > max_len:
            safe = ln[: max_len - 1]
            if cur_lines:
                chunks.append("\n".join(cur_lines))
                cur_lines = []
                cur_len = 0
            chunks.append(safe)
            continue
        cur_lines.append(ln)
        cur_len += ln_len
    if cur_lines:
        chunks.append("\n".join(cur_lines))
    return chunks

# ====== Embed builder ======
def build_embed(date_str: str) -> discord.Embed:
    ensure_day(date_str)
    meta = attendance_data[date_str].get("_meta", {})
    tier = meta.get("tier", "T1")
    cap = get_cap(date_str, tier)
    
    embed = discord.Embed(
        title="⚔️ SiegeSync: War Attendance",
        description=(
            f"📅 **{date_str}** | 🏷️ **{tier}** (Cap: {cap})\n"
            f"🕘 **Event Time: 9:00 PM (GMT+8)**"
        ),
        color=discord.Color.blurple(),
        timestamp=datetime.now(TZ)
    )
    totals = 0

    # Display Main Roles + Absent
    # Layout: Shot Caller (L), Flex (R), Main Ball (L), Def Team (R)
    display_order = ["Shot Caller", "Flex", "Main Ball", "Def Team", "Reserves", "Absent"]

    for role in display_order:
        entries = attendance_data[date_str].get(role, []) or []
        if role in MAIN_ROLES:
            totals += len(entries)
        role_emoji = ROLE_EMOJIS.get(role, "")
        
        is_inline = role in ["Shot Caller", "Flex", "Main Ball", "Def Team"]

        if not entries:
            if role == "Reserves": continue # Don't show empty reserves
            embed.add_field(name=f"{role_emoji} **{role} (0)**", value="—", inline=is_inline)
            if role == "Flex":
                embed.add_field(name="\u200b", value="\u200b", inline=False)
            continue

        if role == "Absent" or role == "Reserves":
            header = f"⚠️ **Reserves ({len(entries)})**" if role == "Reserves" else f"{role_emoji} **{role} ({len(entries)})**"
            lines = [e.get("name") or member_mention(e["user_id"]) for e in entries]
            chunks = _chunk_lines(lines, max_len=1024)
            embed.add_field(name=header, value=chunks[0], inline=False)
            for cont in chunks[1:]:
                embed.add_field(name="\u200b", value=cont, inline=False)
            continue

        grouped: Dict[str, List[dict]] = {}
        for e in entries:
            cls = e.get("class", "Unknown")
            cat = CLASSES.get(cls, ("Unknown", ""))[0]
            grouped.setdefault(cat, []).append(e)

        all_lines: List[str] = []
        for cat in CATEGORY_ORDER:
            members = grouped.get(cat, [])
            if not members:
                continue
            all_lines.append(f"{cat} Classes:")
            for m in members:
                disp_name = m.get("name") or member_mention(m["user_id"])
                all_lines.append(f"{m.get('class','Unknown')} → {disp_name}")
            all_lines.append("")
        if all_lines and all_lines[-1] == "":
            all_lines = all_lines[:-1]

        chunks = _chunk_lines(all_lines, max_len=1024)
        embed.add_field(name=f"{role_emoji} **{role} ({len(entries)})**", value=chunks[0], inline=is_inline)
        for cont in chunks[1:]:
            embed.add_field(name="\u200b", value=cont, inline=is_inline)

        if role == "Flex":
            embed.add_field(name="\u200b", value="\u200b", inline=False)

    embed.set_footer(text=f"Confirmed Attendees: {totals}")
    return embed

# ====== Bot setup ======
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = False

bot = commands.Bot(command_prefix="!", intents=intents)

# ====== UI Components ======
class ClassSelect(discord.ui.Select):
    def __init__(self, role_name: str, date_str: str, cls_type: str, options: List[discord.SelectOption]):
        placeholder = f"Choose class ({cls_type})"
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)
        self.role_name = role_name
        self.date_str = date_str
        self.cls_type = cls_type

    async def callback(self, interaction: discord.Interaction):
        try:
            if is_attendance_locked(self.date_str):
                await interaction.response.send_message("❌ Attendance for this date is now closed.", ephemeral=True)
                return

            user_id = str(interaction.user.id)
            selected_class = self.values[0]
            ensure_day(self.date_str)

            for r in ALL_STORED_ROLES:
                attendance_data[self.date_str][r] = [
                    x for x in attendance_data[self.date_str].get(r, [])
                    if x.get("user_id") != user_id
                ]

            lst = attendance_data[self.date_str].setdefault(self.role_name, [])
            lst.append({"user_id": user_id, "class": selected_class, "name": interaction.user.display_name})
            attendance_data[self.date_str][self.role_name] = lst

            # Save user preference
            attendance_data.setdefault("_users", {})[user_id] = selected_class
            save_data()

            await edit_announce_and_summary(self.date_str)

            if self.role_name == "Reserves":
                msg = f"⚠️ Cap reached. You are in **Reserves** as **{selected_class}**."
            else:
                msg = f"✅ You are signed up for **{self.role_name}** as **{selected_class}**."
            
            await interaction.response.edit_message(content=msg, view=None)

        except Exception as e:
            log.exception("Error in ClassSelect.callback: %s", e)
            if interaction.response.is_done():
                await interaction.followup.send("❌ Error while saving your selection.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Error while saving your selection.", ephemeral=True)

class DefRoleSelect(discord.ui.Select):
    def __init__(self, date_str: str):
        self.date_str = date_str
        ensure_day(date_str)
        
        # Calculate availability
        current_def = attendance_data[date_str].get("Def Team", [])
        counts = {}
        for entry in current_def:
            c = entry.get("class")
            counts[c] = counts.get(c, 0) + 1
        
        options = []
        for role, limit in DEF_LIMITS.items():
            if counts.get(role, 0) >= limit:
                continue
            emoji = CLASSES[role][1]
            options.append(discord.SelectOption(label=role, emoji=emoji, value=role))
        
        if not options:
            options.append(discord.SelectOption(label="Full", value="Full", description="No defense roles available"))

        super().__init__(placeholder="Choose Defense Role", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            if is_attendance_locked(self.date_str):
                await interaction.response.send_message("❌ Attendance for this date is now closed.", ephemeral=True)
                return

            selected = self.values[0]
            if selected == "Full":
                await interaction.response.send_message("❌ All specific defense roles are full.", ephemeral=True)
                return

            user_id = str(interaction.user.id)
            ensure_day(self.date_str)
            
            # Clean user from all other roles first
            for r in ALL_STORED_ROLES:
                attendance_data[self.date_str][r] = [
                    x for x in attendance_data[self.date_str].get(r, [])
                    if x.get("user_id") != user_id
                ]

            # Add to Def Team
            lst = attendance_data[self.date_str].setdefault("Def Team", [])
            lst.append({"user_id": user_id, "class": selected, "name": interaction.user.display_name})
            attendance_data[self.date_str]["Def Team"] = lst
            save_data()
            
            await edit_announce_and_summary(self.date_str)
            await interaction.response.edit_message(content=f"✅ You are signed up for **Def Team** as **{selected}**.", view=None)
        except Exception as e:
            log.exception("Error in DefRoleSelect: %s", e)
            await interaction.response.send_message("❌ Error saving selection.", ephemeral=True)

class RoleButton(discord.ui.Button):
    def __init__(self, role_name: str, date_str: str):
        style = discord.ButtonStyle.danger if role_name == "Absent" else discord.ButtonStyle.primary
        super().__init__(label=role_name, style=style, custom_id=f"role:{date_str}:{role_name}")
        self.role_name = role_name
        self.date_str = date_str

    async def callback(self, interaction: discord.Interaction):
        try:
            if is_attendance_locked(self.date_str):
                await interaction.response.send_message("❌ Attendance for this date is now closed.", ephemeral=True)
                return

            user_id = str(interaction.user.id)
            ensure_day(self.date_str)
 
            # Handle Absent separately as it doesn't involve caps
            if self.role_name == "Absent":
                # Remove from all roles first to prevent duplicates and clear previous signups
                for r in ALL_STORED_ROLES:
                    attendance_data[self.date_str][r] = [
                        x for x in attendance_data[self.date_str].get(r, [])
                        if x.get("user_id") != user_id
                    ]
                lst = attendance_data[self.date_str].setdefault("Absent", [])
                lst.append({"user_id": user_id, "name": interaction.user.display_name})
                attendance_data[self.date_str]["Absent"] = lst
                save_data()
                await edit_announce_and_summary(self.date_str)
                msg = "✅ You have been marked as **Absent**."
                if interaction.response.is_done():
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
                return

            OFFENSIVE_ROLES = ["Shot Caller", "Main Ball", "Flex"]
            
            # Check Cap Logic
            meta = attendance_data[self.date_str].get("_meta", {})
            tier = meta.get("tier", "T1")
            total_cap = get_cap(self.date_str, tier)
            
            def_cap = 5
            off_cap = max(0, total_cap - def_cap)
            
            # Calculate current counts (excluding current user to allow re-signups/swaps)
            current_off_count = 0
            for r in OFFENSIVE_ROLES:
                entries = attendance_data[self.date_str].get(r, [])
                current_off_count += len([e for e in entries if e.get("user_id") != user_id])
            
            current_def_count = len([e for e in attendance_data[self.date_str].get("Def Team", []) if e.get("user_id") != user_id])
            
            # Decide the target role (main role or Reserves)
            target_role = self.role_name

            # 1. Shot Caller Unique Limit
            if self.role_name == "Shot Caller":
                sc_entries = attendance_data[self.date_str].get("Shot Caller", [])
                if any(e.get("user_id") != user_id for e in sc_entries):
                    await interaction.response.send_message("❌ **Shot Caller** role is limited to 1 person and is already taken.", ephemeral=True)
                    return

            # 2. Offensive Roles Cap
            if self.role_name in OFFENSIVE_ROLES:
                if current_off_count >= off_cap:
                    target_role = "Reserves"
            
            # 3. Def Team Cap
            elif self.role_name == "Def Team":
                if current_def_count >= def_cap:
                    target_role = "Reserves"

            # Now that we've determined their destination, remove them from all old roles.
            for r in ALL_STORED_ROLES:
                attendance_data[self.date_str][r] = [
                    x for x in attendance_data[self.date_str].get(r, [])
                    if x.get("user_id") != user_id
                ]

            # --- Special handling for Def Team (if not being sent to reserves) ---
            if self.role_name == "Def Team" and target_role != "Reserves":
                # Show Def Role Selector
                view = discord.ui.View(timeout=120)
                view.add_item(DefRoleSelect(self.date_str))
                msg = "🛡️ Choose your Defense Team Role:"
                await interaction.response.send_message(msg, view=view, ephemeral=True)
                return

            # --- Generic signup for all other roles (and Def Team that fell through to reserves) ---
 
            # Check for saved class preference
            saved_class = attendance_data.get("_users", {}).get(user_id)
            if saved_class:
                lst = attendance_data[self.date_str].setdefault(target_role, [])
                lst.append({"user_id": user_id, "class": saved_class, "name": interaction.user.display_name})
                save_data()
                
                await edit_announce_and_summary(self.date_str)
                
                role_msg = "Reserves" if target_role == "Reserves" else f"**{target_role}**"
                msg = f"✅ You are signed up for {role_msg} as **{saved_class}** (Auto-selected).\nTo change your class, click **🔄 Change Class** below."
                await interaction.response.send_message(msg, ephemeral=True)
                return

            # Normal roles → show class select
            view = discord.ui.View(timeout=120)
            for cls_type, classes in CLASS_TYPES.items():
                if cls_type == "Defense": continue # Skip defense roles for normal class selection
                opts = [discord.SelectOption(label=cls, value=cls, emoji=emoji) for cls, emoji in classes]
                view.add_item(ClassSelect(target_role, self.date_str, cls_type, opts))
 
            role_msg = "Reserves (Cap Reached)" if target_role == "Reserves" else f"**{target_role}**"
            msg = f"Choose your class for {role_msg}:"
            await interaction.response.send_message(msg, view=view, ephemeral=True)
        except Exception as e:
            log.exception("Error in RoleButton.callback: %s", e)
            if interaction.response.is_done():
                await interaction.followup.send("❌ An error occurred.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ An error occurred.", ephemeral=True)

class ChangeClassButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🔄 Change Class", style=discord.ButtonStyle.danger, custom_id="action:change_class", row=1)

    async def callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        users = attendance_data.get("_users", {})
        
        if user_id in users:
            del users[user_id]
            save_data()
            msg = "✅ Your saved class preference has been cleared.\n👉 Click a **Role Button** above to select a new class."
        else:
            msg = "ℹ️ You don't have a saved class preference yet."

        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

class AttendanceView(discord.ui.View):
    def __init__(self, date_str: str):
        super().__init__(timeout=None)
        for r in ROLES:
            self.add_item(RoleButton(r, date_str))
        self.add_item(ChangeClassButton())

# ====== Helpers to post/update ======
async def edit_announce_and_summary(date_str: str) -> None:
    ensure_day(date_str)
    embed = build_embed(date_str)
    view = AttendanceView(date_str) 
    meta = attendance_data[date_str].setdefault("_meta", {})

    # primary
    try:
        ch_id = meta.get("announce_channel_id")
        msg_id = meta.get("announce_message_id")
        if ch_id and msg_id:
            ch = bot.get_channel(int(ch_id))
            if ch:
                msg = await ch.fetch_message(int(msg_id))
                await msg.edit(embed=embed, view=view)
    except Exception:
        log.exception("Failed editing primary announce message")

    # summary
    try:
        s_ch = meta.get("summary_channel_id")
        s_msg = meta.get("summary_message_id")
        if s_ch and s_msg:
            chs = bot.get_channel(int(s_ch))
            if chs:
                msg_s = await chs.fetch_message(int(s_msg))
                await msg_s.edit(content=f"📊 Attendance Summary for **{date_str}**", embed=embed)
    except Exception:
        log.exception("Failed editing summary message")

    save_data()

async def post_attendance(date_str: str) -> Optional[discord.Message]:
    ensure_day(date_str)
    embed = build_embed(date_str)
    view = AttendanceView(date_str)
    meta = attendance_data[date_str].setdefault("_meta", {})

    # primary
    try:
        channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
        if channel is None:
            log.error("Announce channel not found.")
            return None
        msg = await channel.send(content="@everyone", embed=embed, view=view)
        log.info("Attendance posted. Message ID: %s", msg.id)
        meta["posted"] = True
        meta["announce_channel_id"] = channel.id
        meta["announce_message_id"] = msg.id

        # Mention in Guild Chat
        try:
            if (gc := bot.get_channel(GUILD_CHAT_ID)):
                await gc.send(f"<@&{MENTION_ROLE_ID}> Attendance is up! Please sign up in <#{ANNOUNCE_CHANNEL_ID}>")
        except Exception:
            log.warning("Failed to send mention to guild chat")
    except Exception:
        log.exception("Failed posting primary announce")

    # summary in log channel
    try:
        log_chan = bot.get_channel(LOG_CHANNEL_ID)
        if log_chan:
            summary_msg = await log_chan.send(content=f"📊 Attendance Summary for **{date_str}**", embed=embed)
            meta["summarized"] = True
            meta["summary_channel_id"] = log_chan.id
            meta["summary_message_id"] = summary_msg.id
    except Exception:
        log.exception("Failed posting summary")

    save_data()

    # persistent view
    try:
        bot.add_view(AttendanceView(date_str))
    except Exception:
        pass

    return None

async def post_summary(date_str: str) -> Optional[discord.Message]:
    ensure_day(date_str)
    embed = build_embed(date_str)
    meta = attendance_data[date_str].setdefault("_meta", {})
    log_chan = bot.get_channel(LOG_CHANNEL_ID)
    if log_chan is None:
        log.error("Log channel not found for summary.")
        return None

    # Try to edit existing summary message, otherwise send new and store id
    try:
        if meta.get("summary_message_id") and meta.get("summary_channel_id") == log_chan.id:
            msg = await log_chan.fetch_message(int(meta["summary_message_id"]))
            await msg.edit(content=f"📊 Attendance Summary for **{date_str}**", embed=embed)
            meta["summarized"] = True
            save_data()
            return msg
    except Exception:
        log.warning("Could not edit existing summary message, will post a new one.")

    msg = await log_chan.send(content=f"📊 Attendance Summary for **{date_str}**", embed=embed)
    meta["summary_channel_id"] = log_chan.id
    meta["summary_message_id"] = msg.id
    meta["summarized"] = True
    save_data()
    return msg

# ====== Slash commands ======
@app_commands.guilds(discord.Object(id=GUILD_ID))
@bot.tree.command(name="post_now", description="Post today's attendance sign-up to the announcement channel")
async def post_now_cmd(interaction: discord.Interaction):
    date_str = datetime.now(TZ).strftime("%Y-%m-%d")
    try:
        await post_attendance(date_str)
        msg = f"✅ Attendance posted for {date_str}."
    except Exception as e:
        log.exception("Error in /post_now: %s", e)
        msg = f"❌ Failed to post attendance for {date_str}."

    # Always reply
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)

@app_commands.guilds(discord.Object(id=GUILD_ID))
@app_commands.describe(date="Optional: YYYY-MM-DD (default: today)")
@bot.tree.command(name="summary", description="Post or update the attendance summary in the log channel")
async def summary_cmd(interaction: discord.Interaction, date: Optional[str] = None):
    if date is None:
        date = datetime.now(TZ).strftime("%Y-%m-%d")
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        if interaction.response.is_done():
            await interaction.followup.send("❌ Date must be YYYY-MM-DD.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Date must be YYYY-MM-DD.", ephemeral=True)
        return
    msg = await post_summary(date)
    if msg:
        reply = f"✅ Summary for **{date}** posted/updated in the log channel."
    else:
        reply = "❌ Could not post summary (check permissions/channels)."
    if interaction.response.is_done():
        await interaction.followup.send(reply, ephemeral=True)
    else:
        await interaction.response.send_message(reply, ephemeral=True)

@app_commands.guilds(discord.Object(id=GUILD_ID))
@app_commands.describe(tier="Select T1 or T2")
@app_commands.choices(tier=[
    app_commands.Choice(name="T1", value="T1"),
    app_commands.Choice(name="T2", value="T2")
])
@bot.tree.command(name="change_tier", description="Change the attendance cap tier (T1/T2) for today")
async def change_tier_cmd(interaction: discord.Interaction, tier: app_commands.Choice[str]):
    date_str = datetime.now(TZ).strftime("%Y-%m-%d")
    ensure_day(date_str)
    
    attendance_data[date_str]["_meta"]["tier"] = tier.value
    save_data()
    await edit_announce_and_summary(date_str)
    
    msg = f"✅ Tier changed to **{tier.value}** for {date_str}."
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)

@app_commands.guilds(discord.Object(id=GUILD_ID))
@bot.tree.command(name="reset_today", description="Reset today's attendance (clears all signups for today)")
async def reset_today_cmd(interaction: discord.Interaction):
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    attendance_data[today] = {role: [] for role in ROLES}
    attendance_data[today]["_meta"] = {
        "posted": False,
        "announce_channel_id": None,
        "announce_message_id": None,
        "summarized": False,
        "summary_channel_id": None,
        "summary_message_id": None,
        "tier": "T1",
        "locked": False
    }
    attendance_data[today]["Reserves"] = []
    save_data()
    if interaction.response.is_done():
        await interaction.followup.send("✅ Today's attendance has been reset.", ephemeral=True)
    else:
        await interaction.response.send_message("✅ Today's attendance has been reset.", ephemeral=True)

@app_commands.guilds(discord.Object(id=GUILD_ID))
@bot.tree.command(name="post_tomorrow", description="Manually post the attendance sheet for the next day.")
async def post_tomorrow_cmd(interaction: discord.Interaction):
    """Manually posts the attendance for the next day, e.g., if a war ends early."""
    tomorrow_str = (datetime.now(TZ) + timedelta(days=1)).strftime("%Y-%m-%d")
    ensure_day(tomorrow_str)

    meta = attendance_data[tomorrow_str].get("_meta", {})
    if meta.get("posted", False):
        msg = f"ℹ️ Attendance for tomorrow ({tomorrow_str}) has already been posted."
        await interaction.response.send_message(msg, ephemeral=True)
        return

    try:
        await post_attendance(tomorrow_str)
        msg = f"✅ Attendance posted for tomorrow: {tomorrow_str}."
    except Exception as e:
        log.exception("Error in /post_tomorrow: %s", e)
        msg = f"❌ Failed to post attendance for {tomorrow_str}."

    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)

# ====== Scheduler (auto-post/summary) ======
@tasks.loop(minutes=1)
async def scheduler():
    now = datetime.now(TZ)
    date_str = now.strftime("%Y-%m-%d")
    ensure_day(date_str)
    meta = attendance_data.get(date_str, {}).get("_meta", {})

    # Auto post for tomorrow at 10 PM
    if now.hour >= POST_HOUR:
        tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        ensure_day(tomorrow)
        tom_meta = attendance_data[tomorrow]["_meta"]
        if not tom_meta.get("posted", False):
            await post_attendance(tomorrow)

    # Auto summary and lock for today at 9 PM
    if now.hour >= SUMMARY_HOUR:
        if not meta.get("summarized", False):
            await post_summary(date_str)
            meta["summarized"] = True
            save_data()

        if not meta.get("locked", False):
            try:
                ch_id = meta.get("announce_channel_id")
                msg_id = meta.get("announce_message_id")
                if ch_id and msg_id:
                    ch = bot.get_channel(int(ch_id))
                    if ch:
                        msg = await ch.fetch_message(int(msg_id))
                        await msg.edit(view=None)
                        log.info("Locked attendance for %s by removing buttons.", date_str)
                meta["locked"] = True
                save_data()
            except Exception as e:
                log.exception("Failed locking attendance: %s", e)

    # Weekly reset of user preferences (Sunday at 00:00)
    if now.weekday() == 6 and now.hour == 0 and now.minute == 0:
        if attendance_data.get("_users"):
            attendance_data["_users"] = {}
            save_data()
            log.info("🔄 Weekly reset: User class preferences have been cleared.")

# ====== Startup ======
@bot.event
async def on_ready():
    log.info("Bot starting up: loading data and registering views")
    load_data()

    # Add persistent views for any date that already has a posted announce message
    for date_str, data in list(attendance_data.items()):
        try:
            meta = data.get("_meta", {})
            if meta.get("posted", False):
                bot.add_view(AttendanceView(date_str))
        except Exception as e:
            log.exception("Error re-adding view for %s: %s", date_str, e)

    # Also add today's view so buttons work even before posting
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    ensure_day(today)
    bot.add_view(AttendanceView(today))

    # start scheduler
    if not scheduler.is_running():
        scheduler.start()

    # Sync commands: sync to guild (instant) and attempt global sync
    try:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        log.info("✅ Synced commands to guild %s", GUILD_ID)

        # Also attempt global sync (may take up to an hour to propagate)
        await bot.tree.sync()
        log.info("🌍 Synced commands globally")
    except Exception as e:
        log.exception("Failed to sync commands: %s", e)

    log.info("✅ Logged in as %s (id=%s)", bot.user, bot.user.id)

    # Print invite link for easy setup
    invite_url = f"https://discord.com/api/oauth2/authorize?client_id={bot.user.id}&permissions=8&scope=bot%20applications.commands"
    log.info("🔗 If the bot is not in your server, invite it using this link:\n   %s", invite_url)
    
    # Debug: Verify channel visibility
    chk_channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if chk_channel:
        log.info("✅ Announce Channel found: #%s in %s", chk_channel.name, chk_channel.guild.name)
    else:
        log.error("❌ Announce Channel (ID: %s) NOT found. Ensure the ID is correct and the bot is in the server.", ANNOUNCE_CHANNEL_ID)
        log.info("   I am currently in these guilds: %s", ", ".join([f"{g.name} ({g.id})" for g in bot.guilds]))

# ====== Run ======
if __name__ == "__main__":
    bot.run(TOKEN)
