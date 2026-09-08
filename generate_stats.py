import os
import json
import html
from datetime import datetime, timezone, timedelta
import requests

# 1. Konfigurasi Kredensial & Zona Waktu
USER_ID = os.environ.get("HABITICA_USER_ID")
API_TOKEN = os.environ.get("HABITICA_API_TOKEN")
WIB = timezone(timedelta(hours=7))

headers = {
    "x-api-user": USER_ID,
    "x-api-key": API_TOKEN,
    "x-client": f"{USER_ID}-RPGStatsCard"
}

# 2. Inisialisasi Database Lokal
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
    "weekly_top_todos": []
}

if os.path.exists(DB_FILE):
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            db.update(json.load(f))
    except Exception:
        pass

# 3. Logika Reset Mingguan (Senin 06.00 WIB)
now_wib = datetime.now(WIB)
adjusted_time = now_wib - timedelta(hours=6)
cycle_id = f"{adjusted_time.year}-W{adjusted_time.isocalendar()[1]}"

if db["current_cycle_id"] != cycle_id:
    if db["weekly_damage"] > db["peak_weekly_damage"]:
        db["peak_weekly_damage"] = db["weekly_damage"]
    db["weekly_damage"] = 0.0
    db["weekly_top_dailies"] = {}
    db["weekly_top_todos"] = []
    db["current_cycle_id"] = cycle_id

# 4. Ambil Data API Habitica
user_res = requests.get("https://habitica.com/api/v3/user", headers=headers).json().get("data", {})
tasks_res = requests.get("https://habitica.com/api/v3/tasks/user", headers=headers).json().get("data", [])
completed_todos_res = requests.get("https://habitica.com/api/v3/tasks/user?type=completedTodos", headers=headers).json().get("data", [])

profile_name = user_res.get("profile", {}).get("name", "Adventurer")
char_class = user_res.get("stats", {}).get("class", "warrior").lower()
level = user_res.get("stats", {}).get("lvl", 1)
current_gold = user_res.get("stats", {}).get("gp", 0.0)
current_mp = user_res.get("stats", {}).get("mp", 0.0)

if char_class not in db["classes_used"]:
    db["classes_used"].append(char_class)

if current_gold > db["peak_gold"]:
    db["peak_gold"] = current_gold

if db["last_mana"] is not None:
    if current_mp < db["last_mana"]:
        mana_diff = db["last_mana"] - current_mp
        db["total_mana_spent"] += mana_diff
        if mana_diff >= 15:
            db["buffs_cast"] += int(mana_diff // 25) + 1
db["last_mana"] = current_mp

party_quest = user_res.get("party", {}).get("quest", {}).get("progress", {})
current_damage_up = party_quest.get("up", 0.0)

if current_damage_up > db["last_damage_up"]:
    dmg_delta = current_damage_up - db["last_damage_up"]
    db["weekly_damage"] += dmg_delta
    db["all_time_damage"] += dmg_delta
db["last_damage_up"] = current_damage_up

dailies = [t for t in tasks_res if t.get("type") == "daily"]
dailies_due = [t for t in dailies if t.get("isDue", False)]
dailies_done = [t for t in dailies_due if t.get("completed", False)]
due_count = len(dailies_due)
done_count = len(dailies_done)
daily_pct = int((done_count / due_count * 100)) if due_count > 0 else 100

for d in dailies_done:
    d_text = d.get("text", "Daily Task")[:22]
    db["weekly_top_dailies"][d_text] = db["weekly_top_dailies"].get(d_text, 0) + 1

sorted_top_dailies = sorted(db["weekly_top_dailies"].items(), key=lambda x: x[1], reverse=True)[:3]

for todo in completed_todos_res[:3]:
    t_text = todo.get("text", "To-Do Task")[:24]
    if t_text not in db["weekly_top_todos"]:
        db["weekly_top_todos"].append(t_text)
sorted_top_todos = db["weekly_top_todos"][:3]

# Proteksi daftar kosong agar tidak crash
daily_lines = []
for i in range(3):
    if i < len(sorted_top_dailies):
        daily_lines.append(f"{i+1}. {html.escape(sorted_top_dailies[i][0])} ({sorted_top_dailies[i][1]}x)")
    else:
        daily_lines.append(f"{i+1}. -")

todo_lines = []
for i in range(3):
    if i < len(sorted_top_todos):
        todo_lines.append(f"{i+1}. {html.escape(sorted_top_todos[i])}")
    else:
        todo_lines.append(f"{i+1}. -")

todos_active = len([t for t in tasks_res if t.get("type") == "todo"])
todos_cleared = len(completed_todos_res)

habits = [t for t in tasks_res if t.get("type") == "habit"]
pos_clicks = sum(t.get("counterUp", 0) for t in habits)
neg_clicks = sum(t.get("counterDown", 0) for t in habits)
total_clicks = pos_clicks + neg_clicks
habit_ratio = int((pos_clicks / total_clicks * 100)) if total_clicks > 0 else 100

longest_streak = max([t.get("streak", 0) for t in dailies], default=0)

days_elapsed = max(1, (now_wib.weekday() if now_wib.hour >= 6 else (now_wib.weekday() - 1) % 7) + 1)
avg_daily_dmg = db["weekly_damage"] / days_elapsed

with open(DB_FILE, "w", encoding="utf-8") as f:
    json.dump(db, f, indent=2)

quote_text = "Tetap konsisten dan capai tujuanmu hari ini!"
if os.path.exists("quote.txt"):
    with open("quote.txt", "r", encoding="utf-8") as qf:
        lines = [line.strip() for line in qf.readlines() if line.strip()]
        if lines:
            quote_text = " ".join(lines)

CLASS_PALETTES = {
    "mage": {"glow": "#4834D4", "aura": "#686DE0", "name": "ARCHMAGE", "icon": "🔮"},
    "warrior": {"glow": "#EB4D4B", "aura": "#FF7979", "name": "WARRIOR", "icon": "⚔️"},
    "rogue": {"glow": "#F0932B", "aura": "#FFBE76", "name": "SHADOW ROGUE", "icon": "🏹"},
    "healer": {"glow": "#6AB04C", "aura": "#BADC58", "name": "HIGH HEALER", "icon": "🌿"}
}
cls_info = CLASS_PALETTES.get(char_class, CLASS_PALETTES["warrior"])

def badge_style(target_cls):
    return "fill:#F5F6FA; font-weight:bold;" if target_cls in db["classes_used"] else "fill:#57606F; opacity:0.4;"

def fmt(num):
    if num >= 1_000_000:
        return f"{num/1_000_000:.2f}M"
    elif num >= 1_000:
        return f"{num/1_000:.1f}K"
    return f"{int(num)}"

# 5. Render SVG
svg_code = f"""<svg width="380" height="740" viewBox="0 0 380 740" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="auraGlow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="{cls_info['aura']}" stop-opacity="0.6"/>
      <stop offset="100%" stop-color="{cls_info['glow']}" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="barGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#2ED573"/>
      <stop offset="100%" stop-color="#1DD1A1"/>
    </linearGradient>
  </defs>

  <style>
    .header {{ font-family: 'Segoe UI', Roboto, sans-serif; font-weight: bold; fill: #FFFFFF; }}
    .sub {{ font-family: 'Segoe UI', Roboto, sans-serif; font-size: 11px; fill: #A4B0BE; }}
    .label {{ font-family: 'Segoe UI', Roboto, sans-serif; font-size: 10px; fill: #747D8C; text-transform: uppercase; }}
    .val {{ font-family: 'Segoe UI', Roboto, sans-serif; font-size: 13px; font-weight: bold; fill: #F1F2F6; }}
    .gold {{ fill: #FFA502; }}
    .section-title {{ font-family: 'Segoe UI', Roboto, sans-serif; font-size: 11px; font-weight: bold; fill: #ECCC68; letter-spacing: 0.5px; }}
    .list-item {{ font-family: 'Segoe UI', Roboto, sans-serif; font-size: 11px; fill: #CED6E0; }}
  </style>

  <rect width="380" height="740" rx="16" fill="#13141C" stroke="#2F3542" stroke-width="1.5"/>

  <circle cx="48" cy="48" r="32" fill="url(#auraGlow)"/>
  <circle cx="48" cy="48" r="22" fill="#1E202C" stroke="{cls_info['aura']}" stroke-width="1.5"/>
  <text x="48" y="55" font-size="20" text-anchor="middle">{cls_info['icon']}</text>

  <text x="82" y="38" class="header" font-size="15">{html.escape(profile_name[:18])}</text>
  <text x="82" y="53" class="sub">Level {level} • {cls_info['name']}</text>

  <text x="82" y="70" font-size="9" font-family="sans-serif">
    <tspan style="{badge_style('warrior')}">⚔️ WAR </tspan>
    <tspan style="{badge_style('mage')}">🔮 MAG </tspan>
    <tspan style="{badge_style('rogue')}">🏹 ROG </tspan>
    <tspan style="{badge_style('healer')}">🌿 HEA</tspan>
  </text>

  <line x1="16" y1="86" x2="364" y2="86" stroke="#232733" stroke-width="1"/>

  <text x="16" y="105" class="section-title">⚔️ COMBAT &amp; EXPEDITION LOG</text>

  <rect x="16" y="115" width="168" height="42" rx="6" fill="#1C1E2A"/>
  <text x="24" y="130" class="label">Total Dmg (All-Time)</text>
  <text x="24" y="147" class="val">⚔️ {fmt(db['all_time_damage'])}</text>

  <rect x="196" y="115" width="168" height="42" rx="6" fill="#1C1E2A"/>
  <text x="204" y="130" class="label">Weekly Dmg (Sen 06:00)</text>
  <text x="204" y="147" class="val">🗡️ {fmt(db['weekly_damage'])}</text>

  <rect x="16" y="163" width="168" height="42" rx="6" fill="#1C1E2A"/>
  <text x="24" y="178" class="label">Daily Avg Dmg</text>
  <text x="24" y="195" class="val">📊 {fmt(avg_daily_dmg)}/hari</text>

  <rect x="196" y="163" width="168" height="42" rx="6" fill="#1C1E2A"/>
  <text x="204" y="178" class="label">Peak Weekly Record</text>
  <text x="204" y="195" class="val">🔥 {fmt(db['peak_weekly_damage'])}</text>

  <rect x="16" y="211" width="168" height="42" rx="6" fill="#1C1E2A"/>
  <text x="24" y="226" class="label">Bosses Slain</text>
  <text x="24" y="243" class="val">🏆 {db['bosses_slain']} Bosses</text>

  <rect x="196" y="211" width="168" height="42" rx="6" fill="#1C1E2A"/>
  <text x="204" y="226" class="label">Peak Gold Hoarded</text>
  <text x="204" y="243" class="val gold">💰 {fmt(db['peak_gold'])} G</text>

  <text x="20" y="274" class="sub">✨ Buffs Cast to Party: <tspan class="val">{db['buffs_cast']}</tspan></text>
  <text x="20" y="292" class="sub">💧 Total Mana Spent : <tspan class="val">{fmt(db['total_mana_spent'])} MP</tspan> <tspan font-size="9" fill="#747D8C">(All-Time)</tspan></text>

  <line x1="16" y1="308" x2="364" y2="308" stroke="#232733" stroke-width="1"/>

  <text x="16" y="328" class="section-title">📋 PRODUCTIVITY &amp; DISCIPLINE MATRIX</text>

  <text x="16" y="348" class="sub">Dailies Today: <tspan font-weight="bold" fill="#F1F2F6">{done_count}/{due_count} ({daily_pct}%)</tspan></text>
  <rect x="16" y="356" width="348" height="10" rx="5" fill="#242838"/>
  <rect x="16" y="356" width="{int(348 * (daily_pct / 100))}" height="10" rx="5" fill="url(#barGrad)"/>

  <rect x="16" y="376" width="168" height="42" rx="6" fill="#1C1E2A"/>
  <text x="24" y="391" class="label">Bounty Board</text>
  <text x="24" y="408" class="val">🎯 {todos_active} Open / {todos_cleared} Done</text>

  <rect x="196" y="376" width="168" height="42" rx="6" fill="#1C1E2A"/>
  <text x="204" y="391" class="label">Discipline Flame</text>
  <text x="204" y="408" class="val">🔥 {longest_streak} Hari Streak</text>

  <rect x="16" y="424" width="348" height="34" rx="6" fill="#1C1E2A"/>
  <text x="24" y="445" class="sub">Habit Mastery: <tspan class="val">{habit_ratio}% Positif</tspan> ({pos_clicks} 👍 / {neg_clicks} 👎)</text>

  <text x="16" y="482" class="section-title">🏆 TOP 3 DAILIES (Riset Mingguan):</text>
  <text x="24" y="502" class="list-item">{daily_lines[0]}</text>
  <text x="24" y="520" class="list-item">{daily_lines[1]}</text>
  <text x="24" y="538" class="list-item">{daily_lines[2]}</text>

  <text x="16" y="568" class="section-title">🎯 TOP 3 COMPLETED TO-DOS (Mingguan):</text>
  <text x="24" y="588" class="list-item">{todo_lines[0]}</text>
  <text x="24" y="606" class="list-item">{todo_lines[1]}</text>
  <text x="24" y="624" class="list-item">{todo_lines[2]}</text>

  <line x1="16" y1="642" x2="364" y2="642" stroke="#232733" stroke-width="1"/>

  <rect x="16" y="654" width="348" height="66" rx="8" fill="#181A24" stroke="#4834D4" stroke-width="0.8"/>
  <text x="28" y="672" font-family="'Georgia', serif" font-size="10" font-weight="bold" fill="#ECCC68" letter-spacing="0.5px">📜 SCROLL OF INSIGHT</text>
  <text x="28" y="692" font-family="'Georgia', serif" font-size="11" font-style="italic" fill="#DCDDE1">
    {html.escape(quote_text[:90])}
  </text>
</svg>"""

with open("profile-stats.svg", "w", encoding="utf-8") as f:
    f.write(svg_code)

print("Status card SVG and database.json successfully updated.")
