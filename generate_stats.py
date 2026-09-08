import os, json, html, base64, requests
from datetime import datetime, timezone, timedelta

# 1. Setup & Credentials
USER_ID = os.environ.get("HABITICA_USER_ID")
API_TOKEN = os.environ.get("HABITICA_API_TOKEN")
WIB = timezone(timedelta(hours=7))
headers = {"x-api-user": USER_ID, "x-api-key": API_TOKEN, "x-client": f"{USER_ID}-RPGStatsCard"}

# 2. Database Init
DB_FILE = "database.json"
db = {"current_cycle_id": "", "peak_gold": 0.0, "total_mana_spent": 0.0, "last_mana": None, "buffs_cast": 0, "bosses_slain": 0, "all_time_damage": 0.0, "weekly_damage": 0.0, "peak_weekly_damage": 0.0, "last_damage_up": 0.0, "weekly_top_dailies": {}, "last_daily_date": "", "daily_habit_baseline": 0, "total_dailies_cleared": 0}
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r", encoding="utf-8") as f: db.update(json.load(f))

now = datetime.now(WIB)
cycle = f"{(now - timedelta(hours=6)).year}-W{(now - timedelta(hours=6)).isocalendar()[1]}"
if db["current_cycle_id"] != cycle:
    db["peak_weekly_damage"] = max(db["peak_weekly_damage"], db["weekly_damage"])
    db["weekly_damage"] = 0.0; db["weekly_top_dailies"] = {}; db["current_cycle_id"] = cycle

# 3. Fetch API Data
u_res = requests.get("https://habitica.com/api/v3/user", headers=headers).json().get("data", {})
t_res = requests.get("https://habitica.com/api/v3/tasks/user", headers=headers).json().get("data", [])
c_res = requests.get("https://habitica.com/api/v3/tasks/user?type=completedTodos", headers=headers).json().get("data", [])

p_name = html.escape(u_res.get("profile", {}).get("name", "Hero")[:18])
c_class = u_res.get("stats", {}).get("class", "warrior").lower()
lvl = u_res.get("stats", {}).get("lvl", 1)
gold = u_res.get("stats", {}).get("gp", 0.0)
mp = u_res.get("stats", {}).get("mp", 0.0)

db["peak_gold"] = max(db["peak_gold"], gold)
if db["last_mana"] is not None and mp < db["last_mana"]:
    diff = db["last_mana"] - mp
    db["total_mana_spent"] += diff
    if diff >= 15: db["buffs_cast"] += int(diff // 25) + 1
db["last_mana"] = mp

dmg_up = u_res.get("party", {}).get("quest", {}).get("progress", {}).get("up", 0.0)
if dmg_up > db["last_damage_up"]:
    db["weekly_damage"] += (dmg_up - db["last_damage_up"])
    db["all_time_damage"] += (dmg_up - db["last_damage_up"])
db["last_damage_up"] = dmg_up

dailies = [t for t in t_res if t.get("type") == "daily"]
due = [t for t in dailies if t.get("isDue", False)]
done = [t for t in due if t.get("completed", False)]
pct = int((len(done) / len(due) * 100)) if due else 100

for d in done:
    n = html.escape(d.get("text", "")[:28])
    db["weekly_top_dailies"][n] = db["weekly_top_dailies"].get(n, 0) + 1
top_d = sorted(db["weekly_top_dailies"].items(), key=lambda x: x[1], reverse=True)[:3]

habits = [t for t in t_res if t.get("type") == "habit"]
up = sum(t.get("counterUp", 0) for t in habits)
dn = sum(t.get("counterDown", 0) for t in habits)
hratio = int((up / (up + dn) * 100)) if (up + dn) > 0 else 100
top_h = sorted(habits, key=lambda x: x.get("counterUp", 0), reverse=True)[:3]

if db["last_daily_date"] != now.strftime("%Y-%m-%d"):
    db["last_daily_date"] = now.strftime("%Y-%m-%d")
    db["daily_habit_baseline"] = up
    
h_today = max(0, up - db["daily_habit_baseline"])
t_today = sum(1 for t in c_res if t.get("dateCompleted") and datetime.fromisoformat(t["dateCompleted"].replace("Z", "+00:00")).astimezone(WIB).strftime("%Y-%m-%d") == now.strftime("%Y-%m-%d"))
t_active = len([t for t in t_res if t.get("type") == "todo"])

# BARIS INI YANG KEMARIN HILANG: Menghitung total keseluruhan
todos_cleared_total = len(c_res)
grand_total_completed = up + todos_cleared_total + len(done)

streak = max([t.get("streak", 0) for t in dailies], default=0)
days = max(1, (now.weekday() if now.hour >= 6 else (now.weekday() - 1) % 7) + 1)
avg_dmg = db["weekly_damage"] / days

with open(DB_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=2)

def fmt(n): return f"{n/1000000:.2f}M" if n>=1000000 else f"{n/1000:.1f}K" if n>=1000 else str(int(n))

# 4. AUTO-UPDATE BIO MARKDOWN
bar = "█" * int((pct/100)*10) + "░" * (10 - int((pct/100)*10))
md_h = "\n".join([f"{i+1}. {html.escape(h.get('text')[:24])} (+{h.get('counterUp', 0)})" for i, h in enumerate(top_h)]) or "-"
md_d = "\n".join([f"{i+1}. {d[0][:24]} ({d[1]}x)" for i, d in enumerate(top_d)]) or "-"

bio = f"""[![HD Card](https://raw.githubusercontent.com/teddytohari/habitica-stats/main/profile-stats.png)](https://raw.githubusercontent.com/teddytohari/habitica-stats/main/profile-stats.png)

### ⚔️ {p_name} (Lv. {lvl} {c_class.upper()})
🔥 **Streak:** {streak} Days | 💰 **Peak Gold:** {fmt(db['peak_gold'])}

**▬▬ 🛡️ COMBAT & EXPEDITION ▬▬**
⚔️ **Total Dmg:** {fmt(db['all_time_damage'])} | 🗡️ **Weekly Dmg:** {fmt(db['weekly_damage'])}
🏆 **Bosses Slain:** {db['bosses_slain']} | ✨ **Buffs:** {db['buffs_cast']}

**▬▬ 📋 PRODUCTIVITY MATRIX ▬▬**
**Dailies Today:** {len(done)}/{len(due)} ({pct}%)
`{bar}`
👍 **Habit Mastery:** {hratio}% Positive
✅ **Cleared Today:** ✨{h_today} | 📋{len(done)} | 🎯{t_today}

**🔥 TOP 3 HABITS**
{md_h}

**🏆 TOP 3 DAILIES**
{md_d}
"""
try: requests.put("https://habitica.com/api/v3/user", headers=headers, json={"profile.blurb": bio.replace("    ", "")})
except: pass

# 5. GENERATE HD SVG/PNG
bg_img = ""
try:
    bg_k = u_res.get("preferences", {}).get("background", "violet")
    bg_r = requests.get(f"https://habitica-assets.s3.amazonaws.com/mobileApp/images/background_{bg_k}.png", timeout=5)
    if bg_r.status_code == 200: bg_img = f'<image xlink:href="data:image/png;base64,{base64.b64encode(bg_r.content).decode("utf-8")}" x="0" y="0" width="460" height="110" preserveAspectRatio="xMidYMid slice" opacity="0.35"/>'
except: pass

cfg = {"warrior": {"sec": "#fb7185", "bg": "#3a0914", "n": "WARRIOR"}, "mage": {"sec": "#60a5fa", "bg": "#0f172a", "n": "ARCHMAGE"}, "rogue": {"sec": "#fbbf24", "bg": "#321706", "n": "SHADOW ROGUE"}, "healer": {"sec": "#34d399", "bg": "#062b20", "n": "HIGH HEALER"}}.get(c_class, {"sec": "#fb7185", "bg": "#3a0914", "n": "WARRIOR"})

h_str = "".join([f'<text x="28" y="{612+i*18}" class="list">{i+1}. {html.escape(h.get("text", "")[:28])} (+{h.get("counterUp", 0)})</text>' for i, h in enumerate(top_h)])
d_str = "".join([f'<text x="28" y="{712+i*18}" class="list">{i+1}. {d[0][:28]} ({d[1]}x)</text>' for i, d in enumerate(top_d)])

svg = f"""<svg width="920" height="1820" viewBox="0 0 460 910" fill="none" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
  <defs>
    <clipPath id="rc"><rect width="460" height="910" rx="18"/></clipPath>
    <linearGradient id="g1" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#141724"/><stop offset="100%" stop-color="#07080f"/></linearGradient>
    <linearGradient id="gB" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#f59e0b"/><stop offset="100%" stop-color="#78350f"/></linearGradient>
    <linearGradient id="gC" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#24121b"/><stop offset="100%" stop-color="#180c13"/></linearGradient>
    <linearGradient id="gP" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#12182b"/><stop offset="100%" stop-color="#0b101e"/></linearGradient>
    <linearGradient id="gH" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#211710"/><stop offset="100%" stop-color="#140d07"/></linearGradient>
    <linearGradient id="gD" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#0f2119"/><stop offset="100%" stop-color="#07140e"/></linearGradient>
    <linearGradient id="gI" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#1a1226"/><stop offset="100%" stop-color="#0e0a16"/></linearGradient>
    <linearGradient id="gBar" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#10b981"/><stop offset="100%" stop-color="#34d399"/></linearGradient>
  </defs>
  <style>
    .t {{ font-family: 'Noto Sans CJK JP', 'Segoe UI Emoji', sans-serif; font-weight: 800; fill: #fff; }}
    .s {{ font-family: 'Noto Sans CJK JP', 'Segoe UI Emoji', sans-serif; font-size: 11.5px; fill: #94a3b8; }}
    .l {{ font-family: 'Noto Sans CJK JP', 'Segoe UI Emoji', sans-serif; font-size: 9.5px; fill: #94a3b8; font-weight: 600; }}
    .v {{ font-family: 'Noto Sans CJK JP', 'Segoe UI Emoji', sans-serif; font-size: 14px; font-weight: bold; fill: #f8fafc; }}
    .list {{ font-family: 'Noto Sans CJK JP', 'Segoe UI Emoji', sans-serif; font-size: 11.5px; fill: #cbd5e1; }}
  </style>
  <g clip-path="url(#rc)">
    <rect width="460" height="910" fill="url(#g1)"/>
    {bg_img}
    <rect width="460" height="110" fill="#0b0e18" opacity="0.6"/>
    <line x1="0" y1="110" x2="460" y2="110" stroke="url(#gB)" stroke-width="1.5"/>
    
    <rect x="22" y="18" width="62" height="62" rx="12" fill="{cfg['bg']}" stroke="{cfg['sec']}" stroke-width="2"/>
    <path d="M 38 34 L 68 64" stroke="#f8fafc" stroke-width="2.8" stroke-linecap="round"/>
    <path d="M 68 34 L 38 64" stroke="#f8fafc" stroke-width="2.8" stroke-linecap="round"/>
    <circle cx="53" cy="49" r="6" fill="#f59e0b" stroke="#78350f" stroke-width="1.2"/>
    
    <text x="98" y="44" class="t" font-size="18">{p_name}</text>
    <text x="98" y="64" class="s">Level {lvl} • <tspan fill="{cfg['sec']}">{cfg['n']}</tspan></text>
    <text x="98" y="82" font-family="sans-serif" font-size="9.5" fill="#f59e0b" font-weight="bold">★ ACTIVE CHAMPION OF HABITICA ★</text>
    
    <text x="18" y="132" font-family="sans-serif" font-size="11" fill="#fb7185" font-weight="bold">⚔️ COMBAT &amp; EXPEDITION LOG</text>
    <rect x="16" y="142" width="208" height="46" rx="8" fill="url(#gC)" stroke="#4c1d2c"/><text x="26" y="158" class="l">TOTAL DMG (ALL-TIME)</text><text x="26" y="177" class="v">⚔️ {fmt(db['all_time_damage'])}</text>
    <rect x="236" y="142" width="208" height="46" rx="8" fill="url(#gC)" stroke="#4c1d2c"/><text x="246" y="158" class="l">WEEKLY DMG (RESET MON)</text><text x="246" y="177" class="v">🗡️ {fmt(db['weekly_damage'])}</text>
    <rect x="16" y="196" width="208" height="46" rx="8" fill="url(#gC)" stroke="#4c1d2c"/><text x="26" y="212" class="l">DAILY AVG DMG</text><text x="26" y="231" class="v">📊 {fmt(avg_dmg)}/day</text>
    <rect x="236" y="196" width="208" height="46" rx="8" fill="url(#gC)" stroke="#4c1d2c"/><text x="246" y="212" class="l">PEAK WEEKLY RECORD</text><text x="246" y="231" class="v">🔥 {fmt(db['peak_weekly_damage'])}</text>
    <rect x="16" y="250" width="208" height="46" rx="8" fill="url(#gC)" stroke="#4c1d2c"/><text x="26" y="266" class="l">BOSSES SLAIN</text><text x="26" y="285" class="v">🏆 {db['bosses_slain']}</text>
    <rect x="236" y="250" width="208" height="46" rx="8" fill="url(#gC)" stroke="#4c1d2c"/><text x="246" y="266" class="l">PEAK GOLD HOARDED</text><text x="246" y="285" class="v" fill="#fbbf24">💰 {fmt(db['peak_gold'])} G</text>
    <rect x="16" y="304" width="428" height="36" rx="8" fill="url(#gC)" stroke="#4c1d2c"/><text x="26" y="327" class="s">✨ Buffs: <tspan class="v">{db['buffs_cast']}</tspan> Casts • 💧 Mana Spent: <tspan class="v">{fmt(db['total_mana_spent'])} MP</tspan></text>
    
    <text x="18" y="374" font-family="sans-serif" font-size="11" fill="#60a5fa" font-weight="bold">📋 PRODUCTIVITY &amp; DISCIPLINE MATRIX</text>
    <text x="18" y="394" class="s">Dailies Today: <tspan class="v">{len(done)}/{len(due)} ({pct}%)</tspan></text>
    <rect x="16" y="402" width="428" height="11" rx="5.5" fill="#151b2e"/><rect x="16" y="402" width="{int(428*(pct/100))}" height="11" rx="5.5" fill="url(#gBar)"/>
    <rect x="16" y="421" width="428" height="34" rx="7" fill="url(#gP)" stroke="#1e293b"/><text x="26" y="442" class="s">Habit Mastery: <tspan class="v">{hratio}% Positive</tspan> ({up} 👍 / {dn} 👎)</text>
    
    <rect x="16" y="463" width="101" height="46" rx="7" fill="#1f1610" stroke="#b45309"/><text x="22" y="479" class="l">HABITS TODAY</text><text x="22" y="499" class="v">✨ {h_today}</text>
    <rect x="125" y="463" width="101" height="46" rx="7" fill="#0d1f18" stroke="#059669"/><text x="131" y="479" class="l">DAILIES TODAY</text><text x="131" y="499" class="v">📋 {len(done)}</text>
    <rect x="234" y="463" width="101" height="46" rx="7" fill="#0f1f33" stroke="#0284c7"/><text x="240" y="479" class="l">TO-DOS TODAY</text><text x="240" y="499" class="v">🎯 {t_today}</text>
    <rect x="343" y="463" width="101" height="46" rx="7" fill="#241b0b" stroke="#ca8a04"/><text x="349" y="479" class="l">ALL COMPLETED</text><text x="349" y="499" class="v" fill="#fbbf24">⭐ {fmt(grand_total_completed)}</text>
    
    <rect x="16" y="517" width="208" height="46" rx="8" fill="url(#gP)" stroke="#1e293b"/><text x="26" y="533" class="l">BOUNTY BOARD</text><text x="26" y="552" class="v">🎯 {t_active} Open / {todos_cleared_total} Cleared</text>
    <rect x="236" y="517" width="208" height="46" rx="8" fill="url(#gP)" stroke="#1e293b"/><text x="246" y="533" class="l">DISCIPLINE FLAME</text><text x="246" y="552" class="v">🔥 {streak} Days Streak</text>
    
    <rect x="16" y="571" width="428" height="92" rx="8" fill="url(#gH)" stroke="#78350f"/><text x="28" y="591" font-family="sans-serif" font-size="11" font-weight="bold" fill="#f59e0b">🔥 TOP 3 HABITS (MOST ACTIVE)</text>{h_str}
    <rect x="16" y="671" width="428" height="92" rx="8" fill="url(#gD)" stroke="#064e3b"/><text x="28" y="691" font-family="sans-serif" font-size="11" font-weight="bold" fill="#10b981">🏆 TOP 3 DAILIES (WEEKLY)</text>{d_str}
    
    <rect x="16" y="787" width="428" height="96" rx="9" fill="url(#gI)" stroke="#6d28d9"/><text x="28" y="810" font-family="Georgia, serif" font-size="11" font-weight="bold" fill="#facc15">📜 SCROLL OF INSIGHT</text><text x="28" y="832" font-family="Georgia, serif" font-size="12" font-style="italic" fill="#e2e8f0"><tspan x="28" dy="0">Consistency is not perfection,</tspan><tspan x="28" dy="18">it is simply refusing to give up.</tspan></text>
  </g>
  <rect width="460" height="910" rx="18" fill="none" stroke="url(#gB)" stroke-width="3.5"/>
</svg>"""

with open("profile-stats.svg", "w", encoding="utf-8") as f: f.write(svg)

try:
    import cairosvg
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to="profile-stats.png")
except Exception as e: print(f"PNG Error: {e}")
