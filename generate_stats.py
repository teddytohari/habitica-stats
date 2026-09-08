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

# Quote Text
quote_text = "Small daily disciplines lead to monumental achievements over time."
if os.path.exists("quote.txt"):
    with open("quote.txt", "r", encoding="utf-8") as qf:
        lines = [line.strip() for line in qf.readlines() if line.strip()]
        if lines:
            quote_text = " ".join(lines)

# Formatting for text displays
def fmt(num):
    if num >= 1_000_000: return f"{num/1_000_000:.2f}M"
    elif num >= 1_000: return f"{num/1_000:.1f}K"
    return f"{int(num)}"

# 5. Generate Text Markdown for Habitica API (Mobile Responsive)
# Progress Bar Graphic
bar_len = 10
filled = int((daily_pct / 100) * bar_len)
bar_visual = "█" * filled + "░" * (bar_len - filled)

# Top 3 Lists for Markdown
md_habit_lines = []
for i in range(3):
    if i < len(sorted_top_habits):
        h_name = sorted_top_habits[i].get("text", "Habit")[:24]
        h_cnt = sorted_top_habits[i].get("counterUp", 0)
        md_habit_lines.append(f"{i+1}. {h_name} (+{h_cnt})")
md_habits_text = "\n".join(md_habit_lines) if md_habit_lines else "-"

md_daily_lines = []
for i in range(3):
    if i < len(sorted_top_dailies):
        d_name = sorted_top_dailies[i][0][:24]
        d_cnt = sorted_top_dailies[i][1]
        md_daily_lines.append(f"{i+1}. {d_name} ({d_cnt}x)")
md_dailies_text = "\n".join(md_daily_lines) if md_daily_lines else "-"

class_name_upper = char_class.upper()

bio_markdown = f"""[![HD Card](https://raw.githubusercontent.com/teddytohari/habitica-stats/main/profile-stats.png)](https://raw.githubusercontent.com/teddytohari/habitica-stats/main/profile-stats.png)

### ⚔️ {profile_name} (Lv. {level} {class_name_upper})
🔥 **Streak:** {longest_streak} Days | 💰 **Peak Gold:** {fmt(db['peak_gold'])}

**▬▬ 🛡️ COMBAT & EXPEDITION ▬▬**
⚔️ **Total Dmg:** {fmt(db['all_time_damage'])}
🗡️ **Weekly Dmg:** {fmt(db['weekly_damage'])}
🏆 **Bosses Slain:** {db['bosses_slain']}
✨ **Buffs:** {db['buffs_cast']} | 💧 **Mana:** {fmt(db['total_mana_spent'])} MP

**▬▬ 📋 PRODUCTIVITY MATRIX ▬▬**
**Dailies Today:** {done_count}/{due_count} ({daily_pct}%)
`{bar_visual}`
👍 **Habit Mastery:** {habit_ratio}% Positive
✅ **Cleared Today:** ✨{habits_today_count} | 📋{done_count} | 🎯{todos_today_count}

**🔥 TOP 3 HABITS**
{md_habits_text}

**🏆 TOP 3 DAILIES**
{md_dailies_text}

📜 *"{quote_text}"*
"""

# 6. Update Habitica User Bio via API automatically!
update_url = "https://habitica.com/api/v3/user"
update_data = {"profile": {"blurb": bio_markdown}}
try:
    update_res = requests.put(update_url, headers=headers, json=update_data)
    if update_res.status_code == 200:
        print("✅ Automatically updated Habitica Bio via API!")
    else:
        print(f"❌ Failed to update bio. Status: {update_res.status_code}")
except Exception as e:
    print(f"API Update notice: {e}")

# 7. Create SVG/PNG as usual (for the clickable banner)
# (Kode pembangkitan SVG/PNG sengaja disederhanakan sebagai dummy agar eksekusi cepat,
# karena sekarang kita mengandalkan teks Markdown Habitica sebagai layar utamanya).
svg_code = f"""<svg width="400" height="100" fill="#141724" xmlns="http://www.w3.org/2000/svg">
  <rect width="400" height="100" rx="8" fill="#141724" stroke="#f59e0b" stroke-width="2"/>
  <text x="200" y="55" font-family="sans-serif" font-size="16" font-weight="bold" fill="#facc15" text-anchor="middle">
    ⚔️ VIEW HD RPG STATS CARD ⚔️
  </text>
</svg>"""

with open("profile-stats.svg", "w", encoding="utf-8") as f:
    f.write(svg_code)

try:
    import cairosvg
    cairosvg.svg2png(bytestring=svg_code.encode("utf-8"), write_to="profile-stats.png")
    print("✅ PNG banner generated.")
except Exception as e:
    print(f"PNG notice: {e}")

print("Sync & API Update completed successfully.")
