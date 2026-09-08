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

# Mana Tracking & Estimated Buff Casts
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

# Habits Breakdown & Top 3 Habits
habits = [t for t in tasks_res if t.get("type") == "habit"]
pos_clicks = sum(t.get("counterUp", 0) for t in habits)
neg_clicks = sum(t.get("counterDown", 0) for t in habits)
total_clicks = pos_clicks + neg_clicks
habit_ratio = int((pos_clicks / total_clicks * 100)) if total_clicks > 0 else 100

sorted_top_habits = sorted(habits, key=lambda h: h.get("counterUp", 0), reverse=True)[:3]

# Daily Completions Tracking (Today in WIB)
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

# Discipline Streak & Damage Averages
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

# Class Palettes & Theming
CLASS_PALETTES = {
    "mage": {"glow": "#3b82f6", "aura": "#60a5fa", "name": "ARCHMAGE", "icon": "🔮"},
    "warrior": {"glow": "#ef4444", "aura": "#f87171", "name": "WARRIOR", "icon": "⚔️"},
    "rogue": {"glow": "#f59e0b", "aura": "#fbbf24", "name": "SHADOW ROGUE", "icon": "🏹"},
    "healer": {"glow": "#10b981", "aura": "#34d399", "name": "HIGH HEALER", "icon": "🌿"}
}
cls_info = CLASS_PALETTES.get(char_class, CLASS_PALETTES["warrior"])

def badge_style(target_cls):
    return "fill:#f3f4f6; font-weight:bold;" if target_cls in db["classes_used"] else "fill:#4b5563; opacity:0.35;"

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
        h_name = (h_name[:26] + "..") if len(h_name) > 28 else h_name
        h_cnt = sorted_top_habits[i].get("counterUp", 0)
        habit_lines.append(f"{i+1}. {html.escape(h_name)} (+{h_cnt})")
    else:
        habit_lines.append(f"{i+1}. -")

# Safe lines generation for Dailies
daily_lines = []
for i in range(3):
    if i < len(sorted_top_dailies):
        d_name = sorted_top_dailies[i][0]
        d_name = (d_name[:26] + "..") if len(d_name) > 28 else d_name
        d_cnt = sorted_top_dailies[i][1]
        daily_lines.append(f"{i+1}. {html.escape(d_name)} ({d_cnt}x)")
    else:
        daily_lines.append(f"{i+1}. -")

# 5. Render Responsive SVG (Mobile-First 380px Canvas)
svg_code = f"""<svg width="380" height="920" viewBox="0 0 380 920" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="auraGlow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="{cls_info['aura']}" stop-opacity="0.8">
        <animate attributeName="stop-opacity" values="0.8;0.35;0.8" dur="3s" repeatCount="indefinite"/>
      </stop>
      <stop offset="100%" stop-color="{cls_info['glow']}" stop-opacity="0"/>
    </radialGradient>
    
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#141824"/>
      <stop offset="50%" stop-color="#0e111a"/>
      <stop offset="100%" stop-color="#080a10"/>
    </linearGradient>

    <linearGradient id="barGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#10b981"/>
      <stop offset="100%" stop-color="#34d399"/>
    </linearGradient>
  </defs>

  <style>
    .header {{ font-family: 'Segoe UI', Roboto, sans-serif; font-weight: bold; fill: #ffffff; }}
    .sub {{ font-family: 'Segoe UI', Roboto, sans-serif; font-size: 11px; fill: #94a3b8; }}
    .label {{ font-family: 'Segoe UI', Roboto, sans-serif; font-size: 9.5px; fill: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }}
    .val {{ font-family: 'Segoe UI', Roboto, sans-serif; font-size: 13px; font-weight: bold; fill: #f8fafc; }}
    .gold {{ fill: #f59e0b; }}
    .section-title {{ font-family: 'Segoe UI', Roboto, sans-serif; font-size: 10.5px; font-weight: bold; fill: #fbbf24; letter-spacing: 0.6px; text-transform: uppercase; }}
    .list-item {{ font-family: 'Segoe UI', Roboto, sans-serif; font-size: 11px; fill: #cbd5e1; }}
  </style>

  <rect width="380" height="920" rx="18" fill="url(#bgGrad)" stroke="#1e293b" stroke-width="1.5"/>

  <rect x="14" y="14" width="60" height="60" rx="14" fill="url(#auraGlow)"/>
  
  <rect x="20" y="20" width="48" height="48" rx="10" fill="#1e2433" stroke="{cls_info['aura']}" stroke-width="1.8"/>
  <text x="44" y="52" font-size="22" text-anchor="middle">{cls_info['icon']}</text>

  <text x="78" y="38" class="header" font-size="15">{html.escape(profile_name[:16])}</text>
  <text x="78" y="53" class="sub">Level {level} • {cls_info['name']}</text>

  <text x="78" y="68" font-size="9" font-family="sans-serif">
    <tspan style="{badge_style('warrior')}">⚔️ WAR </tspan>
    <tspan style="{badge_style('mage')}">🔮 MAG </tspan>
    <tspan style="{badge_style('rogue')}">🏹 ROG </tspan>
    <tspan style="{badge_style('healer')}">🌿 HEA</tspan>
  </text>

  <line x1="16" y1="82" x2="364" y2="82" stroke="#1e293b" stroke-width="1"/>

  <text x="16" y="100" class="section-title">⚔️ COMBAT &amp; EXPEDITION LOG</text>

  <rect x="16" y="108" width="168" height="42" rx="7" fill="#131926" stroke="#1e2738" stroke-width="1"/>
  <text x="24" y="122" class="label">Total Dmg (All-Time)</text>
  <text x="24" y="140" class="val">⚔️ {fmt(db['all_time_damage'])}</text>

  <rect x="196" y="108" width="168" height="42" rx="7" fill="#131926" stroke="#1e2738" stroke-width="1"/>
  <text x="204" y="122" class="label">Weekly Dmg (Reset Mon)</text>
  <text x="204" y="140" class="val">🗡️ {fmt(db['weekly_damage'])}</text>

  <rect x="16" y="156" width="168" height="42" rx="7" fill="#131926" stroke="#1e2738" stroke-width="1"/>
  <text x="24" y="170" class="label">Daily Avg Dmg</text>
  <text x="24" y="188" class="val">📊 {fmt(avg_daily_dmg)}/day</text>

  <rect x="196" y="156" width="168" height="42" rx="7" fill="#131926" stroke="#1e2738" stroke-width="1"/>
  <text x="204" y="170" class="label">Peak Weekly Record</text>
  <text x="204" y="188" class="val">🔥 {fmt(db['peak_weekly_damage'])}</text>

  <rect x="16" y="204" width="168" height="42" rx="7" fill="#131926" stroke="#1e2738" stroke-width="1"/>
  <text x="24" y="218" class="label">Bosses Slain</text>
  <text x="24" y="236" class="val">🏆 {db['bosses_slain']} Bosses</text>

  <rect x="196" y="204" width="168" height="42" rx="7" fill="#131926" stroke="#1e2738" stroke-width="1"/>
  <text x="204" y="218" class="label">Peak Gold Hoarded</text>
  <text x="204" y="236" class="val gold">💰 {fmt(db['peak_gold'])} G</text>

  <rect x="16" y="252" width="348" height="34" rx="7" fill="#151a28" stroke="#1e293b" stroke-width="1"/>
  <text x="24" y="273" class="sub">✨ Buffs: <tspan class="val">{db['buffs_cast']}</tspan> Casts  •  💧 Mana Spent: <tspan class="val">{fmt(db['total_mana_spent'])} MP</tspan></text>

  <line x1="16" y1="298" x2="364" y2="298" stroke="#1e293b" stroke-width="1"/>

  <text x="16" y="318" class="section-title">📋 PRODUCTIVITY &amp; DISCIPLINE MATRIX</text>

  <text x="16" y="338" class="sub">Dailies Today: <tspan font-weight="bold" fill="#f8fafc">{done_count}/{due_count} ({daily_pct}%)</tspan></text>
  <rect x="16" y="346" width="348" height="10" rx="5" fill="#1e2433"/>
  <rect x="16" y="346" width="{int(348 * (daily_pct / 100))}" height="10" rx="5" fill="url(#barGrad)"/>

  <rect x="16" y="364" width="348" height="32" rx="6" fill="#131926" stroke="#1e2738" stroke-width="1"/>
  <text x="24" y="384" class="sub">Habit Mastery: <tspan class="val">{habit_ratio}% Positive</tspan> ({pos_clicks} 👍 / {neg_clicks} 👎)</text>

  <rect x="16" y="402" width="82" height="42" rx="6" fill="#131926" stroke="#1e2738" stroke-width="1"/>
  <text x="22" y="416" class="label">Habits Today</text>
  <text x="22" y="434" class="val">✨ {habits_today_count}</text>

  <rect x="104" y="402" width="82" height="42" rx="6" fill="#131926" stroke="#1e2738" stroke-width="1"/>
  <text x="110" y="416" class="label">Dailies Today</text>
  <text x="110" y="434" class="val">📋 {done_count}</text>

  <rect x="194" y="402" width="82" height="42" rx="6" fill="#131926" stroke="#1e2738" stroke-width="1"/>
  <text x="200" y="416" class="label">To-Dos Today</text>
  <text x="200" y="434" class="val">🎯 {todos_today_count}</text>

  <rect x="282" y="402" width="82" height="42" rx="6" fill="#131926" stroke="#1e2738" stroke-width="1"/>
  <text x="288" y="416" class="label">All Completed</text>
  <text x="288" y="434" class="val gold">⭐ {fmt(grand_total_completed)}</text>

  <rect x="16" y="450" width="168" height="42" rx="7" fill="#131926" stroke="#1e2738" stroke-width="1"/>
  <text x="24" y="464" class="label">Bounty Board</text>
  <text x="24" y="482" class="val">🎯 {todos_active} Open / {todos_cleared_total} Cleared</text>

  <rect x="196" y="450" width="168" height="42" rx="7" fill="#131926" stroke="#1e2738" stroke-width="1"/>
  <text x="204" y="464" class="label">Discipline Flame</text>
  <text x="204" y="482" class="val">🔥 {longest_streak} Days Streak</text>

  <rect x="16" y="500" width="348" height="88" rx="8" fill="#131926" stroke="#1e2738" stroke-width="1"/>
  <text x="26" y="518" class="section-title">🔥 TOP 3 HABITS (MOST ACTIVE)</text>
  <text x="26" y="538" class="list-item">{habit_lines[0]}</text>
  <text x="26" y="556" class="list-item">{habit_lines[1]}</text>
  <text x="26" y="574" class="list-item">{habit_lines[2]}</text>

  <rect x="16" y="596" width="348" height="88" rx="8" fill="#131926" stroke="#1e2738" stroke-width="1"/>
  <text x="26" y="614" class="section-title">🏆 TOP 3 DAILIES (WEEKLY CONSISTENCY)</text>
  <text x="26" y="634" class="list-item">{daily_lines[0]}</text>
  <text x="26" y="652" class="list-item">{daily_lines[1]}</text>
  <text x="26" y="670" class="list-item">{daily_lines[2]}</text>

  <line x1="16" y1="696" x2="364" y2="696" stroke="#1e293b" stroke-width="1"/>

  <rect x="16" y="708" width="348" height="86" rx="9" fill="#141926" stroke="#3b82f6" stroke-width="0.9"/>
  <text x="28" y="728" font-family="'Georgia', serif" font-size="10.5" font-weight="bold" fill="#fbbf24" letter-spacing="0.5px">📜 SCROLL OF INSIGHT</text>
  <text x="28" y="748" font-family="'Georgia', serif" font-size="11" font-style="italic" fill="#e2e8f0">
    <tspan x="28" dy="0">{html.escape(quote_lines[0]) if len(quote_lines) > 0 else ''}</tspan>
    <tspan x="28" dy="16">{html.escape(quote_lines[1]) if len(quote_lines) > 1 else ''}</tspan>
    <tspan x="28" dy="16">{html.escape(quote_lines[2]) if len(quote_lines) > 2 else ''}</tspan>
  </text>
</svg>"""

with open("profile-stats.svg", "w", encoding="utf-8") as f:
    f.write(svg_code)

print("RPG status card SVG successfully regenerated with enhanced design.")
