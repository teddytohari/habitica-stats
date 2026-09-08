import os, json, html, base64, requests
from datetime import datetime, timezone, timedelta

# 1. Credentials & Setup
USER_ID = os.environ.get("HABITICA_USER_ID")
API_TOKEN = os.environ.get("HABITICA_API_TOKEN")
WIB = timezone(timedelta(hours=7))
headers = {"x-api-user": USER_ID, "x-api-key": API_TOKEN, "x-client": f"{USER_ID}-RPGStatsCard"}

# 2. Local Database
DB_FILE = "database.json"
db = {"current_cycle_id": "", "classes_used": [], "peak_gold": 0.0, "total_mana_spent": 0.0, "last_mana": None, "buffs_cast": 0, "bosses_slain": 0, "all_time_damage": 0.0, "weekly_damage": 0.0, "peak_weekly_damage": 0.0, "last_damage_up": 0.0, "weekly_top_dailies": {}, "last_daily_date": "", "daily_habit_baseline": 0}
if os.path.exists(DB_FILE):
    with open(DB_FILE, "r", encoding="utf-8") as f: db.update(json.load(f))

now = datetime.now(WIB)
cycle = f"{(now - timedelta(hours=6)).year}-W{(now - timedelta(hours=6)).isocalendar()[1]}"
if db["current_cycle_id"] != cycle:
    db["peak_weekly_damage"] = max(db["peak_weekly_damage"], db["weekly_damage"])
    db["weekly_damage"] = 0.0; db["weekly_top_dailies"] = {}; db["current_cycle_id"] = cycle

# 3. Fetch Data API
u_res = requests.get("https://habitica.com/api/v3/user", headers=headers).json().get("data", {})
t_res = requests.get("https://habitica.com/api/v3/tasks/user", headers=headers).json().get("data", [])
c_res = requests.get("https://habitica.com/api/v3/tasks/user?type=completedTodos", headers=headers).json().get("data", [])

if not isinstance(t_res, list): t_res = []
if not isinstance(c_res, list): c_res = []

p_name = html.escape(u_res.get("profile", {}).get("name", "Hero")[:18])
c_class = u_res.get("stats", {}).get("class", "warrior").lower()
lvl = u_res.get("stats", {}).get("lvl", 1)
gold = u_res.get("stats", {}).get("gp", 0.0)
mp = u_res.get("stats", {}).get("mp", 0.0)

if c_class not in db["classes_used"]: db["classes_used"].append(c_class)
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
t_cleared = len(c_res)
g_total = up + t_cleared + len(done)

streak = max([t.get("streak", 0) for t in dailies], default=0)
days = max(1, (now.weekday() if now.hour >= 6 else (now.weekday() - 1) % 7) + 1)
avg_dmg = db["weekly_damage"] / days

with open(DB_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=2)
def fmt(n): return f"{n/1000000:.2f}M" if n>=1000000 else f"{n/1000:.1f}K" if n>=1000 else str(int(n))

quote_text = "Small daily disciplines lead to monumental achievements over time."
if os.path.exists("quote.txt"):
    with open("quote.txt", "r", encoding="utf-8") as qf:
        lines = [line.strip() for line in qf.readlines() if line.strip()]
        if lines: quote_text = " ".join(lines)

# 4. AUTO-UPDATE BIO (DESAIN SHIELDS PROFESIONAL)
bio = f"""### ⚔️ {p_name.upper()} — Level {lvl} {c_class.capitalize()}

![](https://img.shields.io/badge/Level-{lvl}_{c_class.upper()}-432874?style=for-the-badge&labelColor=141724)
![](https://img.shields.io/badge/Total_Dmg-{fmt(db['all_time_damage'])}-880e4f?style=for-the-badge&labelColor=141724)
![](https://img.shields.io/badge/Streak-{streak}_Days-e65100?style=for-the-badge&labelColor=141724)
![](https://img.shields.io/badge/Peak_Gold-{fmt(db['peak_gold'])}-f57f17?style=for-the-badge&labelColor=141724)
![](https://img.shields.io/badge/Dailies_Today-{len(done)}%2F{len(due)}-1b5e20?style=for-the-badge&labelColor=141724)

---
> "{quote_text}"
---
📊 **[Lihat Kartu Statistik HD →](https://raw.githubusercontent.com/teddytohari/habitica-stats/main/profile-stats.png?v=9)**
"""
try: requests.put("https://habitica.com/api/v3/user", headers=headers, json={"profile.blurb": bio.replace("    ", "")})
except: pass

# 5. FETCH ASSETS & DRAW ICONS NATIF (Tanpa Emoji)
logo_img = bg_img = ""
try:
    l_r = requests.get("https://habitica.com/static/img/apple-touch-icon-144x144.png", timeout=5)
    if l_r.status_code == 200: logo_img = f'<image xlink:href="data:image/png;base64,{base64.b64encode(l_r.content).decode("utf-8")}" x="16" y="25" width="80" height="80" clip-path="url(#lc)"/>'
except: pass
try:
    b_r = requests.get("https://habitica-assets.s3.amazonaws.com/mobileApp/images/background_woods.png", timeout=5)
    if b_r.status_code == 200: bg_img = f'<image xlink:href="data:image/png;base64,{base64.b64encode(b_r.content).decode("utf-8")}" x="0" y="0" width="460" height="130" preserveAspectRatio="xMidYMid slice" opacity="0.4"/>'
except: pass

# Vektor Murni (Anti Error Kotak Silang)
ic_sw = '<path d="M4 20L20 4M8 20L20 8" stroke="#fb7185" stroke-width="2.5" stroke-linecap="round"/>'
ic_fr = '<path d="M12 22C12 22 5 15 5 10C5 6 8 2 12 2C12 2 10 6 10 10C10 12 12 14 12 14C12 14 15 11 15 8C17 10 19 13 19 16C19 19.5 16 22 12 22Z" fill="#f59e0b"/>'
ic_tr = '<path d="M4 6H20M5 6V11C5 14.8 8.1 18 12 18C15.9 18 19 14.8 19 11V6M8 18V22M16 18V22M6 22H18" stroke="#facc15" stroke-width="2" stroke-linecap="round" fill="none"/>'
ic_gd = '<circle cx="12" cy="12" r="8" fill="#f59e0b"/><text x="12" y="16" font-size="11" fill="#141724" text-anchor="middle" font-weight="bold" font-family="sans-serif">G</text>'
ic_ch = '<path d="M18 20V10M12 20V4M6 20V14" stroke="#60a5fa" stroke-width="2.5" stroke-linecap="round"/>'
ic_sp = '<path d="M12 2L14 9L21 11L14 13L12 20L10 13L3 11L10 9Z" fill="#b45309"/>'
ic_ck = '<path d="M5 12L10 17L19 7" stroke="#059669" stroke-width="2.5" stroke-linecap="round" fill="none"/>'
ic_tg = '<circle cx="12" cy="12" r="8" stroke="#0284c7" stroke-width="2" fill="none"/><circle cx="12" cy="12" r="3" fill="#0284c7"/>'
ic_st = '<path d="M12 2L15 9L22 9L16 14L18 21L12 17L6 21L8 14L2 9L9 9Z" fill="#ca8a04"/>'

h_str = "".join([f'<text x="28" y="{632+i*18}" class="list">{i+1}. {html.escape(h.get("text", "")[:28])} (+{h.get("counterUp", 0)})</text>' for i, h in enumerate(top_h)])
d_str = "".join([f'<text x="28" y="{732+i*18}" class="list">{i+1}. {d[0][:28]} ({d[1]}x)</text>' for i, d in enumerate(top_d)])

cfg = {"warrior": {"sec": "#fb7185", "bg": "#3a0914", "n": "WARRIOR"}, "mage": {"sec": "#60a5fa", "bg": "#0f172a", "n": "ARCHMAGE"}, "rogue": {"sec": "#fbbf24", "bg": "#321706", "n": "SHADOW ROGUE"}, "healer": {"sec": "#34d399", "bg": "#062b20", "n": "HIGH HEALER"}}.get(c_class, {"sec": "#fb7185", "bg": "#3a0914", "n": "WARRIOR"})

svg = f"""<svg width="920" height="1860" viewBox="0 0 460 930" fill="none" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
  <defs>
    <clipPath id="rc"><rect width="460" height="930" rx="18"/></clipPath>
    <clipPath id="lc"><rect x="16" y="25" width="80" height="80" rx="16"/></clipPath>
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
    .t {{ font-family: sans-serif; font-weight: 900; fill: #fff; }}
    .s {{ font-family: sans-serif; font-size: 11.5px; fill: #94a3b8; }}
    .l {{ font-family: sans-serif; font-size: 9.5px; fill: #94a3b8; font-weight: 600; letter-spacing: 0.5px; }}
    .v {{ font-family: sans-serif; font-size: 14px; font-weight: bold; fill: #f8fafc; }}
    .list {{ font-family: sans-serif; font-size: 11.5px; fill: #cbd5e1; }}
  </style>
  <g clip-path="url(#rc)">
    <rect width="460" height="930" fill="url(#g1)"/>
    {bg_img}
    <rect width="460" height="130" fill="#0b0e18" opacity="0.6"/>
    <line x1="0" y1="130" x2="460" y2="130" stroke="url(#gB)" stroke-width="1.5"/>
    
    {logo_img if logo_img else f'<rect x="16" y="25" width="80" height="80" rx="16" fill="#432874" stroke="#fff" stroke-width="2"/><text x="56" y="75" fill="#fff" font-size="44" font-weight="bold" font-family="serif" text-anchor="middle">H</text>'}
    
    <text x="110" y="50" class="t" font-size="20">{p_name}</text>
    <text x="110" y="72" class="s">Level {lvl} • <tspan fill="{cfg['sec']}">{cfg['n']}</tspan></text>
    <text x="110" y="94" font-family="sans-serif" font-size="10" font-weight="bold">
      <tspan fill="#fb7185" opacity="{1.0 if 'warrior' in db['classes_used'] else 0.3}">WAR</tspan>
      <tspan fill="#60a5fa" opacity="{1.0 if 'mage' in db['classes_used'] else 0.3}" dx="12">MAG</tspan>
      <tspan fill="#f59e0b" opacity="{1.0 if 'rogue' in db['classes_used'] else 0.3}" dx="12">ROG</tspan>
      <tspan fill="#34d399" opacity="{1.0 if 'healer' in db['classes_used'] else 0.3}" dx="12">HEA</tspan>
    </text>
    
    <text x="18" y="152" font-family="sans-serif" font-size="11" fill="#fb7185" font-weight="bold">COMBAT &amp; EXPEDITION LOG</text>
    <rect x="16" y="162" width="208" height="46" rx="8" fill="url(#gC)" stroke="#4c1d2c"/><text x="26" y="178" class="l">TOTAL DMG</text><g transform="translate(26, 183) scale(0.8)">{ic_sw}</g><text x="50" y="197" class="v">{fmt(db['all_time_damage'])}</text>
    <rect x="236" y="162" width="208" height="46" rx="8" fill="url(#gC)" stroke="#4c1d2c"/><text x="246" y="178" class="l">WEEKLY DMG</text><g transform="translate(246, 183) scale(0.8)">{ic_sw}</g><text x="270" y="197" class="v">{fmt(db['weekly_damage'])}</text>
    <rect x="16" y="216" width="208" height="46" rx="8" fill="url(#gC)" stroke="#4c1d2c"/><text x="26" y="232" class="l">DAILY AVG DMG</text><g transform="translate(26, 237) scale(0.8)">{ic_ch}</g><text x="50" y="251" class="v">{fmt(avg_dmg)}/day</text>
    <rect x="236" y="216" width="208" height="46" rx="8" fill="url(#gC)" stroke="#4c1d2c"/><text x="246" y="232" class="l">PEAK WEEKLY RECORD</text><g transform="translate(246, 237) scale(0.8)">{ic_fr}</g><text x="270" y="251" class="v">{fmt(db['peak_weekly_damage'])}</text>
    <rect x="16" y="270" width="208" height="46" rx="8" fill="url(#gC)" stroke="#4c1d2c"/><text x="26" y="286" class="l">BOSSES SLAIN</text><g transform="translate(26, 291) scale(0.8)">{ic_tr}</g><text x="50" y="305" class="v">{db['bosses_slain']}</text>
    <rect x="236" y="270" width="208" height="46" rx="8" fill="url(#gC)" stroke="#4c1d2c"/><text x="246" y="286" class="l">PEAK GOLD HOARDED</text><g transform="translate(246, 291) scale(0.8)">{ic_gd}</g><text x="270" y="305" class="v" fill="#fbbf24">{fmt(db['peak_gold'])} G</text>
    <rect x="16" y="324" width="428" height="36" rx="8" fill="url(#gC)" stroke="#4c1d2c"/><text x="26" y="347" class="s">✨ Buffs: <tspan class="v">{db['buffs_cast']}</tspan> Casts • 💧 Mana Spent: <tspan class="v">{fmt(db['total_mana_spent'])} MP</tspan></text>
    
    <text x="18" y="394" font-family="sans-serif" font-size="11" fill="#60a5fa" font-weight="bold">PRODUCTIVITY &amp; DISCIPLINE MATRIX</text>
    <text x="18" y="414" class="s">Dailies Today: <tspan class="v">{len(done)}/{len(due)} ({pct}%)</tspan></text>
    <rect x="16" y="422" width="428" height="11" rx="5.5" fill="#151b2e"/><rect x="16" y="422" width="{int(428*(pct/100))}" height="11" rx="5.5" fill="url(#gBar)"/>
    <rect x="16" y="441" width="428" height="34" rx="7" fill="url(#gP)" stroke="#1e293b"/><text x="26" y="462" class="s">Habit Mastery: <tspan class="v">{hratio}% Positive</tspan> ({up} 👍 / {dn} 👎)</text>
    
    <rect x="16" y="483" width="101" height="46" rx="7" fill="#1f1610" stroke="#b45309"/><text x="22" y="499" class="l">HABITS TODAY</text><g transform="translate(22, 503) scale(0.75)">{ic_sp}</g><text x="44" y="518" class="v">{h_today}</text>
    <rect x="125" y="483" width="101" height="46" rx="7" fill="#0d1f18" stroke="#059669"/><text x="131" y="499" class="l">DAILIES TODAY</text><g transform="translate(131, 503) scale(0.75)">{ic_ck}</g><text x="153" y="518" class="v">{len(done)}</text>
    <rect x="234" y="483" width="101" height="46" rx="7" fill="#0f1f33" stroke="#0284c7"/><text x="240" y="499" class="l">TO-DOS TODAY</text><g transform="translate(240, 503) scale(0.75)">{ic_tg}</g><text x="262" y="518" class="v">{t_today}</text>
    <rect x="343" y="483" width="101" height="46" rx="7" fill="#241b0b" stroke="#ca8a04"/><text x="349" y="499" class="l">ALL COMPLETED</text><g transform="translate(349, 503) scale(0.75)">{ic_st}</g><text x="371" y="518" class="v" fill="#fbbf24">{fmt(g_total)}</text>
    
    <rect x="16" y="537" width="208" height="46" rx="8" fill="url(#gP)" stroke="#1e293b"/><text x="26" y="553" class="l">BOUNTY BOARD</text><g transform="translate(26, 558) scale(0.8)">{ic_tg}</g><text x="50" y="572" class="v">{t_active} Open / {t_cleared} Done</text>
    <rect x="236" y="537" width="208" height="46" rx="8" fill="url(#gP)" stroke="#1e293b"/><text x="246" y="553" class="l">DISCIPLINE FLAME</text><g transform="translate(246, 558) scale(0.8)">{ic_fr}</g><text x="270" y="572" class="v">{streak} Days Streak</text>
    
    <rect x="16" y="591" width="428" height="92" rx="8" fill="url(#gH)" stroke="#78350f"/><text x="28" y="611" font-family="sans-serif" font-size="11" font-weight="bold" fill="#f59e0b">TOP 3 HABITS (MOST ACTIVE)</text>{h_str}
    <rect x="16" y="691" width="428" height="92" rx="8" fill="url(#gD)" stroke="#064e3b"/><text x="28" y="711" font-family="sans-serif" font-size="11" font-weight="bold" fill="#10b981">TOP 3 DAILIES (WEEKLY)</text>{d_str}
    
    <rect x="16" y="807" width="428" height="96" rx="9" fill="url(#gI)" stroke="#6d28d9"/><text x="28" y="830" font-family="Georgia, serif" font-size="11" font-weight="bold" fill="#facc15">SCROLL OF INSIGHT</text><text x="28" y="852" font-family="Georgia, serif" font-size="12" font-style="italic" fill="#e2e8f0"><tspan x="28" dy="0">Consistency is not perfection,</tspan><tspan x="28" dy="18">it is simply refusing to give up.</tspan></text>
  </g>
  <rect width="460" height="930" rx="18" fill="none" stroke="url(#gB)" stroke-width="3.5"/>
</svg>"""

with open("profile-stats.svg", "w", encoding="utf-8") as f: f.write(svg)

try:
    import cairosvg
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to="profile-stats.png")
except Exception as e: print(f"PNG Error: {e}")
