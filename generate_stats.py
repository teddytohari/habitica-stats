import os
import json
import html
import textwrap
import base64
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
    d_text = d.get("text", "Daily Task")[:28]
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

# Streaks & Damage Averages
longest_streak = max([t.get("streak", 0) for t in dailies], default=0)
days_elapsed = max(1, (now_wib.weekday() if now_wib.hour >= 6 else (now_wib.weekday() - 1) % 7) + 1)
avg_daily_dmg = db["weekly_damage"] / days_elapsed

with open(DB_FILE, "w", encoding="utf-8") as f:
    json.dump(db, f, indent=2)

# Quote Text Wrapping
quote_text = "Small daily disciplines lead to monumental achievements over time."
if os.path.exists("quote.txt"):
    with open("quote.txt", "r", encoding="utf-8") as qf:
        lines = [line.strip() for line in qf.readlines() if line.strip()]
        if lines:
            quote_text = " ".join(lines)

quote_lines = textwrap.wrap(quote_text, width=48)[:3]

# Class Palettes & Theming
CLASS_CONFIG = {
    "warrior": {"primary": "#e11d48", "secondary": "#fb7185", "bg": "#3a0914", "name": "WARRIOR"},
    "mage": {"primary": "#3b82f6", "secondary": "#60a5fa", "bg": "#0f172a", "name": "ARCHMAGE"},
    "rogue": {"primary": "#d97706", "secondary": "#fbbf24", "bg": "#321706", "name": "SHADOW ROGUE"},
    "healer": {"primary": "#059669", "secondary": "#34d399", "bg": "#062b20", "name": "HIGH HEALER"}
}
cfg = CLASS_CONFIG.get(char_class, CLASS_CONFIG["warrior"])

# 5. Fetch Habitica Avatar & Background Image
avatar_b64 = None
try:
    av_url = f"https://habitica.com/export/avatar-{USER_ID}.png"
    av_res = requests.get(av_url, headers=headers, timeout=6)
    if av_res.status_code == 200 and len(av_res.content) > 300:
        avatar_b64 = base64.b64encode(av_res.content).decode("utf-8")
except Exception as e:
    print(f"Avatar notice: {e}")

header_bg_b64 = None
try:
    bg_key = user_res.get("preferences", {}).get("background", "violet")
    bg_url = f"https://habitica-assets.s3.amazonaws.com/mobileApp/images/background_{bg_key}.png"
    bg_res = requests.get(bg_url, timeout=5)
    if bg_res.status_code == 200 and len(bg_res.content) > 300:
        header_bg_b64 = base64.b64encode(bg_res.content).decode("utf-8")
except Exception as e:
    print(f"Background notice: {e}")

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
        h_name = (h_name[:28] + "..") if len(h_name) > 30 else h_name
        h_cnt = sorted_top_habits[i].get("counterUp", 0)
        habit_lines.append(f"{i+1}. {html.escape(h_name)} (+{h_cnt})")
    else:
        habit_lines.append(f"{i+1}. -")

daily_lines = []
for i in range(3):
    if i < len(sorted_top_dailies):
        d_name = sorted_top_dailies[i][0]
        d_name = (d_name[:28] + "..") if len(d_name) > 30 else d_name
        d_cnt = sorted_top_dailies[i][1]
        daily_lines.append(f"{i+1}. {html.escape(d_name)} ({d_cnt}x)")
    else:
        daily_lines.append(f"{i+1}. -")

# 6. Render SVG (Canvas width 460 for edge-to-edge mobile display)
avatar_element = f'<image href="data:image/png;base64,{avatar_b64}" x="20" y="16" width="66" height="66" preserveAspectRatio="xMidYMid meet"/>' if avatar_b64 else f'''
  <rect x="22" y="18" width="62" height="62" rx="12" fill="{cfg['bg']}" stroke="{cfg['secondary']}" stroke-width="2"/>
  <path d="M 38 34 L 68 64" stroke="#f8fafc" stroke-width="2.8" stroke-linecap="round"/>
  <path d="M 68 34 L 38 64" stroke="#f8fafc" stroke-width="2.8" stroke-linecap="round"/>
  <circle cx="53" cy="49" r="6" fill="#f59e0b" stroke="#78350f" stroke-width="1.2"/>
'''

header_bg_element = f'<image href="data:image/png;base64,{header_bg_b64}" x="2" y="2" width="456" height="108" preserveAspectRatio="xMidYMid slice" opacity="0.35" rx="14"/>' if header_bg_b64 else ''

svg_code = f"""<svg width="460" height="910" viewBox="0 0 460 910" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <!-- Background Canvas Gradient -->
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#141724"/>
      <stop offset="50%" stop-color="#0c0e17"/>
      <stop offset="100%" stop-color="#07080f"/>
    </linearGradient>

    <!-- Gold Border Frame -->
    <linearGradient id="goldBorder" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#f59e0b"/>
      <stop offset="50%" stop-color="#d97706"/>
      <stop offset="100%" stop-color="#78350f"/>
    </linearGradient>

    <!-- Thematic Section Gradients (Dark Jewel Tones) -->
    <linearGradient id="combatGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#24121b"/>
      <stop offset="100%" stop-color="#180c13"/>
    </linearGradient>

    <linearGradient id="prodGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#12182b"/>
      <stop offset="100%" stop-color="#0b101e"/>
    </linearGradient>

    <linearGradient id="habitGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#211710"/>
      <stop offset="100%" stop-color="#140d07"/>
    </linearGradient>

    <linearGradient id="dailyGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0f2119"/>
      <stop offset="100%" stop-color="#07140e"/>
    </linearGradient>

    <linearGradient id="insightGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1a1226"/>
      <stop offset="100%" stop-color="#0e0a16"/>
    </linearGradient>

    <linearGradient id="barGrad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#10b981"/>
      <stop offset="100%" stop-color="#34d399"/>
    </linearGradient>
  </defs>

  <style>
    .font-title {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-weight: 800; fill: #ffffff; }}
    .font-sub {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 11.5px; fill: #94a3b8; }}
    .font-label {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 9.5px; fill: #94a3b8; text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px; }}
    .font-val {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; font-weight: bold; fill: #f8fafc; }}
    .font-sec-combat {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 11px; font-weight: bold; fill: #fb7185; letter-spacing: 0.7px; text-transform: uppercase; }}
    .font-sec-prod {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 11px; font-weight: bold; fill: #60a5fa; letter-spacing: 0.7px; text-transform: uppercase; }}
    .font-list {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 11.5px; fill: #cbd5e1; }}
  </style>

  <!-- Outer Fantasy Canvas Frame -->
  <rect width="460" height="910" rx="18" fill="url(#bgGrad)" stroke="url(#goldBorder)" stroke-width="2"/>

  <!-- ================= HEADER (AVATAR & BACKGROUND) ================= -->
  {header_bg_element}
  <rect x="0" y="0" width="460" height="110" rx="16" fill="#0b0e18" opacity="0.6"/>
  <line x1="0" y1="110" x2="460" y2="110" stroke="url(#goldBorder)" stroke-width="1.5"/>

  <!-- Avatar Badge Display -->
  {avatar_element}

  <!-- Hero Titles -->
  <text x="98" y="44" class="font-title" font-size="18">{html.escape(profile_name[:18])}</text>
  <text x="98" y="64" class="font-sub">Level {level} • <tspan fill="{cfg['secondary']}" font-weight="bold">{cfg['name']}</tspan></text>
  <text x="98" y="82" font-size="9.5" fill="#f59e0b" font-weight="bold" letter-spacing="1px">★ ACTIVE CHAMPION OF HABITICA ★</text>

  <!-- ================= COMBAT & EXPEDITION ================= -->
  <text x="18" y="132" class="font-sec-combat">⚔️ COMBAT &amp; EXPEDITION LOG</text>

  <!-- Row 1 -->
  <rect x="16" y="142" width="208" height="46" rx="8" fill="url(#combatGrad)" stroke="#4c1d2c" stroke-width="1"/>
  <text x="26" y="158" class="font-label">Total Dmg (All-Time)</text>
  <text x="26" y="177" class="font-val">⚔️ {fmt(db['all_time_damage'])}</text>

  <rect x="236" y="142" width="208" height="46" rx="8" fill="url(#combatGrad)" stroke="#4c1d2c" stroke-width="1"/>
  <text x="246" y="158" class="font-label">Weekly Dmg (Reset Mon)</text>
  <text x="246" y="177" class="font-val">🗡️ {fmt(db['weekly_damage'])}</text>

  <!-- Row 2 -->
  <rect x="16" y="196" width="208" height="46" rx="8" fill="url(#combatGrad)" stroke="#4c1d2c" stroke-width="1"/>
  <text x="26" y="212" class="font-label">Daily Avg Dmg</text>
  <text x="26" y="231" class="font-val">📊 {fmt(avg_daily_dmg)}/day</text>

  <rect x="236" y="196" width="208" height="46" rx="8" fill="url(#combatGrad)" stroke="#4c1d2c" stroke-width="1"/>
  <text x="246" y="212" class="font-label">Peak Weekly Record</text>
  <text x="246" y="231" class="font-val">🔥 {fmt(db['peak_weekly_damage'])}</text>

  <!-- Row 3 -->
  <rect x="16" y="250" width="208" height="46" rx="8" fill="url(#combatGrad)" stroke="#4c1d2c" stroke-width="1"/>
  <text x="26" y="266" class="font-label">Bosses Slain</text>
  <text x="26" y="285" class="font-val">🏆 {db['bosses_slain']} Bosses</text>

  <rect x="236" y="250" width="208" height="46" rx="8" fill="url(#combatGrad)" stroke="#4c1d2c" stroke-width="1"/>
  <text x="246" y="266" class="font-label">Peak Gold Hoarded</text>
  <text x="246" y="285" class="font-val" fill="#fbbf24">💰 {fmt(db['peak_gold'])} G</text>

  <!-- Consolidated Buff & Mana Box -->
  <rect x="16" y="304" width="428" height="36" rx="8" fill="url(#combatGrad)" stroke="#4c1d2c" stroke-width="1"/>
  <text x="26" y="327" class="font-sub">✨ Buffs: <tspan class="font-val">{db['buffs_cast']}</tspan> Casts  •  💧 Mana Spent: <tspan class="font-val">{fmt(db['total_mana_spent'])} MP</tspan></text>

  <line x1="16" y1="352" x2="444" y2="352" stroke="#252b40" stroke-width="1"/>

  <!-- ================= PRODUCTIVITY MATRIX ================= -->
  <text x="18" y="374" class="font-sec-prod">📋 PRODUCTIVITY &amp; DISCIPLINE MATRIX</text>

  <!-- Dailies Progress -->
  <text x="18" y="394" class="font-sub">Dailies Today: <tspan font-weight="bold" fill="#f8fafc">{done_count}/{due_count} ({daily_pct}%)</tspan></text>
  <rect x="16" y="402" width="428" height="11" rx="5.5" fill="#151b2e"/>
  <rect x="16" y="402" width="{int(428 * (daily_pct / 100))}" height="11" rx="5.5" fill="url(#barGrad)"/>

  <!-- Repositioned Habit Mastery -->
  <rect x="16" y="421" width="428" height="34" rx="7" fill="url(#prodGrad)" stroke="#1e293b" stroke-width="1"/>
  <text x="26" y="442" class="font-sub">Habit Mastery: <tspan class="font-val">{habit_ratio}% Positive</tspan> ({pos_clicks} 👍 / {neg_clicks} 👎)</text>

  <!-- Distinct Color Grid 4 Activity Today -->
  <!-- 1. Habits Today (Amber) -->
  <rect x="16" y="463" width="101" height="46" rx="7" fill="#1f1610" stroke="#b45309" stroke-width="1"/>
  <text x="22" y="479" class="font-label">Habits Today</text>
  <text x="22" y="499" class="font-val">✨ {habits_today_count}</text>

  <!-- 2. Dailies Today (Emerald) -->
  <rect x="125" y="463" width="101" height="46" rx="7" fill="#0d1f18" stroke="#059669" stroke-width="1"/>
  <text x="131" y="479" class="font-label">Dailies Today</text>
  <text x="131" y="499" class="font-val">📋 {done_count}</text>

  <!-- 3. To-Dos Today (Cobalt) -->
  <rect x="234" y="463" width="101" height="46" rx="7" fill="#0f1f33" stroke="#0284c7" stroke-width="1"/>
  <text x="240" y="479" class="font-label">To-Dos Today</text>
  <text x="240" y="499" class="font-val">🎯 {todos_today_count}</text>

  <!-- 4. Grand Total (Gold) -->
  <rect x="343" y="463" width="101" height="46" rx="7" fill="#241b0b" stroke="#ca8a04" stroke-width="1"/>
  <text x="349" y="479" class="font-label">All Completed</text>
  <text x="349" y="499" class="font-val" fill="#fbbf24">⭐ {fmt(grand_total_completed)}</text>

  <!-- Bounty Board & Streak -->
  <rect x="16" y="517" width="208" height="46" rx="8" fill="url(#prodGrad)" stroke="#1e293b" stroke-width="1"/>
  <text x="26" y="533" class="font-label">Bounty Board</text>
  <text x="26" y="552" class="font-val">🎯 {todos_active} Open / {todos_cleared_total} Cleared</text>

  <rect x="236" y="517" width="208" height="46" rx="8" fill="url(#prodGrad)" stroke="#1e293b" stroke-width="1"/>
  <text x="246" y="533" class="font-label">Discipline Flame</text>
  <text x="246" y="552" class="font-val">🔥 {longest_streak} Days Streak</text>

  <!-- Box 1: Dedicated Top 3 Habits (Smoky Bronze) -->
  <rect x="16" y="571" width="428" height="92" rx="8" fill="url(#habitGrad)" stroke="#78350f" stroke-width="1.2"/>
  <text x="28" y="591" font-family="-apple-system, sans-serif" font-size="11px" font-weight="bold" fill="#f59e0b" letter-spacing="0.6px">🔥 TOP 3 HABITS (MOST ACTIVE)</text>
  <text x="28" y="612" class="font-list">{habit_lines[0]}</text>
  <text x="28" y="630" class="font-list">{habit_lines[1]}</text>
  <text x="28" y="648" class="font-list">{habit_lines[2]}</text>

  <!-- Box 2: Dedicated Top 3 Dailies (Deep Forest) -->
  <rect x="16" y="671" width="428" height="92" rx="8" fill="url(#dailyGrad)" stroke="#064e3b" stroke-width="1.2"/>
  <text x="28" y="691" font-family="-apple-system, sans-serif" font-size="11px" font-weight="bold" fill="#10b981" letter-spacing="0.6px">🏆 TOP 3 DAILIES (WEEKLY CONSISTENCY)</text>
  <text x="28" y="712" class="font-list">{daily_lines[0]}</text>
  <text x="28" y="730" class="font-list">{daily_lines[1]}</text>
  <text x="28" y="748" class="font-list">{daily_lines[2]}</text>

  <line x1="16" y1="775" x2="444" y2="775" stroke="#252b40" stroke-width="1"/>

  <!-- ================= SCROLL OF INSIGHT (Dark Amethyst) ================= -->
  <rect x="16" y="787" width="428" height="96" rx="9" fill="url(#insightGrad)" stroke="#6d28d9" stroke-width="1.2"/>
  <text x="28" y="810" font-family="'Georgia', serif" font-size="11" font-weight="bold" fill="#facc15" letter-spacing="0.5px">📜 SCROLL OF INSIGHT</text>
  <text x="28" y="832" font-family="'Georgia', serif" font-size="12" font-style="italic" fill="#e2e8f0">
    <tspan x="28" dy="0">{html.escape(quote_lines[0]) if len(quote_lines) > 0 else ''}</tspan>
    <tspan x="28" dy="18">{html.escape(quote_lines[1]) if len(quote_lines) > 1 else ''}</tspan>
    <tspan x="28" dy="18">{html.escape(quote_lines[2]) if len(quote_lines) > 2 else ''}</tspan>
  </text>
</svg>"""

with open("profile-stats.svg", "w", encoding="utf-8") as f:
    f.write(svg_code)

# Konversi PNG beresolusi tajam (~1.200px lebar) agar mengisi penuh layar HP
try:
    import cairosvg
    cairosvg.svg2png(bytestring=svg_code.encode("utf-8"), write_to="profile-stats.png", scale=2.6)
    print("PNG generated successfully with high-DPI scaling.")
except Exception as e:
    print(f"PNG conversion notice: {e}")

print("Sync completed successfully.")
