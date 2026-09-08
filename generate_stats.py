import os
import json
import html
import textwrap
from datetime import datetime, timezone, timedelta
import requests

# 1. Credentials & Timezone (WIB / UTC+7)
USER_ID = os.environ.get("HABITICA_USER_ID")
API_TOKEN = os.environ.get("HABITICA_API_TOKEN")
WIB = timezone(timedelta(hours=7))

headers = {
    "x-api-user": USER_ID,
    "x-api-key": API_TOKEN,
    "x-client": f"{USER_ID}-RPGStatsCard"
}

# 2. Local Database Initialization
DB_FILE = "database.json"
db = {
    "current_cycle_id": "",
    "classes_used": [],
    "peak_gold": 0.0,
    "total_mana_spent": 0.0,
    "last_mana": None,
    "buffs_cast": 0,
    "bosses_slain": 0,
    "all_time_damage": 0.0,
    "weekly_damage": 0.0,
    "peak_weekly_damage": 0.0,
    "last_damage_up": 0.0,
    "weekly_top_dailies": {},
    "last_daily_date": "",
    "daily_habit_baseline": 0,
    "total_dailies_cleared": 0
}

if os.path.exists(DB_FILE):
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            db.update(json.load(f))
    except Exception:
        pass

# 3. Weekly Reset Cycle (Monday 06:00 AM WIB)
now_wib = datetime.now(WIB)
today_str = now_wib.strftime("%Y-%m-%d")
adjusted_time = now_wib - timedelta(hours=6)
cycle_id = f"{adjusted_time.year}-W{adjusted_time.isocalendar()[1]}"

if db["current_cycle_id"] != cycle_id:
    if db["weekly_damage"] > db["peak_weekly_damage"]:
        db["peak_weekly_damage"] = db["weekly_damage"]
    db["weekly_damage"] = 0.0
    db["weekly_top_dailies"] = {}
    db["current_cycle_id"] = cycle_id

# 4. Fetch Habitica API Data
user_res = requests.get("https://habitica.com/api/v3/user", headers=headers).json().get("data", {})
tasks_res = requests.get("https://habitica.com/api/v3/tasks/user", headers=headers).json().get("data", [])
completed_todos_res = requests.get("https://habitica.com/api/v3/tasks/user?type=completedTodos", headers=headers).json().get("data", [])

if not isinstance(tasks_res, list):
    tasks_res = []
if not isinstance(completed_todos_res, list):
    completed_todos_res = []

# Hero Identity & Core Stats
profile_name = user_res.get("profile", {}).get("name", "Adventurer")
char_class = user_res.get("stats", {}).get("class", "warrior").lower()
level = user_res.get("stats", {}).get("lvl", 1)
current_gold = user_res.get("stats", {}).get("gp", 0.0)
current_mp = user_res.get("stats", {}).get("mp", 0.0)

if char_class not in db["classes_used"]:
    db["classes_used"].append(char_class)

if current_gold > db["peak_gold"]:
    db["peak_gold"] = current_gold

# Mana Tracking & Buff Casts
if db["last_mana"] is not None:
    if current_mp < db["last_mana"]:
        mana_diff = db["last_mana"] - current_mp
        db["total_mana_spent"] += mana_diff
        if mana_diff >= 15:
            db["buffs_cast"] += int(mana_diff // 25) + 1
db["last_mana"] = current_mp

# Combat Damage Calculation
party_quest = user_res.get("party", {}).get("quest", {}).get("progress", {})
current_damage_up = party_quest.get("up", 0.0)

if current_damage_up > db["last_damage_up"]:
    dmg_delta = current_damage_up - db["last_damage_up"]
    db["weekly_damage"] += dmg_delta
    db["all_time_damage"] += dmg_delta
db["last_damage_up"] = current_damage_up

# Dailies Breakdown
dailies = [t for t in tasks_res if t.get("type") == "daily"]
dailies_due = [t for t in dailies if t.get("isDue", False)]
dailies_done = [t for t in dailies_due if t.get("completed", False)]
due_count = len(dailies_due)
done_count = len(dailies_done)
daily_pct = int((done_count / due_count * 100)) if due_count > 0 else 100

for d in dailies_done:
    d_text = d.get("text", "Daily Task")[:24]
    db["weekly_top_dailies"][d_text] = db["weekly_top_dailies"].get(d_text, 0) + 1

sorted_top_dailies = sorted(db["weekly_top_dailies"].items(), key=lambda x: x[1], reverse=True)[:3]

# Habits Breakdown
habits = [t for t in tasks_res if t.get("type") == "habit"]
pos_clicks = sum(t.get("counterUp", 0) for t in habits)
neg_clicks = sum(t.get("counterDown", 0) for t in habits)
total_clicks = pos_clicks + neg_clicks
habit_ratio = int((pos_clicks / total_clicks * 100)) if total_clicks > 0 else 100

sorted_top_habits = sorted(habits, key=lambda h: h.get("counterUp", 0), reverse=True)[:3]

# Daily Completions Tracking (Today)
if db.get("last_daily_date") != today_str:
    db["last_daily_date"] = today_str
    db["daily_habit_baseline"] = pos_clicks

habits_today_count = max(0, pos_clicks - db.get("daily_habit_baseline", pos_clicks))

todos_today_count = 0
for td in completed_todos_res:
    dc = td.get("dateCompleted")
    if dc:
        try:
            utc_dt = datetime.fromisoformat(dc.replace("Z", "+00:00"))
            if utc_dt.astimezone(WIB).strftime("%Y-%m-%d") == today_str:
                todos_today_count += 1
        except Exception:
            pass

todos_active = len([t for t in tasks_res if t.get("type") == "todo"])
todos_cleared_total = len(completed_todos_res)
grand_total_completed = pos_clicks + todos_cleared_total + done_count

# Streaks & Damage Averages
longest_streak = max([t.get("streak", 0) for t in dailies], default=0)
days_elapsed = max(1, (now_wib.weekday() if now_wib.hour >= 6 else (now_wib.weekday() - 1) % 7) + 1)
avg_daily_dmg = db["weekly_damage"] / days_elapsed

# Save database.json
with open(DB_FILE, "w", encoding="utf-8") as f:
    json.dump(db, f, indent=2)

# Quote Wrapping Logic
quote_text = "Small daily disciplines lead to monumental achievements over time."
if os.path.exists("quote.txt"):
    with open("quote.txt", "r", encoding="utf-8") as qf:
        lines = [line.strip() for line in qf.readlines() if line.strip()]
        if lines:
            quote_text = " ".join(lines)

quote_lines = textwrap.wrap(quote_text, width=42)[:3]

# Class Theming: Colors, Glow & Text
CLASS_PALETTES = {
    "mage": {"glow": "#3b82f6", "aura": "#60a5fa", "bg": "#172554", "name": "ARCHMAGE", "icon": "🔮"},
    "warrior": {"glow": "#ef4444", "aura": "#f87171", "bg": "#450a0a", "name": "WARRIOR", "icon": "⚔️"},
    "rogue": {"glow": "#f59e0b", "aura": "#fbbf24", "bg": "#451a03", "name": "SHADOW ROGUE", "icon": "🏹"},
    "healer": {"glow": "#10b981", "aura": "#34d399", "bg": "#064e3b", "name": "HIGH HEALER", "icon": "🌿"}
}
cls_info = CLASS_PALETTES.get(char_class, CLASS_PALETTES["warrior"])

def badge_style(target_cls):
    return "fill:#f8fafc; font-weight:bold;" if target_cls in db["classes_used"] else "fill:#475569; opacity:0.35;"

def fmt(num):
    if num >= 1_000_000:
        return f"{num/1_000_000:.2f}M"
    elif num >= 1_000:
        return f"{num/1_000:.1f}K"
    return f"{int(num)}"

# Safe lines generation for Habits
habit_lines = []
for i in range(3):
    if i < len(sorted_top_habits):
        h_name = sorted_top_habits[i].get("text", "Habit")
        h_name = (h_name[:24] + "..") if len(h_name) > 26 else h_name
        h_cnt = sorted_top_habits[i].get("counterUp", 0)
        habit_lines.append(f"{i+1}. {html.escape(h_name)} (+{h_cnt})")
    else:
        habit_lines.append(f"{i+1}. -")

# Safe lines generation for Dailies
daily_lines = []
for i in range(3):
    if i < len(sorted_top_dailies):
        d_name = sorted_top_dailies[i][0]
        d_name = (d_name[:24] + "..") if len(d_name) > 26 else d_name
        d_cnt = sorted_top_dailies[i][1]
        daily_lines.append(f"{i+1}. {html.escape(d_name)} ({d_cnt}x)")
    else:
        daily_lines.append(f"{i+1}. -")

# 5. Render Responsive SVG (Mobile-First 380px Canvas with Enhanced RPG Theme)
svg_code = f"""<svg width="380" height="920" viewBox="0 0 380 920" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <!-- Multi-Layer Radial Aura -->
    <radialGradient id="auraOuter" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="{cls_info['aura']}" stop-opacity="0.85"/>
      <stop offset="60%" stop-color="{cls_info['glow']}" stop-opacity="0.45"/>
      <stop offset="100%" stop-color="{cls_info['glow']}" stop-opacity="0"/>
    </radialGradient>
    
    <!-- Rich RPG Slate Fantasy Canvas Gradient -->
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#1e2235"/>
      <stop offset="45%" stop-color="#141724"/>
      <stop offset="100%" stop-color="#0d0f18"/>
    </linearGradient>

    <!-- Card Box Surface Gradient -->
    <linearGradient id="cardGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1f2537"/>
      <stop offset="100%" stop-color="#161a29"/>
    </linearGradient>

    <!-- Emerald Progress Gradient -->
    <linearGradient id="barGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#10b981"/>
      <stop offset="100%" stop-color="#34d399"/>
    </linearGradient>
  </defs>

  <style>
    .header {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-weight: 800; fill: #ffffff; letter-spacing: 0.3px; }}
    .sub {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 11px; fill: #94a3b8; }}
    .label {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 9.5px; fill: #718096; text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px; }}
    .val {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 13.5px; font-weight: bold; fill: #f8fafc; }}
    .gold {{ fill: #fbbf24; }}
    .section-title {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 10.5px; font-weight: bold; fill: #facc15; letter-spacing: 0.7px; text-transform: uppercase; }}
    .list-item {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 11px; fill: #cbd5e1; }}
    .emoji-icon {{ font-family: 'Apple Color Emoji', 'Segoe UI Emoji', 'Noto Color Emoji', sans-serif; }}
  </style>

  <!-- Canvas Border & Background -->
  <rect width="380" height="920" rx="18" fill="url(#bgGrad)" stroke="#334155" stroke-width="1.8"/>

  <!-- ================= HEADER SECTION ================= -->
  <!-- Wide Radiant Aura Layer -->
  <circle cx="46" cy="46" r="38" fill="url(#auraOuter)"/>
  
  <!-- Outer Aura Energy Ring -->
  <rect x="16" y="16" width="60" height="60" rx="14" fill="none" stroke="{cls_info['aura']}" stroke-width="1.2" stroke-dasharray="4 2" opacity="0.65"/>

  <!-- RPG Class Square Badge -->
  <rect x="21" y="21" width="50" height="50" rx="11" fill="{cls_info['bg']}" stroke="{cls_info['aura']}" stroke-width="2"/>
  
  <!-- Class Icon -->
  <text x="46" y="47" font-size="24" text-anchor="middle" dominant-baseline="central" class="emoji-icon">{cls_info['icon']}</text>

  <!-- Name & Class Title -->
  <text x="82" y="38" class="header" font-size="15">{html.escape(profile_name[:16])}</text>
  <text x="82" y="53" class="sub">Level {level} • <tspan fill="{cls_info['aura']}" font-weight="bold">{cls_info['name']}</tspan></text>

  <!-- Class Badges Row -->
  <text x="82" y="68" font-size="9.5" class="emoji-icon">
    <tspan style="{badge_style('warrior')}">⚔️ WAR </tspan>
    <tspan style="{badge_style('mage')}">🔮 MAG </tspan>
    <tspan style="{badge_style('rogue')}">🏹 ROG </tspan>
    <tspan style="{badge_style('healer')}">🌿 HEA</tspan>
  </text>

  <line x1="16" y1="84" x2="364" y2="84" stroke="#2a324b" stroke-width="1.2"/>

  <!-- ================= COMBAT & EXPEDITION ================= -->
  <text x="16" y="102" class="section-title">⚔️ COMBAT &amp; EXPEDITION LOG</text>

  <!-- Row 1: Total Dmg & Weekly Dmg -->
  <rect x="16" y="110" width="168" height="42" rx="8" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="24" y="124" class="label">Total Dmg (All-Time)</text>
  <text x="24" y="142" class="val emoji-icon">⚔️ {fmt(db['all_time_damage'])}</text>

  <rect x="196" y="110" width="168" height="42" rx="8" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="204" y="124" class="label">Weekly Dmg (Reset Mon)</text>
  <text x="204" y="142" class="val emoji-icon">🗡️ {fmt(db['weekly_damage'])}</text>

  <!-- Row 2: Daily Avg & Peak Weekly -->
  <rect x="16" y="158" width="168" height="42" rx="8" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="24" y="172" class="label">Daily Avg Dmg</text>
  <text x="24" y="190" class="val emoji-icon">📊 {fmt(avg_daily_dmg)}/day</text>

  <rect x="196" y="158" width="168" height="42" rx="8" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="204" y="172" class="label">Peak Weekly Record</text>
  <text x="204" y="190" class="val emoji-icon">🔥 {fmt(db['peak_weekly_damage'])}</text>

  <!-- Row 3: Bosses Slain & Peak Gold -->
  <rect x="16" y="206" width="168" height="42" rx="8" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="24" y="220" class="label">Bosses Slain</text>
  <text x="24" y="238" class="val emoji-icon">🏆 {db['bosses_slain']} Bosses</text>

  <rect x="196" y="206" width="168" height="42" rx="8" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="204" y="220" class="label">Peak Gold Hoarded</text>
  <text x="204" y="238" class="val gold emoji-icon">💰 {fmt(db['peak_gold'])} G</text>

  <!-- Consolidated Buff & Mana Card -->
  <rect x="16" y="254" width="348" height="34" rx="8" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="24" y="275" class="sub emoji-icon">✨ Buffs: <tspan class="val">{db['buffs_cast']}</tspan> Casts  •  💧 Mana Spent: <tspan class="val">{fmt(db['total_mana_spent'])} MP</tspan></text>

  <line x1="16" y1="298" x2="364" y2="298" stroke="#2a324b" stroke-width="1.2"/>

  <!-- ================= PRODUCTIVITY MATRIX ================= -->
  <text x="16" y="318" class="section-title">📋 PRODUCTIVITY &amp; DISCIPLINE MATRIX</text>

  <!-- Dailies Today Header & Bar -->
  <text x="16" y="338" class="sub">Dailies Today: <tspan font-weight="bold" fill="#f8fafc">{done_count}/{due_count} ({daily_pct}%)</tspan></text>
  <rect x="16" y="346" width="348" height="10" rx="5" fill="#171b29"/>
  <rect x="16" y="346" width="{int(348 * (daily_pct / 100))}" height="10" rx="5" fill="url(#barGrad)"/>

  <!-- Repositioned Habit Mastery -->
  <rect x="16" y="364" width="348" height="32" rx="7" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="24" y="384" class="sub emoji-icon">Habit Mastery: <tspan class="val">{habit_ratio}% Positive</tspan> ({pos_clicks} 👍 / {neg_clicks} 👎)</text>

  <!-- Daily Completions & Total Aggregates (Grid 4) -->
  <rect x="16" y="402" width="82" height="42" rx="7" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="22" y="416" class="label">Habits Today</text>
  <text x="22" y="434" class="val emoji-icon">✨ {habits_today_count}</text>

  <rect x="104" y="402" width="82" height="42" rx="7" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="110" y="416" class="label">Dailies Today</text>
  <text x="110" y="434" class="val emoji-icon">📋 {done_count}</text>

  <rect x="194" y="402" width="82" height="42" rx="7" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="200" y="416" class="label">To-Dos Today</text>
  <text x="200" y="434" class="val emoji-icon">🎯 {todos_today_count}</text>

  <rect x="282" y="402" width="82" height="42" rx="7" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="288" y="416" class="label">All Completed</text>
  <text x="288" y="434" class="val gold emoji-icon">⭐ {fmt(grand_total_completed)}</text>

  <!-- Bounty Board & Discipline Flame -->
  <rect x="16" y="450" width="168" height="42" rx="8" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="24" y="464" class="label">Bounty Board</text>
  <text x="24" y="482" class="val emoji-icon">🎯 {todos_active} Open / {todos_cleared_total} Cleared</text>

  <rect x="196" y="450" width="168" height="42" rx="8" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="204" y="464" class="label">Discipline Flame</text>
  <text x="204" y="482" class="val emoji-icon">🔥 {longest_streak} Days Streak</text>

  <!-- Dedicated Box: Top 3 Habits -->
  <rect x="16" y="500" width="348" height="88" rx="8" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="26" y="518" class="section-title emoji-icon">🔥 TOP 3 HABITS (MOST ACTIVE)</text>
  <text x="26" y="538" class="list-item">{habit_lines[0]}</text>
  <text x="26" y="556" class="list-item">{habit_lines[1]}</text>
  <text x="26" y="574" class="list-item">{habit_lines[2]}</text>

  <!-- Dedicated Box: Top 3 Dailies -->
  <rect x="16" y="596" width="348" height="88" rx="8" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="26" y="614" class="section-title emoji-icon">🏆 TOP 3 DAILIES (WEEKLY CONSISTENCY)</text>
  <text x="26" y="634" class="list-item">{daily_lines[0]}</text>
  <text x="26" y="652" class="list-item">{daily_lines[1]}</text>
  <text x="26" y="670" class="list-item">{daily_lines[2]}</text>

  <line x1="16" y1="696" x2="364" y2="696" stroke="#2a324b" stroke-width="1.2"/>

  <!-- ================= SCROLL OF INSIGHT ================= -->
  <rect x="16" y="708" width="348" height="86" rx="9" fill="#131929" stroke="#3b82f6" stroke-width="1.2"/>
  <text x="28" y="728" font-family="'Georgia', serif" font-size="10.5" font-weight="bold" fill="#facc15" letter-spacing="0.5px">📜 SCROLL OF INSIGHT</text>
  <text x="28" y="748" font-family="'Georgia', serif" font-size="11" font-style="italic" fill="#e2e8f0">
    <tspan x="28" dy="0">{html.escape(quote_lines[0]) if len(quote_lines) > 0 else ''}</tspan>
    <tspan x="28" dy="16">{html.escape(quote_lines[1]) if len(quote_lines) > 1 else ''}</tspan>
    <tspan x="28" dy="16">{html.escape(quote_lines[2]) if len(quote_lines) > 2 else ''}</tspan>
  </text>
</svg>"""

with open("profile-stats.svg", "w", encoding="utf-8") as f:
    f.write(svg_code)

print("RPG status card SVG successfully regenerated with enhanced design.")
