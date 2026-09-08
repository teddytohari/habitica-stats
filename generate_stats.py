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

# 3. Weekly Reset Cycle
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

if not isinstance(tasks_res, list): tasks_res = []
if not isinstance(completed_todos_res, list): completed_todos_res = []

profile_name = user_res.get("profile", {}).get("name", "Adventurer")
char_class = user_res.get("stats", {}).get("class", "warrior").lower()
level = user_res.get("stats", {}).get("lvl", 1)
current_gold = user_res.get("stats", {}).get("gp", 0.0)
current_mp = user_res.get("stats", {}).get("mp", 0.0)

if char_class not in db["classes_used"]: db["classes_used"].append(char_class)
if current_gold > db["peak_gold"]: db["peak_gold"] = current_gold

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
    d_text = d.get("text", "Daily Task")[:28]
    db["weekly_top_dailies"][d_text] = db["weekly_top_dailies"].get(d_text, 0) + 1

sorted_top_dailies = sorted(db["weekly_top_dailies"].items(), key=lambda x: x[1], reverse=True)[:3]

habits = [t for t in tasks_res if t.get("type") == "habit"]
pos_clicks = sum(t.get("counterUp", 0) for t in habits)
neg_clicks = sum(t.get("counterDown", 0) for t in habits)
total_clicks = pos_clicks + neg_clicks
habit_ratio = int((pos_clicks / total_clicks * 100)) if total_clicks > 0 else 100

sorted_top_habits = sorted(habits, key=lambda h: h.get("counterUp", 0), reverse=True)[:3]

if db.get("last_daily_date") != today_str:
    db["last_daily_date"] = today_str
    db["daily_habit_baseline"] = pos_clicks

habits_today_count = max(0, pos_clicks - db.get("daily_habit_baseline", pos_clicks))
todos_today_count = sum(1 for td in completed_todos_res if td.get("dateCompleted") and datetime.fromisoformat(td["dateCompleted"].replace("Z", "+00:00")).astimezone(WIB).strftime("%Y-%m-%d") == today_str)
todos_active = len([t for t in tasks_res if t.get("type") == "todo"])
todos_cleared_total = len(completed_todos_res)
grand_total_completed = pos_clicks + todos_cleared_total + done_count

longest_streak = max([t.get("streak", 0) for t in dailies], default=0)
days_elapsed = max(1, (now_wib.weekday() if now_wib.hour >= 6 else (now_wib.weekday() - 1) % 7) + 1)
avg_daily_dmg = db["weekly_damage"] / days_elapsed

with open(DB_FILE, "w", encoding="utf-8") as f:
    json.dump(db, f, indent=2)

quote_text = "Small daily disciplines lead to monumental achievements over time."
if os.path.exists("quote.txt"):
    with open("quote.txt", "r", encoding="utf-8") as qf:
        lines = [line.strip() for line in qf.readlines() if line.strip()]
        if lines: quote_text = " ".join(lines)

def fmt(num):
    if num >= 1_000_000: return f"{num/1_000_000:.2f}M"
    elif num >= 1_000: return f"{num/1_000:.1f}K"
    return f"{int(num)}"

# 5. GENERATE TEXT MARKDOWN UNTUK AUTO-UPDATE BIO
bar_len = 10
filled = int((daily_pct / 100) * bar_len)
bar_visual = "█" * filled + "░" * (bar_len - filled)

md_habit_lines = "\n".join([f"{i+1}. {h.get('text')[:24]} (+{h.get('counterUp', 0)})" for i, h in enumerate(sorted_top_habits)]) if sorted_top_habits else "-"
md_daily_lines = "\n".join([f"{i+1}. {d[0][:24]} ({d[1]}x)" for i, d in enumerate(sorted_top_dailies)]) if sorted_top_dailies else "-"

bio_markdown = f"""[![HD Card](https://raw.githubusercontent.com/teddytohari/habitica-stats/main/profile-stats.png)](https://raw.githubusercontent.com/teddytohari/habitica-stats/main/profile-stats.png)

### ⚔️ {profile_name} (Lv. {level} {char_class.upper()})
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
{md_habit_lines}

**🏆 TOP 3 DAILIES**
{md_daily_lines}

📜 *"{quote_text}"*
"""

# PUSH KE HABITICA API (Menggunakan dot-notation agar tidak ditolak)
try:
    update_res = requests.put("https://habitica.com/api/v3/user", headers=headers, json={"profile.blurb": bio_markdown})
    print(f"Bio Auto-Update Status: {update_res.status_code}")
except Exception as e:
    print(f"API Update notice: {e}")

# 6. GENERATE HD SVG & PNG GAMBAR BESARNYA (Untuk banner yang bisa di-klik)
CLASS_CONFIG = {
    "warrior": {"secondary": "#fb7185", "bg": "#3a0914", "name": "WARRIOR"},
    "mage": {"secondary": "#60a5fa", "bg": "#0f172a", "name": "ARCHMAGE"},
    "rogue": {"secondary": "#fbbf24", "bg": "#321706", "name": "SHADOW ROGUE"},
    "healer": {"secondary": "#34d399", "bg": "#062b20", "name": "HIGH HEALER"}
}
cfg = CLASS_CONFIG.get(char_class, CLASS_CONFIG["warrior"])

avatar_b64 = header_bg_b64 = None
try:
    av_res = requests.get(f"https://habitica.com/export/avatar-{USER_ID}.png", headers=headers, timeout=5)
    if av_res.status_code == 200: avatar_b64 = base64.b64encode(av_res.content).decode("utf-8")
except: pass

try:
    bg_key = user_res.get("preferences", {}).get("background", "violet")
    bg_res = requests.get(f"https://habitica-assets.s3.amazonaws.com/mobileApp/images/background_{bg_key}.png", timeout=5)
    if bg_res.status_code == 200: header_bg_b64 = base64.b64encode(bg_res.content).decode("utf-8")
except: pass

habit_lines = [f"{i+1}. {html.escape(h.get('text', '')[:28])} (+{h.get('counterUp', 0)})" for i, h in enumerate(sorted_top_habits)]
habit_lines += [f"{i+1}. -" for i in range(len(habit_lines), 3)]
daily_lines = [f"{i+1}. {html.escape(d[0][:28])} ({d[1]}x)" for i, d in enumerate(sorted_top_dailies)]
daily_lines += [f"{i+1}. -" for i in range(len(daily_lines), 3)]
quote_lines = textwrap.wrap(quote_text, width=48)[:3]

avatar_element = f'<image xlink:href="data:image/png;base64,{avatar_b64}" x="18" y="14" width="70" height="70" preserveAspectRatio="xMidYMid meet"/>' if avatar_b64 else f'''<rect x="22" y="18" width="62" height="62" rx="12" fill="{cfg['bg']}" stroke="{cfg['secondary']}" stroke-width="2"/><path d="M 38 34 L 68 64" stroke="#f8fafc" stroke-width="2.8" stroke-linecap="round"/><path d="M 68 34 L 38 64" stroke="#f8fafc" stroke-width="2.8" stroke-linecap="round"/>'''
header_bg_element = f'<image xlink:href="data:image/png;base64,{header_bg_b64}" x="0" y="0" width="460" height="110" preserveAspectRatio="xMidYMid slice" opacity="0.35"/>' if header_bg_b64 else ''

svg_code = f"""<svg width="920" height="1820" viewBox="0 0 460 910" fill="none" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
  <defs>
    <clipPath id="roundCorners"><rect width="460" height="910" rx="18"/></clipPath>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#141724"/><stop offset="100%" stop-color="#07080f"/></linearGradient>
    <linearGradient id="goldBorder" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#f59e0b"/><stop offset="50%" stop-color="#d97706"/><stop offset="100%" stop-color="#78350f"/></linearGradient>
    <linearGradient id="combatGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#24121b"/><stop offset="100%" stop-color="#180c13"/></linearGradient>
    <linearGradient id="prodGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#12182b"/><stop offset="100%" stop-color="#0b101e"/></linearGradient>
    <linearGradient id="habitGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#211710"/><stop offset="100%" stop-color="#140d07"/></linearGradient>
    <linearGradient id="dailyGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#0f2119"/><stop offset="100%" stop-color="#07140e"/></linearGradient>
    <linearGradient id="insightGrad" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#1a1226"/><stop offset="100%" stop-color="#0e0a16"/></linearGradient>
    <linearGradient id="barGrad" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#10b981"/><stop offset="100%" stop-color="#34d399"/></linearGradient>
  </defs>

  <g clip-path="url(#roundCorners)">
    <rect width="460" height="910" fill="url(#bgGrad)" />
    {header_bg_element}
    <rect x="0" y="0" width="460" height="110" fill="#0b0e18" opacity="0.6"/>
    <line x1="0" y1="110" x2="460" y2="110" stroke="url(#goldBorder)" stroke-width="1.5"/>
    {avatar_element}

    <text x="98" y="44" font-family="sans-serif" font-weight="800" fill="#fff" font-size="18">{html.escape(profile_name[:18])}</text>
    <text x="98" y="64" font-family="sans-serif" font-size="11.5" fill="#94a3b8">Level {level} • <tspan fill="{cfg['secondary']}" font-weight="bold">{cfg['name']}</tspan></text>
    
    <!-- COMBAT SECTION -->
    <rect x="16" y="142" width="208" height="46" rx="8" fill="url(#combatGrad)" stroke="#4c1d2c"/><text x="26" y="158" font-family="sans-serif" font-size="9.5" fill="#94a3b8">TOTAL DMG (ALL-TIME)</text><text x="26" y="177" font-family="sans-serif" font-size="14" font-weight="bold" fill="#fff">⚔️ {fmt(db['all_time_damage'])}</text>
    <rect x="236" y="142" width="208" height="46" rx="8" fill="url(#combatGrad)" stroke="#4c1d2c"/><text x="246" y="158" font-family="sans-serif" font-size="9.5" fill="#94a3b8">WEEKLY DMG (RESET MON)</text><text x="246" y="177" font-family="sans-serif" font-size="14" font-weight="bold" fill="#fff">🗡️ {fmt(db['weekly_damage'])}</text>
    
    <rect x="16" y="196" width="208" height="46" rx="8" fill="url(#combatGrad)" stroke="#4c1d2c"/><text x="26" y="212" font-family="sans-serif" font-size="9.5" fill="#94a3b8">DAILY AVG DMG</text><text x="26" y="231" font-family="sans-serif" font-size="14" font-weight="bold" fill="#fff">📊 {fmt(avg_daily_dmg)}/day</text>
    <rect x="236" y="196" width="208" height="46" rx="8" fill="url(#combatGrad)" stroke="#4c1d2c"/><text x="246" y="212" font-family="sans-serif" font-size="9.5" fill="#94a3b8">PEAK WEEKLY RECORD</text><text x="246" y="231" font-family="sans-serif" font-size="14" font-weight="bold" fill="#fff">🔥 {fmt(db['peak_weekly_damage'])}</text>

    <rect x="16" y="250" width="208" height="46" rx="8" fill="url(#combatGrad)" stroke="#4c1d2c"/><text x="26" y="266" font-family="sans-serif" font-size="9.5" fill="#94a3b8">BOSSES SLAIN</text><text x="26" y="285" font-family="sans-serif" font-size="14" font-weight="bold" fill="#fff">🏆 {db['bosses_slain']} Bosses</text>
    <rect x="236" y="250" width="208" height="46" rx="8" fill="url(#combatGrad)" stroke="#4c1d2c"/><text x="246" y="266" font-family="sans-serif" font-size="9.5" fill="#94a3b8">PEAK GOLD HOARDED</text><text x="246" y="285" font-family="sans-serif" font-size="14" font-weight="bold" fill="#fbbf24">💰 {fmt(db['peak_gold'])} G</text>
    
    <rect x="16" y="304" width="428" height="36" rx="8" fill="url(#combatGrad)" stroke="#4c1d2c"/><text x="26" y="327" font-family="sans-serif" font-size="11.5" fill="#94a3b8">✨ Buffs: <tspan fill="#fff" font-weight="bold">{db['buffs_cast']}</tspan> Casts  •  💧 Mana Spent: <tspan fill="#fff" font-weight="bold">{fmt(db['total_mana_spent'])} MP</tspan></text>

    <!-- PRODUCTIVITY SECTION -->
    <rect x="16" y="402" width="428" height="11" rx="5.5" fill="#151b2e"/><rect x="16" y="402" width="{int(428 * (daily_pct / 100))}" height="11" rx="5.5" fill="url(#barGrad)"/>
    <rect x="16" y="421" width="428" height="34" rx="7" fill="url(#prodGrad)" stroke="#1e293b"/><text x="26" y="442" font-family="sans-serif" font-size="11.5" fill="#94a3b8">Habit Mastery: <tspan fill="#fff" font-weight="bold">{habit_ratio}% Positive</tspan> ({pos_clicks} 👍 / {neg_clicks} 👎)</text>
    
    <rect x="16" y="463" width="101" height="46" rx="7" fill="#1f1610" stroke="#b45309"/><text x="22" y="479" font-family="sans-serif" font-size="9.5" fill="#94a3b8">HABITS TODAY</text><text x="22" y="499" font-family="sans-serif" font-size="14" font-weight="bold" fill="#fff">✨ {habits_today_count}</text>
    <rect x="125" y="463" width="101" height="46" rx="7" fill="#0d1f18" stroke="#059669"/><text x="131" y="479" font-family="sans-serif" font-size="9.5" fill="#94a3b8">DAILIES TODAY</text><text x="131" y="499" font-family="sans-serif" font-size="14" font-weight="bold" fill="#fff">📋 {done_count}</text>
    <rect x="234" y="463" width="101" height="46" rx="7" fill="#0f1f33" stroke="#0284c7"/><text x="240" y="479" font-family="sans-serif" font-size="9.5" fill="#94a3b8">TO-DOS TODAY</text><text x="240" y="499" font-family="sans-serif" font-size="14" font-weight="bold" fill="#fff">🎯 {todos_today_count}</text>
    <rect x="343" y="463" width="101" height="46" rx="7" fill="#241b0b" stroke="#ca8a04"/><text x="349" y="479" font-family="sans-serif" font-size="9.5" fill="#94a3b8">ALL COMPLETED</text><text x="349" y="499" font-family="sans-serif" font-size="14" font-weight="bold" fill="#fbbf24">⭐ {fmt(grand_total_completed)}</text>

    <!-- LISTS -->
    <rect x="16" y="571" width="428" height="92" rx="8" fill="url(#habitGrad)" stroke="#78350f"/><text x="28" y="591" font-family="sans-serif" font-size="11" font-weight="bold" fill="#f59e0b">🔥 TOP 3 HABITS</text><text x="28" y="612" font-family="sans-serif" font-size="11.5" fill="#cbd5e1">{habit_lines[0]}</text><text x="28" y="630" font-family="sans-serif" font-size="11.5" fill="#cbd5e1">{habit_lines[1]}</text><text x="28" y="648" font-family="sans-serif" font-size="11.5" fill="#cbd5e1">{habit_lines[2]}</text>
    <rect x="16" y="671" width="428" height="92" rx="8" fill="url(#dailyGrad)" stroke="#064e3b"/><text x="28" y="691" font-family="sans-serif" font-size="11" font-weight="bold" fill="#10b981">🏆 TOP 3 DAILIES</text><text x="28" y="712" font-family="sans-serif" font-size="11.5" fill="#cbd5e1">{daily_lines[0]}</text><text x="28" y="730" font-family="sans-serif" font-size="11.5" fill="#cbd5e1">{daily_lines[1]}</text><text x="28" y="748" font-family="sans-serif" font-size="11.5" fill="#cbd5e1">{daily_lines[2]}</text>
  </g>
  <rect width="460" height="910" rx="18" fill="none" stroke="url(#goldBorder)" stroke-width="3.5"/>
</svg>"""

with open("profile-stats.svg", "w", encoding="utf-8") as f:
    f.write(svg_code)

try:
    import cairosvg
    cairosvg.svg2png(bytestring=svg_code.encode("utf-8"), write_to="profile-stats.png")
except Exception as e:
    print(f"PNG Error: {e}")
