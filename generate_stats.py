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

# Mana Tracking & Buffs
if db["last_mana"] is not None:
    if current_mp < db["last_mana"]:
        mana_diff = db["last_mana"] - current_mp
        db["total_mana_spent"] += mana_diff
        if mana_diff >= 15:
            db["buffs_cast"] += int(mana_diff // 25) + 1
db["last_mana"] = current_mp

# Combat Damage
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

# Daily Tracking (Today)
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

# Streaks & Averages
longest_streak = max([t.get("streak", 0) for t in dailies], default=0)
days_elapsed = max(1, (now_wib.weekday() if now_wib.hour >= 6 else (now_wib.weekday() - 1) % 7) + 1)
avg_daily_dmg = db["weekly_damage"] / days_elapsed

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

# Fantasy RPG Theme Palettes
CLASS_CONFIG = {
    "warrior": {"secondary": "#fb7185", "bg": "#4c0519", "name": "WARRIOR"},
    "mage": {"secondary": "#60a5fa", "bg": "#172554", "name": "ARCHMAGE"},
    "rogue": {"secondary": "#fbbf24", "bg": "#451a03", "name": "SHADOW ROGUE"},
    "healer": {"secondary": "#34d399", "bg": "#064e3b", "name": "HIGH HEALER"}
}
cfg = CLASS_CONFIG.get(char_class, CLASS_CONFIG["warrior"])

def fmt(num):
    if num >= 1_000_000:
        return f"{num/1_000_000:.2f}M"
    elif num >= 1_000:
        return f"{num/1_000:.1f}K"
    return f"{int(num)}"

habit_lines = []
for i in range(3):
    if i < len(sorted_top_habits):
        h_name = sorted_top_habits[i].get("text", "Habit")
        h_name = (h_name[:24] + "..") if len(h_name) > 26 else h_name
        h_cnt = sorted_top_habits[i].get("counterUp", 0)
        habit_lines.append(f"{i+1}. {html.escape(h_name)} (+{h_cnt})")
    else:
        habit_lines.append(f"{i+1}. -")

daily_lines = []
for i in range(3):
    if i < len(sorted_top_dailies):
        d_name = sorted_top_dailies[i][0]
        d_name = (d_name[:24] + "..") if len(d_name) > 26 else d_name
        d_cnt = sorted_top_dailies[i][1]
        daily_lines.append(f"{i+1}. {html.escape(d_name)} ({d_cnt}x)")
    else:
        daily_lines.append(f"{i+1}. -")

# 5. Render Responsive Epic Fantasy SVG
svg_code = f"""<svg width="380" height="930" viewBox="0 0 380 930" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#181c2e"/>
      <stop offset="40%" stop-color="#101424"/>
      <stop offset="100%" stop-color="#0a0c16"/>
    </linearGradient>

    <linearGradient id="goldBorder" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#f59e0b"/>
      <stop offset="50%" stop-color="#d97706"/>
      <stop offset="100%" stop-color="#78350f"/>
    </linearGradient>

    <linearGradient id="cardGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1f253d"/>
      <stop offset="100%" stop-color="#141829"/>
    </linearGradient>

    <linearGradient id="barGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#10b981"/>
      <stop offset="100%" stop-color="#34d399"/>
    </linearGradient>
  </defs>

  <style>
    .font-title {{ font-family: 'Segoe UI', Roboto, sans-serif; font-weight: 800; fill: #ffffff; }}
    .font-sub {{ font-family: 'Segoe UI', Roboto, sans-serif; font-size: 11px; fill: #94a3b8; }}
    .font-label {{ font-family: 'Segoe UI', Roboto, sans-serif; font-size: 9.5px; fill: #94a3b8; text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px; }}
    .font-val {{ font-family: 'Segoe UI', Roboto, sans-serif; font-size: 13.5px; font-weight: bold; fill: #f8fafc; }}
    .font-sec {{ font-family: 'Segoe UI', Roboto, sans-serif; font-size: 10.5px; font-weight: bold; fill: #fbbf24; letter-spacing: 0.7px; text-transform: uppercase; }}
    .font-list {{ font-family: 'Segoe UI', Roboto, sans-serif; font-size: 11px; fill: #cbd5e1; }}
  </style>

  <!-- Outer Fantasy Frame -->
  <rect width="380" height="930" rx="16" fill="url(#bgGrad)" stroke="url(#goldBorder)" stroke-width="2"/>
  <path d="M 0 0 L 380 0 L 380 84 L 0 84 Z" fill="#13182b" opacity="0.8"/>
  <line x1="0" y1="84" x2="380" y2="84" stroke="url(#goldBorder)" stroke-width="1.5"/>

  <!-- ================= HERO BADGE (VECTOR CREST) ================= -->
  <rect x="18" y="16" width="52" height="52" rx="12" fill="{cfg['bg']}" stroke="{cfg['secondary']}" stroke-width="2"/>
  <path d="M 33 28 L 55 50" stroke="#f8fafc" stroke-width="2.5" stroke-linecap="round"/>
  <path d="M 55 28 L 33 50" stroke="#f8fafc" stroke-width="2.5" stroke-linecap="round"/>
  <path d="M 30 25 L 36 31" stroke="#f59e0b" stroke-width="2.5" stroke-linecap="round"/>
  <path d="M 58 25 L 52 31" stroke="#f59e0b" stroke-width="2.5" stroke-linecap="round"/>
  <circle cx="44" cy="39" r="4.5" fill="#f59e0b" stroke="#78350f" stroke-width="1"/>

  <text x="80" y="38" class="font-title" font-size="16">{html.escape(profile_name[:16])}</text>
  <text x="80" y="53" class="font-sub">Level {level} • <tspan fill="{cfg['secondary']}" font-weight="bold">{cfg['name']}</tspan></text>
  <text x="80" y="68" font-size="9" fill="#f59e0b" font-weight="bold" letter-spacing="1px">★ ACTIVE CHAMPION ★</text>

  <!-- ================= COMBAT & EXPEDITION ================= -->
  <text x="18" y="104" class="font-sec">⚔️ COMBAT &amp; EXPEDITION LOG</text>

  <rect x="16" y="112" width="168" height="42" rx="8" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="24" y="126" class="font-label">Total Dmg (All-Time)</text>
  <text x="24" y="144" class="font-val">⚔️ {fmt(db['all_time_damage'])}</text>

  <rect x="196" y="112" width="168" height="42" rx="8" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="204" y="126" class="font-label">Weekly Dmg (Reset Mon)</text>
  <text x="204" y="144" class="font-val">🗡️ {fmt(db['weekly_damage'])}</text>

  <rect x="16" y="160" width="168" height="42" rx="8" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="24" y="174" class="font-label">Daily Avg Dmg</text>
  <text x="24" y="192" class="font-val">📊 {fmt(avg_daily_dmg)}/day</text>

  <rect x="196" y="160" width="168" height="42" rx="8" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="204" y="174" class="font-label">Peak Weekly Record</text>
  <text x="204" y="192" class="font-val">🔥 {fmt(db['peak_weekly_damage'])}</text>

  <rect x="16" y="208" width="168" height="42" rx="8" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="24" y="222" class="font-label">Bosses Slain</text>
  <text x="24" y="240" class="font-val">🏆 {db['bosses_slain']} Bosses</text>

  <rect x="196" y="208" width="168" height="42" rx="8" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="204" y="222" class="font-label">Peak Gold Hoarded</text>
  <text x="204" y="240" class="font-val" fill="#fbbf24">💰 {fmt(db['peak_gold'])} G</text>

  <rect x="16" y="256" width="348" height="34" rx="8" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="24" y="277" class="font-sub">✨ Buffs: <tspan class="font-val">{db['buffs_cast']}</tspan> Casts  •  💧 Mana Spent: <tspan class="font-val">{fmt(db['total_mana_spent'])} MP</tspan></text>

  <line x1="16" y1="302" x2="364" y2="302" stroke="#232a42" stroke-width="1"/>

  <!-- ================= PRODUCTIVITY MATRIX ================= -->
  <text x="18" y="322" class="font-sec">📋 PRODUCTIVITY &amp; DISCIPLINE</text>

  <text x="18" y="342" class="font-sub">Dailies Today: <tspan font-weight="bold" fill="#f8fafc">{done_count}/{due_count} ({daily_pct}%)</tspan></text>
  <rect x="16" y="350" width="348" height="10" rx="5" fill="#141928"/>
  <rect x="16" y="350" width="{int(348 * (daily_pct / 100))}" height="10" rx="5" fill="url(#barGrad)"/>

  <rect x="16" y="368" width="348" height="32" rx="7" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="24" y="388" class="font-sub">Habit Mastery: <tspan class="font-val">{habit_ratio}% Positive</tspan> ({pos_clicks} 👍 / {neg_clicks} 👎)</text>

  <rect x="16" y="406" width="82" height="42" rx="7" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="22" y="420" class="font-label">Habits Today</text>
  <text x="22" y="438" class="font-val">✨ {habits_today_count}</text>

  <rect x="104" y="406" width="82" height="42" rx="7" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="110" y="420" class="font-label">Dailies Today</text>
  <text x="110" y="438" class="font-val">📋 {done_count}</text>

  <rect x="194" y="406" width="82" height="42" rx="7" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="200" y="420" class="font-label">To-Dos Today</text>
  <text x="200" y="438" class="font-val">🎯 {todos_today_count}</text>

  <rect x="282" y="406" width="82" height="42" rx="7" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="288" y="420" class="font-label">All Completed</text>
  <text x="288" y="438" class="font-val" fill="#fbbf24">⭐ {fmt(grand_total_completed)}</text>

  <rect x="16" y="454" width="168" height="42" rx="8" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="24" y="468" class="font-label">Bounty Board</text>
  <text x="24" y="486" class="font-val">🎯 {todos_active} Open / {todos_cleared_total} Done</text>

  <rect x="196" y="454" width="168" height="42" rx="8" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="204" y="468" class="font-label">Discipline Flame</text>
  <text x="204" y="486" class="font-val">🔥 {longest_streak} Days Streak</text>

  <rect x="16" y="504" width="348" height="88" rx="8" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="26" y="522" class="font-sec">🔥 TOP 3 HABITS (MOST ACTIVE)</text>
  <text x="26" y="542" class="font-list">{habit_lines[0]}</text>
  <text x="26" y="560" class="font-list">{habit_lines[1]}</text>
  <text x="26" y="578" class="font-list">{habit_lines[2]}</text>

  <rect x="16" y="600" width="348" height="88" rx="8" fill="url(#cardGrad)" stroke="#2b354f" stroke-width="1"/>
  <text x="26" y="618" class="font-sec">🏆 TOP 3 DAILIES (WEEKLY CONSISTENCY)</text>
  <text x="26" y="638" class="font-list">{daily_lines[0]}</text>
  <text x="26" y="656" class="font-list">{daily_lines[1]}</text>
  <text x="26" y="674" class="font-list">{daily_lines[2]}</text>

  <line x1="16" y1="700" x2="364" y2="700" stroke="#232a42" stroke-width="1"/>

  <!-- ================= SCROLL OF INSIGHT ================= -->
  <rect x="16" y="712" width="348" height="86" rx="8" fill="#131929" stroke="url(#goldBorder)" stroke-width="1.2"/>
  <text x="28" y="732" font-family="'Georgia', serif" font-size="10.5" font-weight="bold" fill="#facc15" letter-spacing="0.5px">📜 SCROLL OF INSIGHT</text>
  <text x="28" y="752" font-family="'Georgia', serif" font-size="11" font-style="italic" fill="#e2e8f0">
    <tspan x="28" dy="0">{html.escape(quote_lines[0]) if len(quote_lines) > 0 else ''}</tspan>
    <tspan x="28" dy="16">{html.escape(quote_lines[1]) if len(quote_lines) > 1 else ''}</tspan>
    <tspan x="28" dy="16">{html.escape(quote_lines[2]) if len(quote_lines) > 2 else ''}</tspan>
  </text>
</svg>"""

with open("profile-stats.svg", "w", encoding="utf-8") as f:
    f.write(svg_code)

# Konversi Otomatis ke PNG Resolusi Tinggi (Agar Muncul di Aplikasi Android)
try:
    import cairosvg
    cairosvg.svg2png(bytestring=svg_code.encode("utf-8"), write_to="profile-stats.png", scale=2.0)
    print("PNG generated successfully.")
except Exception as e:
    print(f"PNG conversion notice: {e}")

print("Sync completed successfully.")
