from pathlib import Path

import discord
from discord.ext import commands, tasks
import sqlite3
import random
import asyncio
import json
import os
import contextvars
from datetime import datetime, timedelta

# =========================================================
# Sky Strike - النسخة النهائية
# الملف: main.py
# قاعدة البيانات: sky_strike_final.db
# =========================================================

DB_FILE = "sky_strike_final.db"
ADMIN_ROLE_ID = 1554501312140546199

GUILD_CONTEXT = contextvars.ContextVar("skystrike_guild_id", default=None)

def set_guild_context(guild_id):
    if guild_id is not None:
        GUILD_CONTEXT.set(int(guild_id))

def current_guild_id():
    guild_id = GUILD_CONTEXT.get()
    if guild_id is None:
        raise RuntimeError("لم يتم تحديد السيرفر الحالي.")
    return int(guild_id)

def guild_db_file(guild_id):
    return f"sky_strike_{int(guild_id)}.db"

if not os.path.exists("config.json"):
    print("❌ ملف config.json غير موجود!")
    raise SystemExit

with open("config.json", "r", encoding="utf-8") as f:
    config_data = json.load(f)

TOKEN = config_data.get("BOT_TOKEN")
ALLOWED_CHANNELS = config_data.get("ALLOWED_CHANNELS", [])

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="",
    intents=intents,
    help_command=None
)

# =========================================================
# الأسلحة وقوتها وأسعارها الافتراضية
# =========================================================

WEAPONS = {
    "مسيرة_انتحارية": {
        "column": "kamikaze_drones",
        "price": 1500,
        "strength": 1,
        "label": "🛸 مسيرة انتحارية"
    },
    "صاروخ_باليستي": {
        "column": "ballistic_missiles",
        "price": 6000,
        "strength": 6,
        "label": "🚀 صاروخ باليستي"
    },
    "صاروخ_كروز": {
        "column": "cruise_missiles",
        "price": 12000,
        "strength": 10,
        "label": "🏹 صاروخ كروز"
    },
    "صاروخ_فرط_صوتي": {
        "column": "hypersonic_missiles",
        "price": 30000,
        "strength": 20,
        "label": "⚡ صاروخ فرط صوتي"
    },
    "كروز_متقدم": {
        "column": "advanced_cruise_missiles",
        "price": 18000,
        "strength": 14,
        "label": "🎯 صاروخ كروز متقدم"
    },
    "إف35": {
        "column": "f35_jets",
        "price": 15000,
        "strength": 12,
        "label": "✈️ إف-35"
    },
    "سوخوي35": {
        "column": "su35_jets",
        "price": 8000,
        "strength": 9,
        "label": "🛩️ سوخوي-35"
    },
    "رافال": {
        "column": "rafale_jets",
        "price": 6000,
        "strength": 7,
        "label": "🇫🇷 رافال"
    }
}

DEFENSE_ITEMS = {
    "ثاد": {
        "column": "thaad_level",
        "price": 25000,
        "strength": 18,
        "label": "📡 ثاد THAAD"
    },
    "إس400": {
        "column": "s400_level",
        "price": 20000,
        "strength": 14,
        "label": "🛡️ إس-400"
    },
    "التشويش": {
        "column": "jammer_level",
        "price": 15000,
        "strength": 5,
        "label": "📻 التشويش"
    },
    "الخزنة": {
        "column": "vault_level",
        "price": 12000,
        "strength": 0,
        "label": "🔐 الخزنة"
    },
    "الأقمار": {
        "column": "satellite_level",
        "price": 18000,
        "strength": 4,
        "label": "🛰️ الأقمار"
    },
    "صاروخ_اعتراضي": {
        "column": "interceptor_missiles",
        "price": 9000,
        "strength": 5,
        "label": "🧨 صاروخ اعتراضي"
    }
}

ALL_SHOP_ITEMS = {**WEAPONS, **DEFENSE_ITEMS}

# تكلفة كل هجوم: تحريك منصات الصواريخ + مؤونة الجنود.
ATTACK_PLATFORM_COST = 3000
REWARD_COOLDOWN_MINUTES = 4
last_reward_times = {}  # (guild_id, user_id)

# =========================================================
# نظام الصناديق العشوائية
# =========================================================

CHESTS = {
    "عادي": {
        "label": "🟫 الصندوق العادي",
        "price": 5000,
        "color": discord.Color.light_grey(),
        "rewards": [
            ("gold", 40, 2000, 6000, "🪙"),
            ("gold", 35, 6000, 10000, "🪙"),
            ("weapon", 20, "مسيرة_انتحارية", 5, "🛸"),
            ("weapon", 5, "صاروخ_باليستي", 1, "🚀"),
        ]
    },
    "نادر": {
        "label": "🟦 الصندوق النادر",
        "price": 15000,
        "color": discord.Color.blue(),
        "rewards": [
            ("gold", 35, 10000, 18000, "🪙"),
            ("gold", 30, 18000, 30000, "🪙"),
            ("weapon", 20, "صاروخ_باليستي", 3, "🚀"),
            ("weapon", 10, "صاروخ_كروز", 2, "🏹"),
            ("weapon", 4, "إف35", 1, "✈️"),
            ("weapon", 1, "صاروخ_فرط_صوتي", 1, "⚡"),
        ]
    },
    "أسطوري": {
        "label": "🟪 الصندوق الأسطوري",
        "price": 50000,
        "color": discord.Color.purple(),
        "rewards": [
            ("gold", 35, 40000, 70000, "🪙"),
            ("gold", 25, 70000, 120000, "🪙"),
            ("weapon", 15, "صاروخ_كروز", 5, "🏹"),
            ("weapon", 12, "صاروخ_فرط_صوتي", 3, "⚡"),
            ("weapon", 8, "إف35", 3, "✈️"),
            ("weapon", 4, "رافال", 5, "🛩️"),
            ("weapon", 1, "صاروخ_اعتراضي", 10, "🛡️"),
        ]
    }
}

CHEST_NAMES = {
    "مسيرة_انتحارية": "🛸 مسيرة انتحارية",
    "صاروخ_باليستي": "🚀 صاروخ باليستي",
    "صاروخ_كروز": "🏹 صاروخ كروز",
    "صاروخ_فرط_صوتي": "⚡ صاروخ فرط صوتي",
    "إف35": "✈️ إف-35",
    "سوخوي35": "✈️ سوخوي-35",
    "رافال": "🛩️ رافال",
    "صاروخ_اعتراضي": "🛡️ صاروخ اعتراضي",
}

# =========================================================
# قاعدة البيانات
# =========================================================

def get_db(guild_id=None):
    if guild_id is None:
        guild_id = current_guild_id()
    return sqlite3.connect(guild_db_file(guild_id))


def ensure_column(cursor, table, column, definition):
    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]

    if column not in columns:
        cursor.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


def init_db(guild_id):
    conn = get_db(guild_id)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            gold INTEGER DEFAULT 50000,
            trophies INTEGER DEFAULT 1000,
            rank_title TEXT DEFAULT 'مُجنّد',
            thaad_level INTEGER DEFAULT 0,
            s400_level INTEGER DEFAULT 0,
            jammer_level INTEGER DEFAULT 0,
            vault_level INTEGER DEFAULT 0,
            satellite_level INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            user_id INTEGER PRIMARY KEY,
            kamikaze_drones INTEGER DEFAULT 0,
            ballistic_missiles INTEGER DEFAULT 0,
            cruise_missiles INTEGER DEFAULT 0,
            f35_jets INTEGER DEFAULT 0,
            su35_jets INTEGER DEFAULT 0,
            rafale_jets INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS active_alliances (
            user_id INTEGER,
            ally_id INTEGER,
            status TEXT DEFAULT 'active',
            PRIMARY KEY(user_id, ally_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS defense_alliances (
            user_id INTEGER,
            ally_id INTEGER,
            jets_committed INTEGER DEFAULT 0,
            f35_committed INTEGER DEFAULT 0,
            su35_committed INTEGER DEFAULT 0,
            rafale_committed INTEGER DEFAULT 0,
            PRIMARY KEY(user_id, ally_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS market_prices (
            item_name TEXT PRIMARY KEY,
            price INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cooldowns (
            user_id INTEGER PRIMARY KEY,
            last_attack TEXT DEFAULT NULL,
            last_mission TEXT DEFAULT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS chest_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chest_type TEXT NOT NULL,
            reward_text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_missions (
            user_id INTEGER PRIMARY KEY,
            mission_date TEXT NOT NULL,
            tasks_json TEXT NOT NULL,
            progress_json TEXT NOT NULL,
            claimed_json TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS market_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            amount INTEGER NOT NULL,
            price INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attack_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attacker_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            attack_type TEXT DEFAULT 'قصف',
            success INTEGER DEFAULT 0,
            stolen_gold INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pending_attacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER NOT NULL,
            attacker_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            attack_type TEXT DEFAULT 'قصف',
            created_at TEXT NOT NULL,
            status TEXT DEFAULT 'open'
        )
    """)

    # إضافة الأعمدة الجديدة للقاعدة القديمة بدون حذف البيانات.
    for col, definition in [
        ("hypersonic_missiles", "INTEGER DEFAULT 0"),
        ("advanced_cruise_missiles", "INTEGER DEFAULT 0"),
        ("interceptor_missiles", "INTEGER DEFAULT 0"),
    ]:
        ensure_column(cur, "inventory", col, definition)

    # توافق مع قواعد البيانات القديمة التي لم يكن فيها وقت آخر مهمة.
    ensure_column(cur, "cooldowns", "last_mission", "TEXT DEFAULT NULL")
    ensure_column(cur, "cooldowns", "last_exploration", "TEXT DEFAULT NULL")

    # يمنع استخدام الثأر أكثر من مرة على نفس آخر هجوم.
    ensure_column(cur, "attack_history", "revenge_used", "INTEGER DEFAULT 0")

    for col, definition in [
        ("f35_committed", "INTEGER DEFAULT 0"),
        ("su35_committed", "INTEGER DEFAULT 0"),
        ("rafale_committed", "INTEGER DEFAULT 0"),
    ]:
        ensure_column(cur, "defense_alliances", col, definition)

    default_prices = [
        ("مسيرة_انتحارية", 1500),
        ("صاروخ_باليستي", 6000),
        ("صاروخ_كروز", 12000),
        ("صاروخ_فرط_صوتي", 30000),
        ("كروز_متقدم", 18000),
        ("إف35", 15000),
        ("سوخوي35", 8000),
        ("رافال", 6000),
        ("ثاد", 25000),
        ("إس400", 20000),
        ("التشويش", 15000),
        ("الخزنة", 12000),
        ("الأقمار", 18000),
        ("صاروخ_اعتراضي", 9000)
    ]

    for item, price in default_prices:
        cur.execute(
            "INSERT OR IGNORE INTO market_prices (item_name, price) VALUES (?, ?)",
            (item, price)
        )

    conn.commit()
    conn.close()



# =========================================================
# أدوات عامة
# =========================================================

def register_user(user_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "INSERT OR IGNORE INTO players (user_id) VALUES (?)",
        (user_id,)
    )

    cur.execute(
        "INSERT OR IGNORE INTO inventory (user_id) VALUES (?)",
        (user_id,)
    )

    conn.commit()
    conn.close()


def has_base(user_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT 1 FROM players WHERE user_id = ?",
        (user_id,)
    )

    result = cur.fetchone() is not None
    conn.close()

    return result


DAILY_TASK_POOL = [
    {"id": "mission", "title": "🎯 نفّذ 2 مهمة", "target": 2, "reward": 12000},
    {"id": "shop", "title": "🛒 اشترِ 3 عناصر من المتجر", "target": 3, "reward": 10000},
    {"id": "chest", "title": "📦 افتح صندوقًا واحدًا", "target": 1, "reward": 15000},
    {"id": "exploration", "title": "🧭 نفّذ استكشافًا واحدًا", "target": 1, "reward": 12000},
    {"id": "market_buy", "title": "🏪 اشترِ عرضًا واحدًا من السوق", "target": 1, "reward": 18000},
]


def _ensure_daily_missions(user_id):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT mission_date, tasks_json, progress_json, claimed_json FROM daily_missions WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if row and row[0] == today:
        conn.close()
        return json.loads(row[1]), json.loads(row[2]), json.loads(row[3])

    tasks = random.sample(DAILY_TASK_POOL, 3)
    progress = {task["id"]: 0 for task in tasks}
    claimed = {task["id"]: False for task in tasks}
    cur.execute(
        "INSERT OR REPLACE INTO daily_missions (user_id, mission_date, tasks_json, progress_json, claimed_json) VALUES (?, ?, ?, ?, ?)",
        (user_id, today, json.dumps(tasks, ensure_ascii=False), json.dumps(progress, ensure_ascii=False), json.dumps(claimed, ensure_ascii=False))
    )
    conn.commit()
    conn.close()
    return tasks, progress, claimed


def progress_daily_task(user_id, task_id, amount=1):
    try:
        tasks, progress, claimed = _ensure_daily_missions(user_id)
        changed = False
        for task in tasks:
            if task["id"] == task_id:
                old = progress.get(task_id, 0)
                new = min(task["target"], old + amount)
                if new != old:
                    progress[task_id] = new
                    changed = True
                break
        if not changed:
            return
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE daily_missions SET progress_json = ? WHERE user_id = ?", (json.dumps(progress, ensure_ascii=False), user_id))
        conn.commit()
        conn.close()
    except Exception:
        pass


def claim_daily_rewards(user_id):
    tasks, progress, claimed = _ensure_daily_missions(user_id)
    total = 0
    completed = []
    for task in tasks:
        tid = task["id"]
        if progress.get(tid, 0) >= task["target"] and not claimed.get(tid, False):
            claimed[tid] = True
            total += task["reward"]
            completed.append(task)

    if total > 0:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE players SET gold = gold + ? WHERE user_id = ?", (total, user_id))
        cur.execute("UPDATE daily_missions SET claimed_json = ? WHERE user_id = ?", (json.dumps(claimed, ensure_ascii=False), user_id))
        conn.commit()
        conn.close()
    return completed, total


def daily_missions_embed(user_id):
    tasks, progress, claimed = _ensure_daily_missions(user_id)
    embed = discord.Embed(title="🎯 مهامك اليومية", color=discord.Color.blue())
    lines = []
    for index, task in enumerate(tasks, 1):
        current = progress.get(task["id"], 0)
        done = current >= task["target"]
        status = "🏆 تم الاستلام" if claimed.get(task["id"], False) else ("✅ مكتملة" if done else "⏳ قيد التقدم")
        lines.append(f"**{index}. {task['title']}**\n`{current}/{task['target']}` — 💰 `{task['reward']:,}` ذهب — {status}")
    embed.description = "\n\n".join(lines)
    embed.set_footer(text="المهام تتجدد تلقائيًا كل يوم")
    return embed


class DailyMissionsView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=180)
        self.user_id = user_id

    @discord.ui.button(label="🎁 استلام المكافآت", style=discord.ButtonStyle.success)
    async def claim(self, interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ هذه المهام ليست لك.", ephemeral=True)
            return
        set_guild_context(interaction.guild_id)
        completed, total = claim_daily_rewards(self.user_id)
        if not completed:
            await interaction.response.send_message("⏳ لا توجد مكافآت مكتملة وجاهزة للاستلام حاليًا.", ephemeral=True)
            return
        names = "\n".join(f"• {task['title']} — 💰 `{task['reward']:,}`" for task in completed)
        await interaction.response.send_message(
            f"🎉 **تم استلام مكافآت مهامك اليومية!**\n\n{names}\n\n💰 **إجمالي المكافأة:** `{total:,}` ذهب",
            ephemeral=True
        )

def get_gold(user_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT gold FROM players WHERE user_id = ?",
        (user_id,)
    )

    row = cur.fetchone()
    conn.close()

    return row[0] if row else 0


def get_price(item):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT price FROM market_prices WHERE item_name = ?",
        (item,)
    )

    row = cur.fetchone()
    conn.close()

    if row:
        return row[0]

    return ALL_SHOP_ITEMS.get(item, {}).get("price", 1000)


def set_price(item, price):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "INSERT OR REPLACE INTO market_prices (item_name, price) VALUES (?, ?)",
        (item, price)
    )

    conn.commit()
    conn.close()


def update_rank(user_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT trophies FROM players WHERE user_id = ?",
        (user_id,)
    )

    row = cur.fetchone()
    trophies = row[0] if row else 1000

    if trophies >= 3000:
        rank = "المشير الحربي 👑"
    elif trophies >= 2500:
        rank = "جنرال 🎖️"
    elif trophies >= 2000:
        rank = "عميد"
    elif trophies >= 1500:
        rank = "نقيب"
    elif trophies >= 1000:
        rank = "ملازم"
    else:
        rank = "مُجنّد"

    cur.execute(
        "UPDATE players SET rank_title = ? WHERE user_id = ?",
        (rank, user_id)
    )

    conn.commit()
    conn.close()

    return rank


def is_admin(member):
    return any(
        role.id == ADMIN_ROLE_ID
        for role in member.roles
    )


def reset_all_players():
    """إرجاع جميع اللاعبين إلى حالة البداية مع تنظيف بيانات المعارك والتحالفات."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE players
        SET
            gold = 50000,
            trophies = 1000,
            rank_title = 'مُجنّد',
            thaad_level = 0,
            s400_level = 0,
            jammer_level = 0,
            vault_level = 0,
            satellite_level = 0
    """)

    cur.execute("""
        UPDATE inventory
        SET
            kamikaze_drones = 0,
            ballistic_missiles = 0,
            cruise_missiles = 0,
            hypersonic_missiles = 0,
            advanced_cruise_missiles = 0,
            f35_jets = 0,
            su35_jets = 0,
            rafale_jets = 0,
            interceptor_missiles = 0
    """)

    cur.execute("DELETE FROM market_listings")
    cur.execute("DELETE FROM active_alliances")
    cur.execute("DELETE FROM defense_alliances")
    cur.execute("DELETE FROM attack_history")
    cur.execute("DELETE FROM pending_attacks")
    cur.execute("DELETE FROM cooldowns")
    cur.execute("DELETE FROM chest_history")
    cur.execute("DELETE FROM daily_missions")

    conn.commit()
    conn.close()

    guild_id = current_guild_id()
    for key in list(pending_joint_attacks.keys()):
        if key and key[0] == guild_id:
            pending_joint_attacks.pop(key, None)
    global pending_drop
    pending_drop.pop(guild_id, None)


def parse_amount(value):
    try:
        amount = int(value)
        if amount < 0:
            return None
        return amount
    except (ValueError, TypeError):
        return None


def format_remaining(td):
    seconds = max(0, int(td.total_seconds()))
    return f"{seconds // 60} دقيقة و {seconds % 60} ثانية"


def alliance_exists(user_a, user_b):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT 1
        FROM active_alliances
        WHERE (user_id = ? AND ally_id = ?)
           OR (user_id = ? AND ally_id = ?)
    """, (
        user_a,
        user_b,
        user_b,
        user_a
    ))

    result = cur.fetchone() is not None

    conn.close()
    return result


def get_attack_cooldown(user_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT last_attack FROM cooldowns WHERE user_id = ?",
        (user_id,)
    )

    row = cur.fetchone()
    conn.close()

    if not row or not row[0]:
        return None

    try:
        return datetime.strptime(
            row[0],
            "%Y-%m-%d %H:%M:%S"
        )
    except ValueError:
        return None


def set_attack_cooldown(user_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO cooldowns (user_id, last_attack)
        VALUES (?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET last_attack = excluded.last_attack
    """, (
        user_id,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()


def get_exploration_cooldown(user_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT last_exploration FROM cooldowns WHERE user_id = ?",
        (user_id,)
    )

    row = cur.fetchone()
    conn.close()

    if not row or not row[0]:
        return None

    try:
        return datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def set_exploration_cooldown(user_id):
    conn = get_db()
    cur = conn.cursor()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        INSERT INTO cooldowns (user_id, last_exploration)
        VALUES (?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET last_exploration = excluded.last_exploration
    """, (user_id, now))

    conn.commit()
    conn.close()


# =========================================================
# المخزون والقوة
# =========================================================

def get_inventory(user_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            kamikaze_drones,
            ballistic_missiles,
            cruise_missiles,
            hypersonic_missiles,
            advanced_cruise_missiles,
            f35_jets,
            su35_jets,
            rafale_jets,
            interceptor_missiles
        FROM inventory
        WHERE user_id = ?
    """, (user_id,))

    row = cur.fetchone()
    conn.close()

    keys = [
        "kamikaze_drones",
        "ballistic_missiles",
        "cruise_missiles",
        "hypersonic_missiles",
        "advanced_cruise_missiles",
        "f35_jets",
        "su35_jets",
        "rafale_jets",
        "interceptor_missiles"
    ]

    if not row:
        return {key: 0 for key in keys}

    return dict(zip(keys, row))


def inventory_strength(selection):
    total = 0

    for item, amount in selection.items():
        if item in WEAPONS:
            total += amount * WEAPONS[item]["strength"]

    return total


def calculate_attack_chance(strength, defense):
    """
    نسبة حقيقية من 100:
    - قوة الترسانة الأعلى = نسبة أعلى.
    - دفاع الخصم الأعلى = نسبة أقل.
    - إذا لم يوجد دفاع وكان هناك سلاح واحد على الأقل = 100%.
    - 100% تعني نجاحًا مؤكدًا.
    """
    if strength <= 0:
        return 0.0

    if defense <= 0:
        return 100.0

    return min(
        100.0,
        (strength / (strength + defense)) * 100.0
    )


def selection_text(selection):
    lines = []

    for item, amount in selection.items():
        if amount > 0:
            lines.append(
                f"{WEAPONS[item]['label']}: `{amount}`"
            )

    return "\n".join(lines) if lines else "لا يوجد شيء محدد."


def valid_selection(selection, inventory):
    for item, amount in selection.items():
        column = WEAPONS[item]["column"]

        if amount < 0:
            return False

        if amount > inventory.get(column, 0):
            return False

    return True


def deduct_selection(user_id, selection):
    conn = get_db()
    cur = conn.cursor()

    for item, amount in selection.items():
        if amount <= 0:
            continue

        column = WEAPONS[item]["column"]

        cur.execute(
            f"""
            UPDATE inventory
            SET {column} = {column} - ?
            WHERE user_id = ?
            """,
            (amount, user_id)
        )

    conn.commit()
    conn.close()


# =========================================================
# الدفاع
# =========================================================

def get_defense_strength(target_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            thaad_level,
            s400_level,
            jammer_level,
            vault_level,
            satellite_level
        FROM players
        WHERE user_id = ?
    """, (target_id,))

    row = cur.fetchone()

    if not row:
        conn.close()
        return 0, 0

    thaad, s400, jammer, vault, satellite = row

    cur.execute(
        "SELECT interceptor_missiles FROM inventory WHERE user_id = ?",
        (target_id,)
    )

    interceptor_row = cur.fetchone()
    interceptors = interceptor_row[0] if interceptor_row else 0

    cur.execute("""
        SELECT
            COALESCE(SUM(jets_committed), 0),
            COALESCE(SUM(f35_committed), 0),
            COALESCE(SUM(su35_committed), 0),
            COALESCE(SUM(rafale_committed), 0)
        FROM defense_alliances
        WHERE ally_id = ?
    """, (target_id,))

    support = cur.fetchone() or (0, 0, 0, 0)
    conn.close()

    old_jets, f35, su35, rafale = support

    # توافق مع النظام القديم الذي كان يخزن الطائرات كلها في jets_committed.
    if f35 == 0 and su35 == 0 and rafale == 0 and old_jets > 0:
        su35 = old_jets

    support_strength = (
        f35 * WEAPONS["إف35"]["strength"] +
        su35 * WEAPONS["سوخوي35"]["strength"] +
        rafale * WEAPONS["رافال"]["strength"]
    )

    defense = (
        thaad * DEFENSE_ITEMS["ثاد"]["strength"] +
        s400 * DEFENSE_ITEMS["إس400"]["strength"] +
        jammer * DEFENSE_ITEMS["التشويش"]["strength"] +
        satellite * DEFENSE_ITEMS["الأقمار"]["strength"] +
        interceptors * DEFENSE_ITEMS["صاروخ_اعتراضي"]["strength"] +
        support_strength
    )

    return defense, vault


# =========================================================
# سجل الهجمات - مطلوب للثأر
# =========================================================

def record_attack(
    attacker_id,
    target_id,
    attack_type,
    success,
    stolen_gold
):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO attack_history
        (
            attacker_id,
            target_id,
            attack_type,
            success,
            stolen_gold,
            created_at,
            revenge_used
        )
        VALUES (?, ?, ?, ?, ?, ?, 0)
    """, (
        attacker_id,
        target_id,
        attack_type,
        1 if success else 0,
        stolen_gold,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()


def was_attacked_by(attacker_id, victim_id):
    """
    يتحقق من آخر هجوم فعلي من attacker على victim فقط.
    إذا تم استخدام الثأر لهذا الهجوم من قبل، فلا يمكن تكراره.
    عند حدوث هجوم جديد، يسجل كسجل جديد ويمكن الثأر منه مرة واحدة.
    """
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, revenge_used
        FROM attack_history
        WHERE attacker_id = ?
          AND target_id = ?
        ORDER BY id DESC
        LIMIT 1
    """, (
        attacker_id,
        victim_id
    ))

    row = cur.fetchone()
    conn.close()

    if not row:
        return False

    return int(row[1] or 0) == 0


def consume_revenge(attacker_id, victim_id):
    """
    يستهلك حق الثأر المرتبط بآخر هجوم من attacker على victim.
    يتم الاستهلاك عند تنفيذ الهجوم فعليًا، وليس عند فتح واجهة الثأر.
    """
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE attack_history
        SET revenge_used = 1
        WHERE id = (
            SELECT id
            FROM attack_history
            WHERE attacker_id = ?
              AND target_id = ?
            ORDER BY id DESC
            LIMIT 1
        )
    """, (
        attacker_id,
        victim_id
    ))

    changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return changed


# =========================================================
# حل الهجوم الفردي
# =========================================================

def resolve_attack(
    attacker_id,
    target_id,
    selection,
    attack_type
):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT gold FROM players WHERE user_id = ?",
        (attacker_id,)
    )
    attacker = cur.fetchone()

    cur.execute(
        "SELECT gold FROM players WHERE user_id = ?",
        (target_id,)
    )
    target = cur.fetchone()

    if not attacker or not target:
        conn.close()

        return {
            "ok": False,
            "success": False,
            "private_message": "❌ أحد الطرفين لا يملك قاعدة."
        }

    attacker_gold = attacker[0]
    target_gold = target[0]

    # إعادة التحقق عند تنفيذ الثأر لمنع الضغط على أكثر من جلسة
    # واستخدام نفس آخر هجوم مرتين.
    if attack_type == "ثار" and not was_attacked_by(
        target_id,
        attacker_id
    ):
        conn.close()
        return {
            "ok": False,
            "success": False,
            "private_message": (
                "❌ تم استخدام الثأر لهذا الهجوم بالفعل، "
                "أو لم يعد هناك هجوم جديد للرد عليه."
            )
        }

    # تكلفة تحريك منصات الصواريخ ومؤونة الجنود.
    if attacker_gold < ATTACK_PLATFORM_COST:
        conn.close()

        return {
            "ok": False,
            "success": False,
            "private_message": (
                "❌ لا تملك ذهبًا كافيًا لتنفيذ الهجوم.\n"
                f"💰 تكلفة الهجوم: `{ATTACK_PLATFORM_COST:,}` ذهب."
            )
        }

    strength = inventory_strength(selection)
    defense, vault = get_defense_strength(target_id)

    # النسبة تعتمد مباشرة على قوة الترسانة مقابل دفاع الخصم.
    chance = calculate_attack_chance(
        strength,
        defense
    )

    # خصم تكلفة الهجوم سواء نجح أو فشل.
    cur.execute(
        """
        UPDATE players
        SET gold = gold - ?
        WHERE user_id = ?
        """,
        (
            ATTACK_PLATFORM_COST,
            attacker_id
        )
    )

    # 100% = نجاح مؤكد.
    success = (
        chance >= 100.0
        or random.uniform(0, 100) < chance
    )

    stolen = 0

    if success:
        # الخزنة تقلل الذهب المسروق.
        vault_reduction = min(
            0.10,
            vault * 0.01
        )

        steal_rate = max(
            0.05,
            0.20 - vault_reduction
        )

        stolen = int(target_gold * steal_rate)

        # الثأر يضاعف الذهب المكتسب.
        if attack_type == "ثار":
            stolen *= 2

        cur.execute(
            """
            UPDATE players
            SET gold = max(0, gold - ?)
            WHERE user_id = ?
            """,
            (stolen, target_id)
        )

        cur.execute(
            """
            UPDATE players
            SET gold = gold + ?,
                trophies = trophies + 20
            WHERE user_id = ?
            """,
            (stolen, attacker_id)
        )

        cur.execute(
            """
            UPDATE players
            SET trophies = max(0, trophies - 20)
            WHERE user_id = ?
            """,
            (target_id,)
        )

    else:
        cur.execute(
            """
            UPDATE players
            SET trophies = max(0, trophies - 15)
            WHERE user_id = ?
            """,
            (attacker_id,)
        )

        cur.execute(
            """
            UPDATE players
            SET trophies = trophies + 15
            WHERE user_id = ?
            """,
            (target_id,)
        )

    conn.commit()
    conn.close()

    # إذا كان هذا هجوم ثأر، يستهلك حق الثأر المرتبط بآخر هجوم للخصم.
    # الفشل أو النجاح كلاهما يستهلكان محاولة الثأر.
    if attack_type == "ثار":
        consume_revenge(
            target_id,
            attacker_id
        )

    # تسجيل الهجوم حتى يستطيع الطرف الآخر أخذ الثأر منه لاحقًا.
    record_attack(
        attacker_id,
        target_id,
        attack_type,
        success,
        stolen
    )

    # الدفاع الجوي للحليف ينتهي بعد أول معركة.
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM defense_alliances WHERE ally_id = ?",
        (target_id,)
    )

    conn.commit()
    conn.close()

    update_rank(attacker_id)
    update_rank(target_id)

    if success:
        private_message = (
            "💥 **نجحت العملية!**\n"
            f"🎯 الهدف: <@{target_id}>\n"
            f"💪 قوة الترسانة: `{strength}`\n"
            f"📊 فرصة النجاح: `{chance:.1f}%`\n"
            f"🪙 الذهب المكتسب: `{stolen:,}`\n"
            f"🚀 تكلفة تحريك المنصات والمؤونة: `{ATTACK_PLATFORM_COST:,}` ذهب"
        )

        if attack_type == "ثار":
            private_message += (
                "\n🔥 **تم مضاعفة الذهب بسبب الثأر.**"
            )

    else:
        private_message = (
            "🔴 **فشلت العملية.**\n"
            f"🎯 الهدف: <@{target_id}>\n"
            f"💪 قوة الترسانة: `{strength}`\n"
            f"📊 فرصة النجاح: `{chance:.1f}%`\n"
            f"🚀 تكلفة تحريك المنصات والمؤونة: `{ATTACK_PLATFORM_COST:,}` ذهب\n"
            "🏆 تم خصم 15 كأسًا."
        )

    return {
        "ok": True,
        "success": success,
        "stolen": stolen,
        "private_message": private_message
    }


# =========================================================
# الهجوم المشترك بين الحلفاء
# =========================================================

pending_joint_attacks = {}

# المهلة الكاملة من لحظة كتابة "قصف" حتى اختيار الترسانة والتأكيد.
ATTACK_SETUP_TIMEOUT_SECONDS = 120


def joint_key(channel_id, target_id):
    return (current_guild_id(), channel_id, target_id)


async def expire_attack_session(key):
    """يلغي جلسة القصف تلقائيًا بعد انتهاء المهلة."""
    await asyncio.sleep(ATTACK_SETUP_TIMEOUT_SECONDS)
    lobby = pending_joint_attacks.get(key)
    if lobby:
        created_at = lobby.get("created_at")
        if created_at and (datetime.now() - created_at).total_seconds() >= ATTACK_SETUP_TIMEOUT_SECONDS:
            pending_joint_attacks.pop(key, None)


def attack_session_expired(key):
    lobby = pending_joint_attacks.get(key)
    if not lobby:
        return True

    created_at = lobby.get("created_at")
    if not created_at:
        return False

    expired = (datetime.now() - created_at).total_seconds() >= ATTACK_SETUP_TIMEOUT_SECONDS
    if expired:
        pending_joint_attacks.pop(key, None)
    return expired


def submit_joint_selection(
    channel_id,
    target_id,
    user_id,
    selection
):
    key = joint_key(channel_id, target_id)

    lobby = pending_joint_attacks.get(key)

    if not lobby:
        return False, "انتهت جلسة الهجوم."

    if user_id not in lobby["allowed"]:
        return False, "أنت لست من أطراف هذا الهجوم."

    lobby["selections"][user_id] = dict(selection)

    return True, "تم حفظ الترسانة."


def resolve_joint_attack(
    channel_id,
    target_id
):
    key = joint_key(channel_id, target_id)
    lobby = pending_joint_attacks.get(key)

    if not lobby:
        return None

    participants = list(
        lobby["selections"].keys()
    )

    if len(participants) < 2:
        return None

    total_strength = sum(
        inventory_strength(
            lobby["selections"][uid]
        )
        for uid in participants
    )

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT gold FROM players WHERE user_id = ?",
        (target_id,)
    )

    target_row = cur.fetchone()

    if not target_row:
        conn.close()

        return {
            "success": False,
            "stolen": 0,
            "participants": participants
        }

    target_gold = target_row[0]

    # كل مشارك يدفع 3000 ذهب.
    fee_errors = []

    for uid in participants:
        cur.execute(
            "SELECT gold FROM players WHERE user_id = ?",
            (uid,)
        )
        row = cur.fetchone()
        gold = row[0] if row else 0

        if gold < ATTACK_PLATFORM_COST:
            fee_errors.append(uid)

    if fee_errors:
        conn.close()

        return {
            "ok": False,
            "success": False,
            "stolen": 0,
            "participants": participants,
            "chance": 0,
            "strength": total_strength,
            "error": (
                "أحد المشاركين لا يملك "
                f"`{ATTACK_PLATFORM_COST:,}` ذهب لتكلفة الهجوم."
            )
        }

    defense, vault = get_defense_strength(
        target_id
    )

    # النسبة تعتمد على مجموع ترسانة جميع المشاركين مقابل دفاع الهدف.
    chance = calculate_attack_chance(
        total_strength,
        defense
    )

    # خصم 3000 من كل مشارك سواء نجح الهجوم أو فشل.
    for uid in participants:
        cur.execute(
            """
            UPDATE players
            SET gold = gold - ?
            WHERE user_id = ?
            """,
            (
                ATTACK_PLATFORM_COST,
                uid
            )
        )

    # 100% = نجاح مؤكد.
    success = (
        chance >= 100.0
        or random.uniform(0, 100) < chance
    )

    stolen = 0

    if success:
        vault_reduction = min(
            0.10,
            vault * 0.01
        )

        steal_rate = max(
            0.05,
            0.20 - vault_reduction
        )

        stolen = int(
            target_gold * steal_rate
        )

        cur.execute(
            """
            UPDATE players
            SET gold = max(0, gold - ?)
            WHERE user_id = ?
            """,
            (stolen, target_id)
        )

        share = stolen // len(participants)
        remainder = stolen - (
            share * len(participants)
        )

        for index, uid in enumerate(participants):
            amount = share

            if index == 0:
                amount += remainder

            cur.execute(
                """
                UPDATE players
                SET gold = gold + ?,
                    trophies = trophies + 20
                WHERE user_id = ?
                """,
                (amount, uid)
            )

    else:
        for uid in participants:
            cur.execute(
                """
                UPDATE players
                SET trophies = max(0, trophies - 15)
                WHERE user_id = ?
                """,
                (uid,)
            )

        cur.execute(
            """
            UPDATE players
            SET trophies = trophies + 15
            WHERE user_id = ?
            """,
            (target_id,)
        )

    conn.commit()
    conn.close()

    # كل قائد يدفع فقط الأسلحة التي اختارها.
    for uid in participants:
        deduct_selection(
            uid,
            lobby["selections"][uid]
        )

        set_attack_cooldown(uid)

        record_attack(
            uid,
            target_id,
            "قصف_مشترك",
            success,
            stolen // len(participants)
            if success else 0
        )

        update_rank(uid)

    update_rank(target_id)

    # انتهاء دفاع الحليف بعد المعركة.
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM defense_alliances WHERE ally_id = ?",
        (target_id,)
    )

    conn.commit()
    conn.close()

    del pending_joint_attacks[key]

    return {
        "success": success,
        "stolen": stolen,
        "participants": participants,
        "chance": chance,
        "strength": total_strength,
        "fee": ATTACK_PLATFORM_COST
    }


# =========================================================
# نافذة كمية السلاح
# =========================================================

class QuantityModal(discord.ui.Modal):
    def __init__(self, parent_view, item):
        super().__init__(
            title=f"تحديد كمية - {WEAPONS[item]['label']}"
        )

        self.parent_view = parent_view
        self.item = item

        self.amount_input = discord.ui.TextInput(
            label="الكمية",
            placeholder="اكتب رقمًا مثل 5",
            required=True,
            max_length=6
        )

        self.add_item(self.amount_input)

    async def on_submit(self, interaction):
        set_guild_context(interaction.guild_id)
        try:
            amount = int(
                self.amount_input.value
            )
        except ValueError:
            await interaction.response.send_message(
                "❌ اكتب رقمًا صحيحًا.",
                ephemeral=True
            )
            return

        if amount < 0:
            await interaction.response.send_message(
                "❌ الكمية لا يمكن أن تكون سالبة.",
                ephemeral=True
            )
            return

        available = self.parent_view.inventory.get(
            WEAPONS[self.item]["column"],
            0
        )

        if amount > available:
            await interaction.response.send_message(
                f"❌ لا تملك هذه الكمية.\n"
                f"المتاح: `{available}`.",
                ephemeral=True
            )
            return

        self.parent_view.selection[
            self.item
        ] = amount

        await interaction.response.edit_message(
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )


class ArsenalSelect(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view

        options = []

        for item, data in WEAPONS.items():
            available = parent_view.inventory.get(
                data["column"],
                0
            )

            options.append(
                discord.SelectOption(
                    label=data["label"][:100],
                    description=f"المتاح: {available}",
                    value=item
                )
            )

        super().__init__(
            placeholder="اختر سلاحًا لتحديد كميته...",
            min_values=1,
            max_values=1,
            options=options,
            row=0
        )

    async def callback(self, interaction):
        if interaction.user.id != self.parent_view.user_id:
            await interaction.response.send_message(
                "❌ هذه الواجهة ليست لك.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            QuantityModal(
                self.parent_view,
                self.values[0]
            )
        )


class GuildScopedView(discord.ui.View):
    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "❌ هذا الأمر يعمل داخل السيرفر فقط.",
                ephemeral=True
            )
            return False
        set_guild_context(interaction.guild_id)
        return True


class ArsenalView(GuildScopedView):
    def __init__(
        self,
        user_id,
        target_id,
        attack_type="قصف",
        joint=False,
        channel_id=None
    ):
        super().__init__(timeout=(120 if attack_type == "قصف" else 180))

        self.user_id = user_id
        self.target_id = target_id
        self.attack_type = attack_type
        self.joint = joint
        self.channel_id = channel_id

        self.inventory = get_inventory(
            user_id
        )

        self.selection = {
            item: 0
            for item in WEAPONS
        }

        self.add_item(
            ArsenalSelect(self)
        )

    def build_embed(self):
        title = (
            "⚔️ تجهيز الثأر"
            if self.attack_type == "ثار"
            else "🚀 تجهيز القصف"
        )

        embed = discord.Embed(
            title=title,
            description=(
                f"🎯 الهدف: <@{self.target_id}>\n"
                "🔒 اختيارك لا يظهر للاعب الآخر.\n"
                "حدد كمية كل سلاح ثم اضغط تأكيد."
            ),
            color=discord.Color.red()
        )

        embed.add_field(
            name="🎒 الترسانة المحددة",
            value=selection_text(
                self.selection
            ),
            inline=False
        )

        strength = inventory_strength(self.selection)
        defense, _ = get_defense_strength(self.target_id)
        chance = calculate_attack_chance(
            strength,
            defense
        )

        embed.add_field(
            name="💥 قوة الترسانة",
            value=f"`{strength}`",
            inline=True
        )

        embed.add_field(
            name="📊 نسبة نجاح الهجوم",
            value=f"`{chance:.1f}%` من 100",
            inline=True
        )

        embed.add_field(
            name="🪙 الذهب",
            value=(
                f"`{get_gold(self.user_id):,}`\n"
                f"🚀 تكلفة الهجوم: `{ATTACK_PLATFORM_COST:,}`"
            ),
            inline=True
        )

        return embed

    @discord.ui.button(
        label="🚀 تأكيد الترسانة",
        style=discord.ButtonStyle.danger,
        row=1
    )
    async def confirm(
        self,
        interaction,
        button
    ):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ هذه الواجهة ليست لك.",
                ephemeral=True
            )
            return

        if sum(self.selection.values()) <= 0:
            await interaction.response.send_message(
                "❌ اختر سلاحًا واحدًا على الأقل.",
                ephemeral=True
            )
            return

        # مهلة القصف تُحسب من لحظة كتابة الأمر، وليس من لحظة فتح النافذة الخاصة.
        if self.attack_type == "قصف":
            key = joint_key(self.channel_id, self.target_id)
            if attack_session_expired(key):
                await interaction.response.send_message(
                    "⏰ انتهت مهلة اختيار الترسانة والتأكيد (دقيقتان). تم إلغاء الهجوم.",
                    ephemeral=True
                )
                return

        current_inventory = get_inventory(
            self.user_id
        )

        if not valid_selection(
            self.selection,
            current_inventory
        ):
            await interaction.response.send_message(
                "❌ الكمية لم تعد متوفرة في المخزن.",
                ephemeral=True
            )
            return

        if self.attack_type == "قصف":
            cooldown = get_attack_cooldown(
                self.user_id
            )

            if cooldown:
                remaining = (
                    timedelta(minutes=5)
                    - (datetime.now() - cooldown)
                )

                if remaining.total_seconds() > 0:
                    await interaction.response.send_message(
                        f"⏳ منصاتك في تبريد.\n"
                        f"المتبقي: `{format_remaining(remaining)}`.",
                        ephemeral=True
                    )
                    return

        # تكلفة تحريك المنصات ومؤونة الجنود لكل مشارك.
        if get_gold(self.user_id) < ATTACK_PLATFORM_COST:
            await interaction.response.send_message(
                "❌ لا تملك الذهب الكافي للمشاركة في الهجوم.\n"
                f"💰 تحتاج إلى `{ATTACK_PLATFORM_COST:,}` ذهب.",
                ephemeral=True
            )
            return

        # هجوم مشترك.
        if self.joint:
            ok, msg = submit_joint_selection(
                self.channel_id,
                self.target_id,
                self.user_id,
                self.selection
            )

            if not ok:
                await interaction.response.send_message(
                    f"❌ {msg}",
                    ephemeral=True
                )
                return

            lobby = pending_joint_attacks[
                joint_key(
                    self.channel_id,
                    self.target_id
                )
            ]

            await interaction.response.edit_message(
                content=(
                    "✅ **تم حفظ ترسانتك الخاصة.**\n"
                    "لن يراها اللاعب الآخر.\n"
                    f"👥 الترسانات الجاهزة: "
                    f"`{len(lobby['selections'])}/2`"
                ),
                embed=None,
                view=None
            )

            if len(lobby["selections"]) >= 2:
                result = resolve_joint_attack(
                    self.channel_id,
                    self.target_id
                )

                if result:
                    if not result.get("ok", True):
                        await interaction.channel.send(
                            f"❌ لم يتم تنفيذ الهجوم المشترك: "
                            f"{result.get('error', 'تعذر تنفيذ الهجوم.')}"
                        )
                        return

                    participants = " و ".join(
                        f"<@{uid}>"
                        for uid in result["participants"]
                    )

                    if result["success"]:
                        public = (
                            f"📢 **نجح الهجوم المشترك!**\n"
                            f"🎯 الهدف: <@{self.target_id}>\n"
                            f"👥 المهاجمون: {participants}\n"
                            f"🪙 الذهب المكتسب إجمالًا: `{result['stolen']:,}` ذهب\n"
                            f"🏆 الكؤوس: `+20` لكل مهاجم و `-20` للهدف"
                        )
                    else:
                        public = (
                            f"📢 **فشل الهجوم المشترك.**\n"
                            f"🎯 الهدف: <@{self.target_id}>\n"
                            f"👥 المهاجمون: {participants}\n"
                            f"🏆 الكؤوس: `-15` لكل مهاجم و `+15` للهدف"
                        )

                    await interaction.channel.send(
                        public +
                        f"\n🚀 تكلفة كل مشارك: `{ATTACK_PLATFORM_COST:,}` ذهب."
                    )

            return

        # هجوم فردي / ثأر.
        await interaction.response.defer(
            ephemeral=True
        )

        result = resolve_attack(
            self.user_id,
            self.target_id,
            self.selection,
            self.attack_type
        )

        if result["ok"]:
            deduct_selection(
                self.user_id,
                self.selection
            )

            if self.attack_type == "قصف":
                set_attack_cooldown(
                    self.user_id
                )

        await interaction.edit_original_response(
            embed=discord.Embed(
                title="📋 نتيجة العملية",
                description=result["private_message"],
                color=(
                    discord.Color.green()
                    if result["success"]
                    else discord.Color.red()
                )
            ),
            view=None
        )

        if result["ok"]:
            if result["success"]:
                if self.attack_type == "ثار":
                    public = (
                        f"📢 **نجح الثأر!** {interaction.user.mention} "
                        f"هاجم <@{self.target_id}> بنجاح.\n"
                        f"🪙 الذهب المكتسب: `{result['stolen']:,}` ذهب (من الهدف)\n"
                        f"🏆 الكؤوس: `+20` للمهاجم و `-20` للهدف"
                    )
                else:
                    public = (
                        f"📢 **نجح القصف!** {interaction.user.mention} "
                        f"هاجم <@{self.target_id}> بنجاح.\n"
                        f"🪙 الذهب المكتسب: `{result['stolen']:,}` ذهب (من الهدف)\n"
                        f"🏆 الكؤوس: `+20` للمهاجم و `-20` للهدف"
                    )
            else:
                if self.attack_type == "ثار":
                    public = (
                        f"📢 **فشل الثأر.** {interaction.user.mention} "
                        f"لم ينجح الهجوم على <@{self.target_id}>.\n"
                        f"🏆 الكؤوس: `-15` للمهاجم و `+15` للهدف"
                    )
                else:
                    public = (
                        f"📢 **فشل القصف.** {interaction.user.mention} "
                        f"لم ينجح الهجوم على <@{self.target_id}>.\n"
                        f"🏆 الكؤوس: `-15` للمهاجم و `+15` للهدف"
                    )

            await interaction.channel.send(
                public + (
                    f"\n🚀 تكلفة تحريك المنصات والمؤونة: "
                    f"`{ATTACK_PLATFORM_COST:,}` ذهب."
                )
            )

    @discord.ui.button(
        label="❌ إلغاء",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def cancel(
        self,
        interaction,
        button
    ):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ هذه الواجهة ليست لك.",
                ephemeral=True
            )
            return

        await interaction.response.edit_message(
            content="❌ تم إلغاء تجهيز الترسانة.",
            embed=None,
            view=None
        )


# =========================================================
# بوابة جلسة الهجوم الخاصة
# =========================================================

class AttackGatewayView(GuildScopedView):
    """واجهة عامة لا تكشف الهدف، وتفتح التفاصيل بشكل خاص فقط."""

    def __init__(self, channel_id, creator_id, target_id):
        super().__init__(timeout=ATTACK_SETUP_TIMEOUT_SECONDS)
        self.channel_id = channel_id
        self.creator_id = creator_id
        self.target_id = target_id

    @discord.ui.button(
        label="🔒 فتح جلسة القائد",
        style=discord.ButtonStyle.primary
    )
    async def open_session(self, interaction, button):
        if interaction.user.id != self.creator_id:
            await interaction.response.send_message(
                "❌ هذه جلسة خاصة بقائد الهجوم.",
                ephemeral=True
            )
            return

        key = joint_key(self.channel_id, self.target_id)
        if attack_session_expired(key):
            await interaction.response.send_message(
                "⏰ انتهت مهلة الهجوم (دقيقتان) وتم إلغاء القصف.",
                ephemeral=True
            )
            return

        lobby = pending_joint_attacks.get(key)

        await interaction.response.send_message(
            embed=discord.Embed(
                title=f"⚔️ جلسة هجوم على <@{self.target_id}>",
                description=(
                    f"👤 القائد: <@{self.creator_id}>\n"
                    "🤝 حليف واحد فقط يمكنه الانضمام إذا كان بينكما تحالف.\n"
                    "🔒 هذه الجلسة لا يراها إلا أنت.\n"
                    "اختر ترسانتك أو نفذ الهجوم منفردًا."
                ),
                color=discord.Color.red()
            ),
            view=JointAttackLobbyView(
                self.channel_id,
                self.creator_id,
                self.target_id
            ),
            ephemeral=True
        )

    @discord.ui.button(
        label="🤝 انضمام الحلف",
        style=discord.ButtonStyle.success
    )
    async def join_ally(self, interaction, button):
        if interaction.user.id == self.creator_id:
            await interaction.response.send_message(
                "❌ أنت قائد الهجوم. استخدم زر فتح جلسة القائد.",
                ephemeral=True
            )
            return

        key = joint_key(self.channel_id, self.target_id)
        if attack_session_expired(key):
            await interaction.response.send_message(
                "⏰ انتهت مهلة الهجوم (دقيقتان) وتم إلغاء القصف.",
                ephemeral=True
            )
            return

        lobby = pending_joint_attacks.get(key)

        if not alliance_exists(self.creator_id, interaction.user.id):
            await interaction.response.send_message(
                "❌ لا يوجد تحالف بينك وبين قائد الهجوم.",
                ephemeral=True
            )
            return

        if interaction.user.id not in lobby["allowed"]:
            if len(lobby["allowed"]) >= 2:
                await interaction.response.send_message(
                    "❌ تم تحديد أطراف هذا الهجوم.",
                    ephemeral=True
                )
                return
            lobby["allowed"].append(interaction.user.id)

        if interaction.user.id in lobby["selections"]:
            await interaction.response.send_message(
                "✅ لقد اخترت ترسانتك بالفعل.",
                ephemeral=True
            )
            return

        arsenal_view = ArsenalView(
            interaction.user.id,
            self.target_id,
            "قصف",
            joint=True,
            channel_id=self.channel_id
        )

        await interaction.response.send_message(
            content="🤝 تم انضمامك للهجوم. اختر ترسانتك بشكل خاص:",
            embed=arsenal_view.build_embed(),
            view=arsenal_view,
            ephemeral=True
        )


# =========================================================
# واجهة الهجوم المشترك
# =========================================================

class JointAttackLobbyView(GuildScopedView):
    def __init__(
        self,
        channel_id,
        creator_id,
        target_id
    ):
        super().__init__(timeout=180)

        self.channel_id = channel_id
        self.creator_id = creator_id
        self.target_id = target_id

    @discord.ui.button(
        label="🎯 اختيار ترسانتي",
        style=discord.ButtonStyle.primary
    )
    async def choose(
        self,
        interaction,
        button
    ):
        key = joint_key(
            self.channel_id,
            self.target_id
        )

        if attack_session_expired(key):
            await interaction.response.send_message(
                "⏰ انتهت مهلة الهجوم (دقيقتان) وتم إلغاء القصف.",
                ephemeral=True
            )
            return

        lobby = pending_joint_attacks.get(
            key
        )

        if not lobby:
            await interaction.response.send_message(
                "❌ انتهت جلسة الهجوم.",
                ephemeral=True
            )
            return

        if interaction.user.id not in lobby["allowed"]:
            await interaction.response.send_message(
                "❌ هذا الهجوم مخصص للقائد وحليفه.",
                ephemeral=True
            )
            return

        if interaction.user.id in lobby["selections"]:
            await interaction.response.send_message(
                "✅ لقد اخترت ترسانتك بالفعل.",
                ephemeral=True
            )
            return

        arsenal_view = ArsenalView(
            interaction.user.id,
            self.target_id,
            "قصف",
            joint=True,
            channel_id=self.channel_id
        )

        await interaction.response.send_message(
            embed=arsenal_view.build_embed(),
            view=arsenal_view,
            ephemeral=True
        )

    @discord.ui.button(
        label="🤝 انضمام الحليف",
        style=discord.ButtonStyle.success
    )
    async def join(
        self,
        interaction,
        button
    ):
        key = joint_key(
            self.channel_id,
            self.target_id
        )

        if attack_session_expired(key):
            await interaction.response.send_message(
                "⏰ انتهت مهلة الهجوم (دقيقتان) وتم إلغاء القصف.",
                ephemeral=True
            )
            return

        lobby = pending_joint_attacks.get(
            key
        )

        if not lobby:
            await interaction.response.send_message(
                "❌ انتهت جلسة الهجوم.",
                ephemeral=True
            )
            return

        if interaction.user.id == self.creator_id:
            await interaction.response.send_message(
                "❌ أنت القائد. استخدم زر اختيار ترسانتي.",
                ephemeral=True
            )
            return

        if not alliance_exists(
            self.creator_id,
            interaction.user.id
        ):
            await interaction.response.send_message(
                "❌ لا يوجد تحالف بينك وبين قائد الهجوم.",
                ephemeral=True
            )
            return

        if len(lobby["allowed"]) >= 2:
            await interaction.response.send_message(
                "❌ تم تحديد أطراف هذا الهجوم.",
                ephemeral=True
            )
            return

        lobby["allowed"].append(
            interaction.user.id
        )

        await interaction.response.send_message(
            "🤝 تم انضمامك للهجوم.\n"
            "اضغط **اختيار ترسانتي** ثم حدد أسلحتك.",
            ephemeral=True
        )

    @discord.ui.button(
        label="⚡ تنفيذ منفرد",
        style=discord.ButtonStyle.secondary
    )
    async def solo(
        self,
        interaction,
        button
    ):
        if interaction.user.id != self.creator_id:
            await interaction.response.send_message(
                "❌ القائد فقط يستطيع تنفيذ الهجوم منفردًا.",
                ephemeral=True
            )
            return

        key = joint_key(
            self.channel_id,
            self.target_id
        )

        if attack_session_expired(key):
            await interaction.response.send_message(
                "⏰ انتهت مهلة الهجوم (دقيقتان) وتم إلغاء القصف.",
                ephemeral=True
            )
            return

        lobby = pending_joint_attacks.get(
            key
        )

        if not lobby:
            await interaction.response.send_message(
                "❌ انتهت جلسة الهجوم.",
                ephemeral=True
            )
            return

        if self.creator_id not in lobby["selections"]:
            await interaction.response.send_message(
                "❌ اختر ترسانتك أولًا.",
                ephemeral=True
            )
            return

        selection = lobby["selections"][
            self.creator_id
        ]

        result = resolve_attack(
            self.creator_id,
            self.target_id,
            selection,
            "قصف"
        )

        if result["ok"]:
            deduct_selection(
                self.creator_id,
                selection
            )

            set_attack_cooldown(
                self.creator_id
            )

        pending_joint_attacks.pop(
            key,
            None
        )

        if not result["ok"]:
            await interaction.response.send_message(
                result.get("private_message", "❌ تعذر تنفيذ الهجوم."),
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "✅ تم تنفيذ الهجوم منفردًا.",
            ephemeral=True
        )

        if result["success"]:
            public = (
                f"📢 **نجح القصف!** {interaction.user.mention} "
                f"هاجم <@{self.target_id}> بنجاح.\n"
                f"🪙 الذهب المكتسب: `{result['stolen']:,}` ذهب (من الهدف)\n"
                f"🏆 الكؤوس: `+20` للمهاجم و `-20` للهدف\n"
                f"🚀 تكلفة تحريك المنصات والمؤونة: `{ATTACK_PLATFORM_COST:,}` ذهب."
            )
        else:
            public = (
                f"📢 **فشل القصف.** {interaction.user.mention} "
                f"لم ينجح الهجوم على <@{self.target_id}>.\n"
                f"🪙 الذهب المكتسب: `0` ذهب\n"
                f"🏆 الكؤوس: `-15` للمهاجم و `+15` للهدف\n"
                f"🚀 تكلفة تحريك المنصات والمؤونة: `{ATTACK_PLATFORM_COST:,}` ذهب."
            )

        await interaction.channel.send(public)


# =========================================================
# التحالف
# =========================================================

class AcceptAllianceView(GuildScopedView):
    def __init__(
        self,
        inviter_id,
        ally_id
    ):
        super().__init__(timeout=120)

        self.inviter_id = inviter_id
        self.ally_id = ally_id

    @discord.ui.button(
        label="🤝 قبول التحالف",
        style=discord.ButtonStyle.success
    )
    async def accept(
        self,
        interaction,
        button
    ):
        if interaction.user.id != self.ally_id:
            await interaction.response.send_message(
                "❌ هذا الطلب ليس لك.",
                ephemeral=True
            )
            return

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            "SELECT gold FROM players WHERE user_id = ?",
            (self.inviter_id,)
        )
        p1 = cur.fetchone()

        cur.execute(
            "SELECT gold FROM players WHERE user_id = ?",
            (self.ally_id,)
        )
        p2 = cur.fetchone()

        if not p1 or not p2:
            conn.close()

            await interaction.response.send_message(
                "❌ يجب أن تكون القاعدتان موجودتين.",
                ephemeral=True
            )
            return

        if p1[0] < 100000 or p2[0] < 100000:
            conn.close()

            await interaction.response.send_message(
                "❌ يجب أن يملك كل طرف 100,000 ذهب.",
                ephemeral=True
            )
            return

        cur.execute(
            """
            INSERT OR REPLACE INTO active_alliances
            (user_id, ally_id, status)
            VALUES (?, ?, 'active')
            """,
            (
                self.inviter_id,
                self.ally_id
            )
        )

        cur.execute(
            """
            INSERT OR REPLACE INTO active_alliances
            (user_id, ally_id, status)
            VALUES (?, ?, 'active')
            """,
            (
                self.ally_id,
                self.inviter_id
            )
        )

        cur.execute(
            """
            UPDATE players
            SET gold = gold - 100000
            WHERE user_id IN (?, ?)
            """,
            (
                self.inviter_id,
                self.ally_id
            )
        )

        conn.commit()
        conn.close()

        await interaction.response.edit_message(
            content=(
                f"🤝 **تم إنشاء التحالف بين "
                f"<@{self.inviter_id}> "
                f"و {interaction.user.mention}.**"
            ),
            view=None
        )

    @discord.ui.button(
        label="❌ رفض",
        style=discord.ButtonStyle.danger
    )
    async def deny(
        self,
        interaction,
        button
    ):
        if interaction.user.id != self.ally_id:
            await interaction.response.send_message(
                "❌ هذا الطلب ليس لك.",
                ephemeral=True
            )
            return

        await interaction.response.edit_message(
            content="❌ تم رفض طلب التحالف.",
            view=None
        )


# =========================================================
# الدفاع الجوي للحليف
# =========================================================

class DefenseModal(discord.ui.Modal):
    def __init__(
        self,
        user_id,
        ally_id
    ):
        super().__init__(
            title="🛡️ تحديد الدفاع الجوي"
        )

        self.user_id = user_id
        self.ally_id = ally_id

        self.f35 = discord.ui.TextInput(
            label="عدد إف-35",
            placeholder="0",
            required=True,
            default="0",
            max_length=5
        )

        self.su35 = discord.ui.TextInput(
            label="عدد سوخوي-35",
            placeholder="0",
            required=True,
            default="0",
            max_length=5
        )

        self.rafale = discord.ui.TextInput(
            label="عدد رافال",
            placeholder="0",
            required=True,
            default="0",
            max_length=5
        )

        self.add_item(self.f35)
        self.add_item(self.su35)
        self.add_item(self.rafale)

    async def on_submit(
        self,
        interaction
    ):
        set_guild_context(interaction.guild_id)
        try:
            f35 = int(self.f35.value)
            su35 = int(self.su35.value)
            rafale = int(self.rafale.value)
        except ValueError:
            await interaction.response.send_message(
                "❌ اكتب أرقامًا صحيحة.",
                ephemeral=True
            )
            return

        if min(
            f35,
            su35,
            rafale
        ) < 0:
            await interaction.response.send_message(
                "❌ لا يمكن استخدام أرقام سالبة.",
                ephemeral=True
            )
            return

        inv = get_inventory(
            self.user_id
        )

        if (
            f35 > inv["f35_jets"]
            or su35 > inv["su35_jets"]
            or rafale > inv["rafale_jets"]
        ):
            await interaction.response.send_message(
                "❌ الكمية غير متوفرة.\n"
                f"إف-35 المتاح: `{inv['f35_jets']}`\n"
                f"سوخوي-35 المتاح: `{inv['su35_jets']}`\n"
                f"رافال المتاح: `{inv['rafale_jets']}`",
                ephemeral=True
            )
            return

        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            INSERT OR REPLACE INTO defense_alliances
            (
                user_id,
                ally_id,
                jets_committed,
                f35_committed,
                su35_committed,
                rafale_committed
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            self.user_id,
            self.ally_id,
            f35 + su35 + rafale,
            f35,
            su35,
            rafale
        ))

        cur.execute("""
            UPDATE inventory
            SET
                f35_jets = f35_jets - ?,
                su35_jets = su35_jets - ?,
                rafale_jets = rafale_jets - ?
            WHERE user_id = ?
        """, (
            f35,
            su35,
            rafale,
            self.user_id
        ))

        conn.commit()
        conn.close()

        await interaction.response.send_message(
            f"✅ تم تخصيص الدفاع لـ <@{self.ally_id}>.\n"
            f"✈️ إف-35: `{f35}`\n"
            f"🛩️ سوخوي-35: `{su35}`\n"
            f"🇫🇷 رافال: `{rafale}`",
            ephemeral=True
        )


class DefenseButtonView(GuildScopedView):
    def __init__(
        self,
        owner_id,
        ally_id
    ):
        super().__init__(timeout=120)

        self.owner_id = owner_id
        self.ally_id = ally_id

    @discord.ui.button(
        label="🛡️ اختيار الطائرات",
        style=discord.ButtonStyle.primary
    )
    async def choose(
        self,
        interaction,
        button
    ):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "❌ هذا الزر ليس لك.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            DefenseModal(
                self.owner_id,
                self.ally_id
            )
        )


# =========================================================
# القاعدة الخاصة
# =========================================================

def build_base_embed(user_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            gold,
            trophies,
            rank_title,
            thaad_level,
            s400_level,
            jammer_level,
            vault_level,
            satellite_level
        FROM players
        WHERE user_id = ?
    """, (user_id,))

    p = cur.fetchone()

    cur.execute("""
        SELECT
            kamikaze_drones,
            ballistic_missiles,
            cruise_missiles,
            hypersonic_missiles,
            advanced_cruise_missiles,
            f35_jets,
            su35_jets,
            rafale_jets,
            interceptor_missiles
        FROM inventory
        WHERE user_id = ?
    """, (user_id,))

    i = cur.fetchone()

    conn.close()

    if not p or not i:
        return discord.Embed(
            title="❌ لا توجد قاعدة",
            description="اكتب `ابدا` أولًا."
        )

    (
        gold,
        trophies,
        rank,
        thaad,
        s400,
        jammer,
        vault,
        satellite
    ) = p

    (
        drones,
        ballistic,
        cruise,
        hyper,
        advanced,
        f35,
        su35,
        rafale,
        interceptor
    ) = i

    embed = discord.Embed(
        title="🏰 قاعدتك العسكرية - خاصة",
        color=discord.Color.dark_blue()
    )

    embed.add_field(
        name="💰 الحساب",
        value=(
            f"🪙 الذهب: `{gold:,}`\n"
            f"🏆 الكؤوس: `{trophies:,}`\n"
            f"🎖️ الرتبة: `{rank}`"
        ),
        inline=False
    )

    embed.add_field(
        name="🛡️ الدفاع",
        value=(
            f"📡 ثاد: `{thaad}`\n"
            f"🛡️ إس-400: `{s400}`\n"
            f"📻 التشويش: `{jammer}`\n"
            f"🔐 الخزنة: `{vault}`\n"
            f"🛰️ الأقمار: `{satellite}`\n"
            f"🧨 اعتراضي: `{interceptor}`"
        ),
        inline=True
    )

    embed.add_field(
        name="🎒 الهجوم",
        value=(
            f"🛸 مسيرات: `{drones}`\n"
            f"🚀 باليستي: `{ballistic}`\n"
            f"🏹 كروز: `{cruise}`\n"
            f"⚡ فرط صوتي: `{hyper}`\n"
            f"🎯 كروز متقدم: `{advanced}`"
        ),
        inline=True
    )

    embed.add_field(
        name="✈️ الطائرات",
        value=(
            f"إف-35: `{f35}`\n"
            f"سوخوي-35: `{su35}`\n"
            f"رافال: `{rafale}`"
        ),
        inline=False
    )

    return embed


class BasePrivateView(GuildScopedView):
    def __init__(self, user_id):
        super().__init__(timeout=120)

        self.user_id = user_id

    @discord.ui.button(
        label="🔒 عرض قاعدتي بشكل خاص",
        style=discord.ButtonStyle.primary
    )
    async def show(
        self,
        interaction,
        button
    ):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ هذا الزر ليس لك.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            embed=build_base_embed(
                self.user_id
            ),
            ephemeral=True
        )


# =========================================================
# الاستكشاف
# =========================================================

EXPLORATION_MIN_GOLD = 6000
EXPLORATION_SUCCESS_CHANCE = 0.60
EXPLORATION_PROFIT_RATE = 0.40
EXPLORATION_COOLDOWN_SECONDS = 90


class ExplorationModal(discord.ui.Modal):
    def __init__(self, user_id):
        super().__init__(title="🧭 تحديد ميزانية الاستكشاف")
        self.user_id = user_id

        self.amount_input = discord.ui.TextInput(
            label="كمية الذهب",
            placeholder="أقل مبلغ: 6000",
            required=True,
            min_length=4,
            max_length=12
        )
        self.add_item(self.amount_input)

    async def on_submit(self, interaction):
        set_guild_context(interaction.guild_id)

        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ هذه الواجهة ليست لك.",
                ephemeral=True
            )
            return

        last_exploration = get_exploration_cooldown(self.user_id)
        if last_exploration is not None:
            elapsed = (datetime.now() - last_exploration).total_seconds()
            remaining = int(EXPLORATION_COOLDOWN_SECONDS - elapsed)
            if remaining > 0:
                minutes = remaining // 60
                seconds = remaining % 60
                await interaction.response.send_message(
                    "⏳ لا يمكنك تنفيذ استكشاف جديد الآن.\n"
                    f"🧭 حاول بعد **{minutes} دقيقة و {seconds} ثانية**.",
                    ephemeral=True
                )
                return

        amount = parse_amount(
            str(self.amount_input.value).replace(",", "").replace("٬", "")
        )

        if amount is None or amount < EXPLORATION_MIN_GOLD:
            await interaction.response.send_message(
                f"❌ أقل كمية للاستكشاف هي `{EXPLORATION_MIN_GOLD:,}` ذهب.",
                ephemeral=True
            )
            return

        current_gold = get_gold(self.user_id)

        if current_gold < amount:
            await interaction.response.send_message(
                f"❌ لا تملك ذهبًا كافيًا.\n"
                f"🪙 المطلوب: `{amount:,}`\n"
                f"💰 رصيدك: `{current_gold:,}`",
                ephemeral=True
            )
            return

        # يتم سحب المبلغ أولًا، ثم تحديد النتيجة.
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "UPDATE players SET gold = gold - ? WHERE user_id = ?",
            (amount, self.user_id)
        )
        conn.commit()
        conn.close()

        set_exploration_cooldown(self.user_id)

        success = random.random() < EXPLORATION_SUCCESS_CHANCE

        if success:
            profit = int(amount * EXPLORATION_PROFIT_RATE)
            returned = amount + profit

            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "UPDATE players SET gold = gold + ? WHERE user_id = ?",
                (returned, self.user_id)
            )
            conn.commit()
            conn.close()

            new_balance = get_gold(self.user_id)

            embed = discord.Embed(
                title="🧭 نجحت رحلة الاستكشاف!",
                description=(
                    f"🎉 عثرت على موارد ثمينة أثناء الاستكشاف.\n\n"
                    f"💰 المبلغ المستكشف: `{amount:,}` ذهب\n"
                    f"📈 الربح: `+{profit:,}` ذهب (40%)\n"
                    f"🪙 المبلغ العائد: `{returned:,}` ذهب\n"
                    f"💳 رصيدك الجديد: `{new_balance:,}` ذهب"
                ),
                color=discord.Color.green()
            )
            embed.set_footer(text="نسبة النجاح 60% • نسبة الخسارة 40%")
        else:
            new_balance = get_gold(self.user_id)

            embed = discord.Embed(
                title="💥 فشل الاستكشاف",
                description=(
                    f"❌ لم تجد الموارد المطلوبة وخسرت كامل المبلغ المحدد.\n\n"
                    f"💸 المبلغ المفقود: `{amount:,}` ذهب\n"
                    f"💳 رصيدك الجديد: `{new_balance:,}` ذهب"
                ),
                color=discord.Color.red()
            )
            embed.set_footer(text="نسبة النجاح 60% • نسبة الخسارة 40%")
        progress_daily_task(self.user_id, "exploration")

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )


class ExplorationView(GuildScopedView):
    def __init__(self, user_id):
        super().__init__(timeout=120)
        self.user_id = user_id

    @discord.ui.button(
        label="🧭 اختيار كمية الذهب",
        style=discord.ButtonStyle.success
    )
    async def choose_amount(self, interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ هذا الزر ليس لك.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            ExplorationModal(self.user_id)
        )


class GoldBalanceView(GuildScopedView):
    def __init__(self, user_id):
        super().__init__(timeout=180)
        self.user_id = user_id

    @discord.ui.button(
        label="🪙 عرض رصيدي",
        style=discord.ButtonStyle.primary
    )
    async def show_balance(self, interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ هذا الزر ليس لك.",
                ephemeral=True
            )
            return

        gold = get_gold(interaction.user.id)

        embed = discord.Embed(
            title="🪙 رصيدك من الذهب",
            description=f"💰 **تملك:** `{gold:,}` ذهب",
            color=discord.Color.gold()
        )
        embed.set_footer(text="هذه الرسالة خاصة بك فقط")

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )


# =========================================================
# الصناديق العشوائية
# =========================================================

def choose_chest_reward(chest_type):
    chest = CHESTS[chest_type]
    roll = random.uniform(0, 100)
    current = 0

    for reward in chest["rewards"]:
        current += reward[1]
        if roll <= current:
            return reward

    return chest["rewards"][-1]


def grant_chest_reward(user_id, reward):
    reward_type = reward[0]
    conn = get_db()
    cur = conn.cursor()

    if reward_type == "gold":
        amount = random.randint(reward[2], reward[3])
        cur.execute(
            "UPDATE players SET gold = gold + ? WHERE user_id = ?",
            (amount, user_id)
        )
        reward_text = f"{reward[4]} **{amount:,} ذهب**"

    elif reward_type == "weapon":
        item = reward[2]
        amount = reward[3]
        data = ALL_SHOP_ITEMS.get(item)
        if not data:
            conn.close()
            return None

        cur.execute(
            f"UPDATE inventory SET {data['column']} = {data['column']} + ? WHERE user_id = ?",
            (amount, user_id)
        )
        reward_text = f"{reward[4]} **{CHEST_NAMES.get(item, data['label'])} × {amount}**"

    else:
        conn.close()
        return None

    conn.commit()
    conn.close()
    return reward_text


class ChestOpenView(GuildScopedView):
    def __init__(self, user_id, chest_type):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.chest_type = chest_type
        self.opened = False

    @discord.ui.button(label="🔓 فتح الصندوق", style=discord.ButtonStyle.success)
    async def open_chest(self, interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ هذا الصندوق ليس لك.",
                ephemeral=True
            )
            return

        if self.opened:
            await interaction.response.send_message(
                "❌ تم استخدام هذا الصندوق بالفعل.",
                ephemeral=True
            )
            return

        self.opened = True
        chest = CHESTS[self.chest_type]
        set_guild_context(interaction.guild_id)
        gold = get_gold(self.user_id)

        if gold < chest["price"]:
            self.opened = False
            await interaction.response.send_message(
                f"❌ لا تملك الذهب الكافي.\n"
                f"💰 سعر الصندوق: `{chest['price']:,}` ذهب\n"
                f"🪙 رصيدك: `{gold:,}` ذهب",
                ephemeral=True
            )
            return

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "UPDATE players SET gold = gold - ? WHERE user_id = ?",
            (chest["price"], self.user_id)
        )
        conn.commit()
        conn.close()

        reward = choose_chest_reward(self.chest_type)
        reward_text = grant_chest_reward(self.user_id, reward)

        if reward_text is None:
            # استرجاع السعر إذا حصل خطأ غير متوقع في المكافأة.
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "UPDATE players SET gold = gold + ? WHERE user_id = ?",
                (chest["price"], self.user_id)
            )
            conn.commit()
            conn.close()
            self.opened = False
            await interaction.response.send_message(
                "❌ حدث خطأ أثناء فتح الصندوق، وتم إرجاع الذهب.",
                ephemeral=True
            )
            return

        new_balance = get_gold(self.user_id)

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO chest_history (user_id, chest_type, reward_text, created_at) VALUES (?, ?, ?, ?)",
            (
                self.user_id,
                self.chest_type,
                reward_text,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        )
        conn.commit()
        conn.close()

        progress_daily_task(self.user_id, "chest")

        embed = discord.Embed(
            title="🎉 تم فتح الصندوق!",
            description=(
                f"📦 **{chest['label']}**\n\n"
                f"🎁 **المكافأة:**\n{reward_text}\n\n"
                f"💸 تكلفة الصندوق: `{chest['price']:,}` ذهب\n"
                f"💳 رصيدك الجديد: `{new_balance:,}` ذهب"
            ),
            color=chest["color"]
        )
        embed.set_footer(text="هذه النتيجة خاصة بك فقط")

        button.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(embed=embed, ephemeral=True)


class ChestShopView(GuildScopedView):
    def __init__(self, user_id):
        super().__init__(timeout=180)
        self.user_id = user_id

    async def send_chest(self, interaction, chest_type):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ هذه القائمة ليست لك.",
                ephemeral=True
            )
            return

        set_guild_context(interaction.guild_id)
        chest = CHESTS[chest_type]
        gold = get_gold(self.user_id)

        if gold < chest["price"]:
            await interaction.response.send_message(
                f"❌ لا تملك الذهب الكافي. تحتاج `{chest['price']:,}` ذهب.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"📦 {chest['label']}",
            description=(
                "🎁 **الصندوق جاهز للفتح!**\n\n"
                f"💰 السعر: `{chest['price']:,}` ذهب\n"
                f"🪙 رصيدك الحالي: `{gold:,}` ذهب\n\n"
                "اضغط **فتح الصندوق** لشراء الصندوق واستلام مكافأتك العشوائية."
            ),
            color=chest["color"]
        )
        embed.set_footer(text="المكافأة عشوائية ولا يمكن معرفة محتواها مسبقًا")

        await interaction.response.send_message(
            embed=embed,
            view=ChestOpenView(self.user_id, chest_type),
            ephemeral=True
        )

    @discord.ui.button(label="🟫 عادي • 5,000", style=discord.ButtonStyle.secondary, row=0)
    async def normal(self, interaction, button):
        await self.send_chest(interaction, "عادي")

    @discord.ui.button(label="🟦 نادر • 15,000", style=discord.ButtonStyle.primary, row=0)
    async def rare(self, interaction, button):
        await self.send_chest(interaction, "نادر")

    @discord.ui.button(label="🟪 أسطوري • 50,000", style=discord.ButtonStyle.danger, row=0)
    async def legendary(self, interaction, button):
        await self.send_chest(interaction, "أسطوري")


class ChestHistoryView(GuildScopedView):
    def __init__(self, user_id):
        super().__init__(timeout=60)
        self.user_id = user_id

    @discord.ui.button(label="📜 عرض آخر الصناديق", style=discord.ButtonStyle.secondary)
    async def history(self, interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ هذا الزر ليس لك.",
                ephemeral=True
            )
            return

        set_guild_context(interaction.guild_id)
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT chest_type, reward_text, created_at FROM chest_history WHERE user_id = ? ORDER BY id DESC LIMIT 10",
            (self.user_id,)
        )
        rows = cur.fetchall()
        conn.close()

        if not rows:
            text = "لا يوجد لديك سجل صناديق حتى الآن."
        else:
            lines = []
            for chest_type, reward_text, created_at in rows:
                lines.append(
                    f"📦 **{CHESTS[chest_type]['label']}** — {reward_text}\n🕒 `{created_at}`"
                )
            text = "\n\n".join(lines)

        embed = discord.Embed(
            title="📜 سجل الصناديق",
            description=text,
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)



# =========================================================
# الأحداث العشوائية
# =========================================================

RANDOM_EVENTS = [
    {
        "title": "⛏️ اكتشاف منجم ذهب",
        "description": "تم اكتشاف منجم ذهب نادر بالقرب من قواعد اللاعبين! أول لاعب يصل إليه يحصل على كمية كبيرة من الذهب.",
        "type": "gold",
        "min": 8000,
        "max": 20000,
        "button": "⛏️ استخرج الذهب"
    },
    {
        "title": "📦 سقوط إمدادات جوية",
        "description": "سقطت شحنة عسكرية مجهولة في المنطقة! أول لاعب يصل إليها يحصل على سلاح عشوائي.",
        "type": "weapon",
        "button": "📦 استلام الإمدادات"
    },
    {
        "title": "🚚 قافلة تجارية",
        "description": "ظهرت قافلة تجارية محملة بالذهب. أول لاعب يعثر عليها يحصل على مكافأة مالية كبيرة.",
        "type": "gold",
        "min": 12000,
        "max": 30000,
        "button": "🚚 اعتراض القافلة"
    },
    {
        "title": "🛰️ صندوق معلومات عسكري",
        "description": "تم العثور على صندوق يحتوي على معلومات عسكرية سرية. أول لاعب يفتحه يحصل على مكافأة.",
        "type": "gold",
        "min": 6000,
        "max": 16000,
        "button": "🛰️ الحصول على المعلومات"
    }
]

class RandomEventView(GuildScopedView):
    def __init__(self, event_data):
        super().__init__(timeout=300)
        self.event_data = event_data
        self.claimed = False
        self.message = None

    async def disable_buttons(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

    @discord.ui.button(label="🎁 استلام الحدث", style=discord.ButtonStyle.success)
    async def claim_event(self, interaction, button):
        set_guild_context(interaction.guild_id)

        if self.claimed:
            await interaction.response.send_message(
                "❌ انتهى الحدث، فقد حصل عليه لاعب آخر.",
                ephemeral=True
            )
            return

        if not has_base(interaction.user.id):
            await interaction.response.send_message(
                "❌ يجب أن تكتب `ابدا` أولًا حتى تتمكن من المشاركة في الأحداث.",
                ephemeral=True
            )
            return

        # أول لاعب يصل هنا يفوز بالحدث.
        self.claimed = True
        button.disabled = True

        event = self.event_data
        reward_text = None

        if event["type"] == "gold":
            amount = random.randint(event["min"], event["max"])
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "UPDATE players SET gold = gold + ? WHERE user_id = ?",
                (amount, interaction.user.id)
            )
            conn.commit()
            conn.close()
            reward_text = f"🪙 **{amount:,} ذهب**"

        elif event["type"] == "weapon":
            possible = [
                ("مسيرة_انتحارية", 3, "🛸"),
                ("صاروخ_باليستي", 1, "🚀"),
                ("صاروخ_كروز", 1, "🏹"),
                ("إف35", 1, "✈️"),
            ]
            item, amount, emoji = random.choice(possible)
            data = ALL_SHOP_ITEMS.get(item)

            if not data:
                self.claimed = False
                button.disabled = False
                await interaction.response.send_message(
                    "❌ حدث خطأ أثناء توزيع المكافأة.",
                    ephemeral=True
                )
                return

            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                f"UPDATE inventory SET {data['column']} = {data['column']} + ? WHERE user_id = ?",
                (amount, interaction.user.id)
            )
            conn.commit()
            conn.close()
            reward_text = f"{emoji} **{data['label']} × {amount}**"

        embed = discord.Embed(
            title="🏆 تم حسم الحدث!",
            description=(
                f"🎉 الفائز: {interaction.user.mention}\n\n"
                f"🎁 المكافأة: {reward_text}\n\n"
                "انتهى هذا الحدث ولن يستطيع لاعب آخر الحصول على المكافأة."
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text="Sky Strike • الأحداث العشوائية")

        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        if not self.claimed:
            self.claimed = True
            await self.disable_buttons()


async def create_random_event():
    """ينشئ حدثًا عشوائيًا في أول قناة مسموحة يمكن للبوت الكتابة فيها."""
    event = random.choice(RANDOM_EVENTS)

    for guild in bot.guilds:
        set_guild_context(guild.id)

        channel = None
        for channel_id in ALLOWED_CHANNELS:
            candidate = guild.get_channel(channel_id)
            if candidate is not None and hasattr(candidate, "send"):
                permissions = candidate.permissions_for(guild.me)
                if permissions.view_channel and permissions.send_messages:
                    channel = candidate
                    break

        if channel is None:
            continue

        view = RandomEventView(event)
        embed = discord.Embed(
            title=f"🎲 حدث عشوائي: {event['title']}",
            description=(
                f"{event['description']}\n\n"
                "⚡ **القانون:** أول لاعب يضغط الزر ويحصل على المكافأة يفوز.\n"
                "⏳ مدة الحدث: **5 دقائق**.\n\n"
                f"اضغط الزر: **{event['button']}**"
            ),
            color=discord.Color.orange()
        )
        embed.set_footer(text="Sky Strike • حدث عشوائي")

        try:
            message = await channel.send(embed=embed, view=view)
            view.message = message
        except (discord.Forbidden, discord.HTTPException):
            continue


@tasks.loop(minutes=15)
async def random_event_loop():
    await create_random_event()


# =========================================================
# السوق بين اللاعبين
# =========================================================

def market_item_label(item_name):
    return WEAPONS.get(item_name, {}).get("label", item_name)


def get_active_market_listings(limit=20, seller_id=None):
    conn = get_db()
    cur = conn.cursor()

    if seller_id is None:
        cur.execute(
            """
            SELECT id, seller_id, item_name, amount, price, created_at
            FROM market_listings
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,)
        )
    else:
        cur.execute(
            """
            SELECT id, seller_id, item_name, amount, price, created_at
            FROM market_listings
            WHERE seller_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (seller_id, limit)
        )

    rows = cur.fetchall()
    conn.close()
    return rows


def create_market_listing(seller_id, item_name, amount, price):
    """يحجز الأسلحة أولًا ثم ينشئ العرض، حتى لا يستطيع البائع بيع نفس الأسلحة مرتين."""
    if item_name not in WEAPONS or amount <= 0 or price <= 0:
        return False, "بيانات العرض غير صحيحة."

    register_user(seller_id)
    data = WEAPONS[item_name]
    column = data["column"]

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        f"SELECT {column} FROM inventory WHERE user_id = ?",
        (seller_id,)
    )
    row = cur.fetchone()
    owned = row[0] if row else 0

    if owned < amount:
        conn.close()
        return False, f"لا تملك كمية كافية. لديك `{owned}` فقط."

    cur.execute(
        f"UPDATE inventory SET {column} = {column} - ? WHERE user_id = ? AND {column} >= ?",
        (amount, seller_id, amount)
    )

    if cur.rowcount != 1:
        conn.rollback()
        conn.close()
        return False, "تعذر حجز الكمية، حاول مرة أخرى."

    cur.execute(
        """
        INSERT INTO market_listings
        (seller_id, item_name, amount, price, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            seller_id,
            item_name,
            amount,
            price,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    )

    conn.commit()
    listing_id = cur.lastrowid
    conn.close()
    return True, listing_id


def buy_market_listing(buyer_id, listing_id):
    """شراء العرض في عملية واحدة: الذهب ينتقل للبائع والسلاح للمشتري."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT seller_id, item_name, amount, price FROM market_listings WHERE id = ?",
        (listing_id,)
    )
    row = cur.fetchone()

    if not row:
        conn.close()
        return False, "هذا العرض لم يعد موجودًا."

    seller_id, item_name, amount, price = row

    if buyer_id == seller_id:
        conn.close()
        return False, "لا يمكنك شراء عرضك الخاص."

    if item_name not in WEAPONS:
        conn.close()
        return False, "العنصر الموجود في العرض غير صالح."

    cur.execute("SELECT gold FROM players WHERE user_id = ?", (buyer_id,))
    buyer_row = cur.fetchone()
    buyer_gold = buyer_row[0] if buyer_row else 0

    if buyer_gold < price:
        conn.close()
        return False, f"لا تملك الذهب الكافي. تحتاج `{price:,}` ذهب."

    column = WEAPONS[item_name]["column"]

    cur.execute(
        "UPDATE players SET gold = gold - ? WHERE user_id = ? AND gold >= ?",
        (price, buyer_id, price)
    )
    if cur.rowcount != 1:
        conn.rollback()
        conn.close()
        return False, "تعذر خصم الذهب، حاول مرة أخرى."

    cur.execute(
        "UPDATE players SET gold = gold + ? WHERE user_id = ?",
        (price, seller_id)
    )

    # في حالة كان المشتري جديدًا على جدول inventory، register_user يضمن وجوده.
    cur.execute(
        f"UPDATE inventory SET {column} = {column} + ? WHERE user_id = ?",
        (amount, buyer_id)
    )

    cur.execute("DELETE FROM market_listings WHERE id = ?", (listing_id,))
    if cur.rowcount != 1:
        conn.rollback()
        conn.close()
        return False, "تعذر إتمام شراء العرض."

    conn.commit()
    conn.close()

    progress_daily_task(buyer_id, "market_buy")
    return True, {
        "seller_id": seller_id,
        "item_name": item_name,
        "amount": amount,
        "price": price
    }


def cancel_market_listing(seller_id, listing_id):
    """إلغاء عرض وإرجاع الأسلحة المحجوزة للبائع."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT item_name, amount FROM market_listings WHERE id = ? AND seller_id = ?",
        (listing_id, seller_id)
    )
    row = cur.fetchone()

    if not row:
        conn.close()
        return False, "العرض غير موجود أو ليس تابعًا لك."

    item_name, amount = row
    if item_name not in WEAPONS:
        conn.close()
        return False, "العنصر الموجود في العرض غير صالح."

    column = WEAPONS[item_name]["column"]
    cur.execute(
        f"UPDATE inventory SET {column} = {column} + ? WHERE user_id = ?",
        (amount, seller_id)
    )
    cur.execute("DELETE FROM market_listings WHERE id = ?", (listing_id,))

    conn.commit()
    conn.close()
    return True, (item_name, amount)


def market_listings_text(rows, message_guild=None):
    if not rows:
        return "لا توجد عروض للبيع حاليًا."

    lines = []
    for listing_id, seller_id, item_name, amount, price, created_at in rows:
        member = message_guild.get_member(seller_id) if message_guild else None
        seller_name = member.display_name if member else f"لاعب {seller_id}"
        lines.append(
            f"**#{listing_id}** — {market_item_label(item_name)} × `{amount:,}`\n"
            f"👤 البائع: **{seller_name}**\n"
            f"💰 السعر الإجمالي: `{price:,}` ذهب"
        )
    return "\n\n".join(lines)


class MarketPurchaseView(GuildScopedView):
    def __init__(self, user_id, listing_id):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.listing_id = listing_id
        self.done = False

    @discord.ui.button(label="🛒 شراء العرض", style=discord.ButtonStyle.success)
    async def purchase(self, interaction, button):
        set_guild_context(interaction.guild_id)

        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ هذا العرض ليس لك. افتح السوق من حسابك.",
                ephemeral=True
            )
            return

        if self.done:
            await interaction.response.send_message(
                "❌ تم استخدام هذا العرض بالفعل.",
                ephemeral=True
            )
            return

        if not has_base(interaction.user.id):
            await interaction.response.send_message(
                "❌ يجب أن تكتب `ابدا` أولًا.",
                ephemeral=True
            )
            return

        self.done = True
        ok, result = buy_market_listing(interaction.user.id, self.listing_id)

        if not ok:
            self.done = False
            await interaction.response.send_message(
                f"❌ {result}",
                ephemeral=True
            )
            return

        item_name = result["item_name"]
        amount = result["amount"]
        price = result["price"]
        new_balance = get_gold(interaction.user.id)

        button.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            f"✅ **تم الشراء بنجاح!**\n\n"
            f"📦 {market_item_label(item_name)} × `{amount:,}`\n"
            f"💰 السعر: `{price:,}` ذهب\n"
            f"🪙 رصيدك الجديد: `{new_balance:,}` ذهب",
            ephemeral=True
        )


class MarketSelect(discord.ui.Select):
    def __init__(self, user_id, rows):
        self.user_id = user_id
        options = []

        for listing_id, seller_id, item_name, amount, price, created_at in rows:
            options.append(
                discord.SelectOption(
                    label=f"#{listing_id} {market_item_label(item_name)} × {amount}",
                    description=f"السعر: {price:,} ذهب"[:100],
                    value=str(listing_id)
                )
            )

        super().__init__(
            placeholder="🛒 اختر عرضًا لشرائه...",
            min_values=1,
            max_values=1,
            options=options,
            row=0
        )

    async def callback(self, interaction):
        set_guild_context(interaction.guild_id)
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ هذه القائمة ليست لك.",
                ephemeral=True
            )
            return

        listing_id = int(self.values[0])
        rows = get_active_market_listings(limit=25)
        listing = next((r for r in rows if r[0] == listing_id), None)

        if not listing:
            await interaction.response.send_message(
                "❌ هذا العرض لم يعد متاحًا.",
                ephemeral=True
            )
            return

        _, seller_id, item_name, amount, price, _ = listing
        if seller_id == self.user_id:
            await interaction.response.send_message(
                "❌ لا يمكنك شراء عرضك الخاص.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🛒 تأكيد شراء من السوق",
            description=(
                f"📦 **العنصر:** {market_item_label(item_name)}\n"
                f"🔢 **الكمية:** `{amount:,}`\n"
                f"💰 **السعر:** `{price:,}` ذهب\n\n"
                "اضغط الزر لتأكيد الشراء."
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text="النتيجة الخاصة بالشراء ستظهر لك فقط")

        await interaction.response.send_message(
            embed=embed,
            view=MarketPurchaseView(self.user_id, listing_id),
            ephemeral=True
        )


class MarketView(GuildScopedView):
    def __init__(self, user_id, rows):
        super().__init__(timeout=180)
        self.user_id = user_id
        if rows:
            self.add_item(MarketSelect(user_id, rows))


class MarketSellSelect(discord.ui.Select):
    def __init__(self, user_id):
        self.user_id = user_id
        options = [
            discord.SelectOption(
                label=data["label"][:100],
                value=item,
                description="اختر السلاح الذي تريد عرضه للبيع"
            )
            for item, data in WEAPONS.items()
        ]
        super().__init__(
            placeholder="📦 اختر السلاح للبيع...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ هذه القائمة ليست لك.",
                ephemeral=True
            )
            return
        await interaction.response.send_modal(
            MarketSellModal(self.user_id, self.values[0])
        )


class MarketSellModal(discord.ui.Modal):
    def __init__(self, user_id, item_name):
        super().__init__(title=f"بيع {market_item_label(item_name)[:35]}")
        self.user_id = user_id
        self.item_name = item_name

        self.amount_input = discord.ui.TextInput(
            label="الكمية",
            placeholder="مثال: 5",
            required=True,
            max_length=8
        )
        self.price_input = discord.ui.TextInput(
            label="السعر الإجمالي بالذهب",
            placeholder="مثال: 30000",
            required=True,
            max_length=12
        )
        self.add_item(self.amount_input)
        self.add_item(self.price_input)

    async def on_submit(self, interaction):
        set_guild_context(interaction.guild_id)
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ هذه الواجهة ليست لك.",
                ephemeral=True
            )
            return

        try:
            amount = int(str(self.amount_input.value).replace(",", "").replace("٬", ""))
            price = int(str(self.price_input.value).replace(",", "").replace("٬", ""))
        except ValueError:
            await interaction.response.send_message(
                "❌ الكمية والسعر يجب أن يكونا أرقامًا صحيحة.",
                ephemeral=True
            )
            return

        if amount <= 0 or price <= 0:
            await interaction.response.send_message(
                "❌ الكمية والسعر يجب أن يكونا أكبر من صفر.",
                ephemeral=True
            )
            return

        ok, result = create_market_listing(
            self.user_id,
            self.item_name,
            amount,
            price
        )

        if not ok:
            await interaction.response.send_message(
                f"❌ {result}",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"✅ **تم نشر العرض في السوق!**\n\n"
            f"📦 {market_item_label(self.item_name)} × `{amount:,}`\n"
            f"💰 السعر الإجمالي: `{price:,}` ذهب\n"
            f"🔢 رقم العرض: `#{result}`\n\n"
            "تم حجز الأسلحة حتى يتم الشراء أو إلغاء العرض.",
            ephemeral=True
        )


class MarketSellView(GuildScopedView):
    def __init__(self, user_id):
        super().__init__(timeout=180)
        self.add_item(MarketSellSelect(user_id))


class MyMarketSelect(discord.ui.Select):
    def __init__(self, user_id, rows):
        self.user_id = user_id
        options = [
            discord.SelectOption(
                label=f"#{listing_id} {market_item_label(item_name)} × {amount}",
                description=f"السعر: {price:,} ذهب"[:100],
                value=str(listing_id)
            )
            for listing_id, seller_id, item_name, amount, price, created_at in rows
        ]
        super().__init__(
            placeholder="❌ اختر عرضًا لإلغائه...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction):
        set_guild_context(interaction.guild_id)
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ هذه القائمة ليست لك.",
                ephemeral=True
            )
            return

        listing_id = int(self.values[0])
        ok, result = cancel_market_listing(self.user_id, listing_id)
        if not ok:
            await interaction.response.send_message(
                f"❌ {result}",
                ephemeral=True
            )
            return

        item_name, amount = result
        await interaction.response.send_message(
            f"✅ تم إلغاء العرض `#{listing_id}` وإرجاع {market_item_label(item_name)} × `{amount:,}` إلى مخزونك.",
            ephemeral=True
        )


class MyMarketView(GuildScopedView):
    def __init__(self, user_id, rows):
        super().__init__(timeout=180)
        if rows:
            self.add_item(MyMarketSelect(user_id, rows))


# =========================================================
# المتجر
# =========================================================

class ShopQuantityModal(discord.ui.Modal):
    def __init__(self, user_id, item):
        super().__init__(
            title=f"تحديد كمية - {ALL_SHOP_ITEMS[item]['label']}"
        )

        self.user_id = user_id
        self.item = item

        self.amount_input = discord.ui.TextInput(
            label="الكمية",
            placeholder="اكتب العدد مثل 5",
            required=True,
            max_length=6
        )

        self.add_item(self.amount_input)

    async def on_submit(self, interaction):
        set_guild_context(interaction.guild_id)
        try:
            amount = int(self.amount_input.value)
        except ValueError:
            await interaction.response.send_message(
                "❌ اكتب رقمًا صحيحًا.",
                ephemeral=True
            )
            return

        if amount <= 0:
            await interaction.response.send_message(
                "❌ الكمية يجب أن تكون أكبر من صفر.",
                ephemeral=True
            )
            return

        price = get_price(self.item)
        total_cost = price * amount
        data = ALL_SHOP_ITEMS[self.item]
        column = data["column"]

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            "SELECT gold FROM players WHERE user_id = ?",
            (self.user_id,)
        )

        row = cur.fetchone()
        gold = row[0] if row else 0

        if gold < total_cost:
            conn.close()

            await interaction.response.send_message(
                "❌ لا تملك الذهب الكافي لهذه الكمية.\n"
                f"📦 الكمية: `{amount}`\n"
                f"💰 سعر القطعة: `{price:,}`\n"
                f"💳 الإجمالي: `{total_cost:,}`\n"
                f"🪙 رصيدك: `{gold:,}`",
                ephemeral=True
            )
            return

        # الأنظمة الدفاعية ترفع المستوى بعدد الكمية.
        if self.item in DEFENSE_ITEMS and self.item != "صاروخ_اعتراضي":
            cur.execute(
                f"""
                UPDATE players
                SET gold = gold - ?,
                    {column} = {column} + ?
                WHERE user_id = ?
                """,
                (
                    total_cost,
                    amount,
                    self.user_id
                )
            )
        else:
            cur.execute(
                """
                UPDATE players
                SET gold = gold - ?
                WHERE user_id = ?
                """,
                (
                    total_cost,
                    self.user_id
                )
            )

            cur.execute(
                f"""
                UPDATE inventory
                SET {column} = {column} + ?
                WHERE user_id = ?
                """,
                (
                    amount,
                    self.user_id
                )
            )

        conn.commit()
        conn.close()

        progress_daily_task(self.user_id, "shop", amount)

        await interaction.response.send_message(
            f"✅ تم شراء **{data['label']}** × `{amount}`.\n"
            f"💰 الإجمالي: `{total_cost:,}` ذهب.",
            ephemeral=True
        )


class ShopSelect(discord.ui.Select):
    def __init__(self, user_id):
        self.user_id = user_id

        options = []

        for item, data in ALL_SHOP_ITEMS.items():
            price = get_price(item)

            options.append(
                discord.SelectOption(
                    label=(
                        f"{data['label']} - "
                        f"{price:,}🪙"
                    )[:100],
                    value=item
                )
            )

        super().__init__(
            placeholder="🛒 اختر شيئًا من المتجر...",
            options=options,
            row=0
        )

    async def callback(
        self,
        interaction
    ):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ هذه الواجهة ليست لك.",
                ephemeral=True
            )
            return

        item = self.values[0]

        # بعد اختيار العنصر، يحدد اللاعب الكمية التي يريد شراءها.
        await interaction.response.send_modal(
            ShopQuantityModal(
                self.user_id,
                item
            )
        )


class ShopView(GuildScopedView):
    def __init__(self, user_id):
        super().__init__(timeout=120)

        self.add_item(
            ShopSelect(user_id)
        )


class RevengeGatewayView(GuildScopedView):
    def __init__(self, user_id, target_id):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.target_id = target_id

    @discord.ui.button(
        label="🔒 فتح ترسانة الثأر",
        style=discord.ButtonStyle.danger
    )
    async def open_arsenal(self, interaction, button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ هذه الترسانة ليست لك.",
                ephemeral=True
            )
            return

        arsenal_view = ArsenalView(
            self.user_id,
            self.target_id,
            "ثار"
        )

        await interaction.response.send_message(
            embed=arsenal_view.build_embed(),
            view=arsenal_view,
            ephemeral=True
        )


# =========================================================
# نظام الدروب
# =========================================================

pending_drop = {}


def grant_drop_item(user_id, item, amount):
    """إضافة عنصر دروب للاعب مع دعم الذهب والأسلحة والدفاعات."""
    register_user(user_id)

    conn = get_db()
    cur = conn.cursor()

    if item == "gold":
        cur.execute(
            "UPDATE players SET gold = gold + ? WHERE user_id = ?",
            (amount, user_id)
        )
    elif item in ALL_SHOP_ITEMS:
        data = ALL_SHOP_ITEMS[item]
        column = data["column"]

        if item in DEFENSE_ITEMS and item != "صاروخ_اعتراضي":
            cur.execute(
                f"UPDATE players SET {column} = {column} + ? WHERE user_id = ?",
                (amount, user_id)
            )
        else:
            cur.execute(
                f"UPDATE inventory SET {column} = {column} + ? WHERE user_id = ?",
                (amount, user_id)
            )
    else:
        conn.close()
        return False

    conn.commit()
    conn.close()
    return True


def drop_item_label(item):
    if item == "gold":
        return "🪙 ذهب"
    return ALL_SHOP_ITEMS[item]["label"]


def drop_selection_text(items):
    if not items:
        return "لم يتم اختيار أي شيء بعد."
    return "\n".join(
        f"{drop_item_label(item)} × `{amount:,}`"
        for item, amount in items.items()
        if amount > 0
    ) or "لم يتم اختيار أي شيء بعد."


class DropQuantityModal(discord.ui.Modal):
    def __init__(self, parent_view, item):
        super().__init__(title=f"تحديد كمية - {drop_item_label(item)[:30]}")
        self.parent_view = parent_view
        self.item = item

        self.amount_input = discord.ui.TextInput(
            label="الكمية",
            placeholder="مثال: 10",
            required=True,
            min_length=1,
            max_length=12
        )
        self.add_item(self.amount_input)

    async def on_submit(self, interaction):
        set_guild_context(interaction.guild_id)
        if interaction.user.id != self.parent_view.admin_id:
            await interaction.response.send_message(
                "❌ هذه الواجهة ليست لك.",
                ephemeral=True
            )
            return

        amount = parse_amount(
            str(self.amount_input.value).replace(",", "").replace("٬", "")
        )

        if amount is None or amount <= 0:
            await interaction.response.send_message(
                "❌ الكمية يجب أن تكون رقمًا أكبر من صفر.",
                ephemeral=True
            )
            return

        self.parent_view.items[self.item] = amount

        await interaction.response.edit_message(
            embed=self.parent_view.build_embed(),
            view=self.parent_view
        )


class DropSelect(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_view = parent_view

        options = [
            discord.SelectOption(
                label="🪙 ذهب",
                description="تحديد كمية الذهب في الدروب",
                value="gold"
            )
        ]

        for item, data in ALL_SHOP_ITEMS.items():
            options.append(
                discord.SelectOption(
                    label=data["label"][:100],
                    description="تحديد الكمية التي سيحصل عليها الفائز",
                    value=item
                )
            )

        super().__init__(
            placeholder="📦 اختر عنصرًا لإضافته للدروب...",
            min_values=1,
            max_values=1,
            options=options,
            row=0
        )

    async def callback(self, interaction):
        if interaction.user.id != self.parent_view.admin_id:
            await interaction.response.send_message(
                "❌ هذه الواجهة ليست لك.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            DropQuantityModal(
                self.parent_view,
                self.values[0]
            )
        )


class DropAdminView(GuildScopedView):
    def __init__(self, admin_id):
        super().__init__(timeout=300)
        self.admin_id = admin_id
        self.items = {}
        self.add_item(DropSelect(self))

    def build_embed(self):
        embed = discord.Embed(
            title="📦 تجهيز الدروب",
            description=(
                "اختر العناصر والكميات من القائمة.\n"
                "يمكنك إضافة أكثر من عنصر، مثل: `10 كروز + 3,000 ذهب`.\n"
                "بعد الانتهاء اضغط **تأكيد الدروب**."
            ),
            color=discord.Color.orange()
        )
        embed.add_field(
            name="🎁 محتوى الدروب",
            value=drop_selection_text(self.items),
            inline=False
        )
        embed.add_field(
            name="👥 عدد الفائزين",
            value="`3` لاعبين",
            inline=True
        )
        return embed

    @discord.ui.button(
        label="✅ تأكيد الدروب",
        style=discord.ButtonStyle.success,
        row=1
    )
    async def confirm(self, interaction, button):
        global pending_drop

        if interaction.user.id != self.admin_id or not is_admin(interaction.user):
            await interaction.response.send_message(
                "❌ هذه الواجهة ليست لك.",
                ephemeral=True
            )
            return

        if not self.items:
            await interaction.response.send_message(
                "❌ أضف عنصرًا واحدًا على الأقل إلى الدروب.",
                ephemeral=True
            )
            return

        pending_drop[current_guild_id()] = {
            "items": dict(self.items),
            "max_claims": 3,
            "claimed": set(),
            "created_by": self.admin_id,
            "created_at": datetime.now()
        }

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="✅ تم تجهيز الدروب",
                description=(
                    "تم حفظ الدروب بنجاح.\n"
                    "اكتب الآن `انزال` في شات اللاعبين لإظهاره.\n\n"
                    f"🎁 المحتوى:\n{drop_selection_text(self.items)}\n"
                    "👥 أول 3 لاعبين يحصلون على المحتوى كاملًا."
                ),
                color=discord.Color.green()
            ),
            view=None
        )

    @discord.ui.button(
        label="🗑️ إلغاء",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def cancel(self, interaction, button):
        if interaction.user.id != self.admin_id or not is_admin(interaction.user):
            await interaction.response.send_message(
                "❌ هذه الواجهة ليست لك.",
                ephemeral=True
            )
            return

        await interaction.response.edit_message(
            content="❌ تم إلغاء تجهيز الدروب.",
            embed=None,
            view=None
        )


class DropClaimView(GuildScopedView):
    def __init__(self):
        super().__init__(timeout=180)
        self.guild_id = current_guild_id()

    async def on_timeout(self):
        global pending_drop
        pending_drop.pop(self.guild_id, None)
        for item in self.children:
            item.disabled = True
        if getattr(self, "message", None):
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    @discord.ui.button(
        label="🎁 أخذ الدروب",
        style=discord.ButtonStyle.success
    )
    async def claim(self, interaction, button):
        global pending_drop

        drop = pending_drop.get(current_guild_id())
        if not drop:
            await interaction.response.send_message(
                "❌ لا يوجد دروب متاح حاليًا.",
                ephemeral=True
            )
            return

        if interaction.user.id in drop["claimed"]:
            await interaction.response.send_message(
                "❌ حصلت على هذا الدروب مسبقًا.",
                ephemeral=True
            )
            return

        if len(drop["claimed"]) >= drop["max_claims"]:
            await interaction.response.send_message(
                "❌ انتهت الدروب. تم أخذها من أول 3 لاعبين.",
                ephemeral=True
            )
            return

        for item, amount in drop["items"].items():
            if not grant_drop_item(interaction.user.id, item, amount):
                await interaction.response.send_message(
                    "❌ حدث خطأ أثناء توزيع الدروب.",
                    ephemeral=True
                )
                return

        drop["claimed"].add(interaction.user.id)
        position = len(drop["claimed"])
        remaining = drop["max_claims"] - position

        await interaction.response.send_message(
            f"🎉 **مبروك!** حصلت على الدروب رقم `{position}/3`.\n"
            f"🎁 المحتوى:\n{drop_selection_text(drop['items'])}",
            ephemeral=True
        )

        if remaining <= 0:
            pending_drop.pop(current_guild_id(), None)
            try:
                button.disabled = True
                await interaction.message.edit(view=self)
            except Exception:
                pass

class GameManageModal(discord.ui.Modal, title="⚙️ تعديل اللاعب"):
    item = discord.ui.TextInput(
        label="العنصر",
        placeholder="gold أو اسم السلاح/الدفاع",
        required=True,
        max_length=50
    )
    amount = discord.ui.TextInput(
        label="العدد",
        placeholder="مثال: 5000",
        required=True,
        max_length=15
    )

    def __init__(self, admin_id, target_id, action):
        super().__init__()
        self.admin_id = admin_id
        self.target_id = target_id
        self.action = action

    async def on_submit(self, interaction: discord.Interaction):
        set_guild_context(interaction.guild_id)
        if interaction.user.id != self.admin_id or not is_admin(interaction.user):
            await interaction.response.send_message(
                "❌ هذه الواجهة ليست لك.",
                ephemeral=True
            )
            return

        item = str(self.item.value).strip()
        amount = parse_amount(str(self.amount.value).replace(",", "").replace("٬", ""))

        if amount is None or amount <= 0:
            await interaction.response.send_message(
                "❌ العدد يجب أن يكون أكبر من صفر.",
                ephemeral=True
            )
            return

        if item not in ALL_SHOP_ITEMS and item != "gold":
            await interaction.response.send_message(
                "❌ العنصر غير معروف. استخدم `gold` أو اسم العنصر كما يظهر في المتجر.",
                ephemeral=True
            )
            return

        register_user(self.target_id)
        conn = get_db()
        cur = conn.cursor()

        if item == "gold":
            if self.action == "اضافة":
                cur.execute(
                    "UPDATE players SET gold = gold + ? WHERE user_id = ?",
                    (amount, self.target_id)
                )
            else:
                cur.execute(
                    "UPDATE players SET gold = max(0, gold - ?) WHERE user_id = ?",
                    (amount, self.target_id)
                )
        else:
            data = ALL_SHOP_ITEMS[item]
            column = data["column"]

            if item in DEFENSE_ITEMS and item != "صاروخ_اعتراضي":
                table = "players"
            else:
                table = "inventory"

            if self.action == "اضافة":
                cur.execute(
                    f"UPDATE {table} SET {column} = {column} + ? WHERE user_id = ?",
                    (amount, self.target_id)
                )
            else:
                cur.execute(
                    f"UPDATE {table} SET {column} = max(0, {column} - ?) WHERE user_id = ?",
                    (amount, self.target_id)
                )

        conn.commit()
        conn.close()

        action_text = "إضافة" if self.action == "اضافة" else "سحب"
        item_label = ALL_SHOP_ITEMS[item]["label"] if item in ALL_SHOP_ITEMS else "💰 الذهب"

        await interaction.response.send_message(
            f"✅ تم **{action_text}** `{amount:,}` من **{item_label}** للاعب <@{self.target_id}>.",
            ephemeral=True
        )


class GameManageView(GuildScopedView):
    def __init__(self, admin_id, target_id):
        super().__init__(timeout=180)
        self.admin_id = admin_id
        self.target_id = target_id

    @discord.ui.button(label="➕ إضافة", style=discord.ButtonStyle.success)
    async def add(self, interaction, button):
        if interaction.user.id != self.admin_id or not is_admin(interaction.user):
            await interaction.response.send_message("❌ هذه الواجهة ليست لك.", ephemeral=True)
            return
        await interaction.response.send_modal(
            GameManageModal(self.admin_id, self.target_id, "اضافة")
        )

    @discord.ui.button(label="➖ سحب", style=discord.ButtonStyle.danger)
    async def remove(self, interaction, button):
        if interaction.user.id != self.admin_id or not is_admin(interaction.user):
            await interaction.response.send_message("❌ هذه الواجهة ليست لك.", ephemeral=True)
            return
        await interaction.response.send_modal(
            GameManageModal(self.admin_id, self.target_id, "سحب")
        )


PRICE_PERCENTAGES = list(range(5, 101, 5))


class PriceAdjustSelect(discord.ui.Select):
    def __init__(self, admin_id, increase):
        self.admin_id = admin_id
        self.increase = increase

        options = [
            discord.SelectOption(
                label=f"{'رفع' if increase else 'خفض'} {percent}%",
                value=str(percent),
                description=(
                    f"{'زيادة' if increase else 'تقليل'} أسعار المتجر بنسبة {percent}%"
                )
            )
            for percent in PRICE_PERCENTAGES
        ]

        super().__init__(
            placeholder=(
                "📈 اختر نسبة رفع الأسعار..."
                if increase
                else "📉 اختر نسبة خفض الأسعار..."
            ),
            options=options,
            row=0 if increase else 1
        )

    async def callback(self, interaction: discord.Interaction):
        set_guild_context(interaction.guild_id)

        if interaction.user.id != self.admin_id or not is_admin(interaction.user):
            await interaction.response.send_message(
                "❌ هذه القائمة للآدمن فقط.",
                ephemeral=True
            )
            return

        percent = int(self.values[0])
        multiplier = (
            1 + (percent / 100)
            if self.increase
            else 1 - (percent / 100)
        )

        changed = []
        for item, data in ALL_SHOP_ITEMS.items():
            old_price = get_price(item)
            new_price = max(1, int(round(old_price * multiplier)))
            set_price(item, new_price)
            changed.append(
                f"{data['label']} — `{new_price:,}` ➡️ `{old_price:,}` ذهب"
            )

        action = "رفع" if self.increase else "خفض"
        sign = "+" if self.increase else "-"

        embed = discord.Embed(
            title="💰 تحديث أسعار المتجر",
            description=(
                f"📢 تم **{action} جميع أسعار المتجر بنسبة {percent}%**.\n\n"
                + "\n".join(changed)
            ),
            color=discord.Color.green() if self.increase else discord.Color.red()
        )
        embed.set_footer(text=f"التغيير: {sign}{percent}%")

        # رسالة عامة في نفس الروم، وليست خاصة بالآدمن.
        await interaction.response.send_message(embed=embed)


class PriceAdminView(GuildScopedView):
    def __init__(self, admin_id):
        super().__init__(timeout=180)
        self.admin_id = admin_id
        self.add_item(PriceAdjustSelect(admin_id, True))
        self.add_item(PriceAdjustSelect(admin_id, False))


# =========================================================
# أوامر الرسائل النصية
# =========================================================

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.guild is None:
        return

    set_guild_context(message.guild.id)

    if message.channel.id not in ALLOWED_CHANNELS:
        return

    content = message.content.strip()

    if not content:
        return

    tokens = content.split()
    cmd = tokens[0]

    # =====================================================
    # ابدا
    # =====================================================

    if cmd == "ابدا":
        if has_base(message.author.id):
            await message.channel.send(
                f"⚠️ {message.author.mention} "
                "لديك قاعدة عسكرية بالفعل."
            )
            return

        register_user(
            message.author.id
        )

        await message.channel.send(
            f"🚀 **تم تأسيس قاعدة "
            f"{message.author.mention}!**\n"
            "🪙 رصيد البداية: `50,000` ذهب."
        )
        return

    # =====================================================
    # اوامر
    # =====================================================

    if cmd == "اوامر":
        embed = discord.Embed(
            title="📋 أوامر اللعبة",
            color=discord.Color.blue()
        )

        embed.description = (
            "`ابدا` — إنشاء القاعدة.\n"
            "`قاعدتي` — عرض القاعدة بشكل خاص.\n"
            "`اوامر` — عرض أوامر اللعبة.\n"
            "`انجازاتي` — الكؤوس والرتبة.\n"
            "`التوب` — أفضل 10 لاعبين.\n"
            "`مهمه` — مهمة للحصول على ذهب (كل 4 دقائق).\n"
            "`مهامي` — 3 مهام يومية مع مكافآت ذهبية.\n"
            "`مكافأة` — مكافأة من 3,000 إلى 10,000 ذهب (كل 4 دقائق).\n"
            "`متجر` — شراء الأسلحة والدفاعات.\n"
            "`سوق` — شراء أسلحة من لاعبين آخرين.\n"
            "`بيع` — عرض أسلحتك للبيع في السوق.\n"
            "`عروضي` — عرض وإلغاء عروضك في السوق.\n"
            "`ذهب` — عرض رصيد الذهب على الخاص.\n"
            "`استكشاف` — استكشاف مقابل الذهب (نجاح 60% / خسارة 40%)، مرة كل 90 ثانية.\n\n"
            "`صناديق` — شراء وفتح صناديق عشوائية بمكافآت مختلفة.\n"
            "`صناديق_السجل` — عرض آخر الصناديق التي فتحتها بشكل خاص.\n\n"

            "`قصف @الشخص` — هجوم واختيار كمية كل سلاح.\n"
            "`تجسس @الشخص` — تقرير تجسس خاص.\n"
            "`ثار @الشخص` — الثأر ممن هاجمك سابقًا.\n\n"

            "`تحالف @الشخص` — إرسال طلب تحالف (100,000 ذهب لكل طرف).\n"
            "`الغاء_تحالف @الشخص` — إلغاء التحالف.\n"
            "`حظر_جوي @الشخص` — تخصيص طائرات للدفاع، ولا يشترط وجود تحالف.\n\n"

            "`معلومات @الشخص` — للآدمن.\n"
            "`تعديل @الشخص` — إدارة اللاعب عبر أزرار الإضافة والسحب (للآدمن).\n"
            "`سعر` — تعديل أسعار المتجر عبر الإيمبد (للآدمن).\n"
            "`تصفير كل` — تصفير جميع اللاعبين وإعادتهم للبداية (للآدمن).\n"
            "`انزال` — للآدمن: نشر الدروب للاعبين.\n"
            "`🎲 الأحداث` — أحداث عشوائية تظهر تلقائيًا كل 15 دقيقة."
        )

        await message.channel.send(
            embed=embed
        )
        return

    # =====================================================
    # مهامي - المهام اليومية
    # =====================================================

    if cmd == "مهامي":
        if not has_base(message.author.id):
            await message.channel.send(
                f"❌ {message.author.mention} يجب أن تكتب `ابدا` أولًا."
            )
            return

        embed = daily_missions_embed(message.author.id)
        await message.channel.send(
            embed=embed,
            view=DailyMissionsView(message.author.id),
            delete_after=180
        )
        return

    # =====================================================
    # ذهب - زر خاص داخل الشات
    # =====================================================

    if cmd == "ذهب":
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        embed = discord.Embed(
            title="🪙 رصيد الذهب",
            description=(
                "اضغط على الزر بالأسفل لعرض رصيدك من الذهب.\n\n"
                "🔒 **الرصيد سيظهر لك وحدك ولا يراه باقي الأعضاء.**"
            ),
            color=discord.Color.gold()
        )
        embed.set_footer(text="Sky Strike • الرصيد خاص بصاحب الزر")

        await message.channel.send(
            embed=embed,
            view=GoldBalanceView(message.author.id),
            delete_after=180
        )
        return

    # =====================================================
    # استكشاف
    # =====================================================

    if cmd == "استكشاف":
        gold = get_gold(message.author.id)

        embed = discord.Embed(
            title="🧭 الاستكشاف",
            description=(
                "أرسل قواتك لاستكشاف مناطق مجهولة مقابل الذهب.\n\n"
                f"💰 **أقل كمية:** `{EXPLORATION_MIN_GOLD:,}` ذهب\n"
                "🎯 **نسبة النجاح:** `60%`\n"
                "💥 **نسبة الخسارة:** `40%`\n"
                "📈 عند النجاح تحصل على المبلغ المحدد + `40%` ربح.\n"
                "💸 عند الفشل تخسر كامل المبلغ الذي حددته.\n\n"
                f"🪙 **رصيدك الحالي:** `{gold:,}` ذهب"
            ),
            color=discord.Color.dark_green()
        )

        await message.channel.send(
            embed=embed,
            view=ExplorationView(message.author.id),
            delete_after=180
        )
        return

    # =====================================================
    # متجر
    # =====================================================

    if cmd == "صناديق":
        if not has_base(message.author.id):
            await message.channel.send(
                f"❌ {message.author.mention} يجب أن تكتب `ابدا` أولًا.",
                delete_after=7
            )
            return

        embed = discord.Embed(
            title="📦 صناديق Sky Strike",
            description=(
                "اختر نوع الصندوق الذي تريد فتحه.\n\n"
                "🟫 **عادي** — `5,000` ذهب\n"
                "🟦 **نادر** — `15,000` ذهب\n"
                "🟪 **أسطوري** — `50,000` ذهب\n\n"
                "🎲 كل صندوق يحتوي على مكافأة عشوائية.\n"
                "🔒 نتيجة الفتح تظهر لك أنت فقط.\n\n"
                f"🪙 رصيدك الحالي: `{get_gold(message.author.id):,}` ذهب"
            ),
            color=discord.Color.gold()
        )
        await message.channel.send(
            embed=embed,
            view=ChestShopView(message.author.id),
            delete_after=180
        )
        return

    if cmd == "صناديق_السجل":
        if not has_base(message.author.id):
            await message.channel.send(
                f"❌ {message.author.mention} يجب أن تكتب `ابدا` أولًا.",
                delete_after=7
            )
            return

        await message.channel.send(
            f"🔒 {message.author.mention} اضغط الزر لعرض سجل صناديقك بشكل خاص.",
            view=ChestHistoryView(message.author.id),
            delete_after=120
        )
        return

    if cmd == "متجر":
        if not has_base(message.author.id):
            await message.channel.send(
                f"❌ {message.author.mention} يجب أن تكتب `ابدا` أولًا.",
                delete_after=7
            )
            return

        embed = discord.Embed(
            title="🛒 متجر Sky Strike",
            description=(
                "اختر أي عنصر من القائمة لشرائه.\n"
                "💡 الأسلحة الجديدة موجودة هنا فقط ولن تظهر ضمن `اوامر`.\n"
                f"🪙 رصيدك الحالي: `{get_gold(message.author.id):,}`"
            ),
            color=discord.Color.gold()
        )

        for item, data in ALL_SHOP_ITEMS.items():
            if item == "gold":
                continue

            price = get_price(item)
            kind = "🛡️ دفاع" if item in DEFENSE_ITEMS else "⚔️ هجوم"
            embed.add_field(
                name=data["label"],
                value=f"{kind} — `{price:,}` ذهب",
                inline=True
            )

        await message.channel.send(
            embed=embed,
            view=ShopView(message.author.id),
            delete_after=180
        )
        return

    # =====================================================
    # سوق اللاعبين
    # =====================================================

    if cmd == "سوق":
        if not has_base(message.author.id):
            await message.channel.send(
                f"❌ {message.author.mention} يجب أن تكتب `ابدا` أولًا.",
                delete_after=7
            )
            return

        rows = get_active_market_listings(limit=20)
        embed = discord.Embed(
            title="🏪 سوق اللاعبين",
            description=(
                "هنا يعرض اللاعبون الأسلحة للبيع لبعضهم البعض.\n"
                "اختر عرضًا من القائمة ثم اضغط **شراء العرض**.\n\n"
                + market_listings_text(rows, message.guild)
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text="الأسلحة المعروضة يتم حجزها حتى البيع أو إلغاء العرض")

        await message.channel.send(
            embed=embed,
            view=MarketView(message.author.id, rows),
            delete_after=180
        )
        return

    if cmd == "بيع":
        if not has_base(message.author.id):
            await message.channel.send(
                f"❌ {message.author.mention} يجب أن تكتب `ابدا` أولًا.",
                delete_after=7
            )
            return

        embed = discord.Embed(
            title="💰 بيع في السوق",
            description=(
                "اختر السلاح الذي تريد بيعه.\n\n"
                "بعد الاختيار ستحدد **الكمية** و**السعر الإجمالي**.\n"
                "⚠️ يتم حجز الأسلحة عند نشر العرض حتى يتم شراؤه أو إلغاؤه."
            ),
            color=discord.Color.orange()
        )
        await message.channel.send(
            embed=embed,
            view=MarketSellView(message.author.id),
            delete_after=180
        )
        return

    if cmd == "عروضي":
        if not has_base(message.author.id):
            await message.channel.send(
                f"❌ {message.author.mention} يجب أن تكتب `ابدا` أولًا.",
                delete_after=7
            )
            return

        rows = get_active_market_listings(limit=20, seller_id=message.author.id)
        embed = discord.Embed(
            title="📋 عروضي في السوق",
            description=market_listings_text(rows, message.guild),
            color=discord.Color.blue()
        )
        if rows:
            embed.set_footer(text="اختر عرضًا من القائمة لإلغائه وإرجاع السلاح لمخزونك")
        else:
            embed.set_footer(text="ليس لديك عروض نشطة حاليًا")

        await message.channel.send(
            embed=embed,
            view=MyMarketView(message.author.id, rows) if rows else None,
            delete_after=180
        )
        return

    # =====================================================
    # منع الأوامر بدون قاعدة
    # =====================================================

    if not has_base(
        message.author.id
    ):
        await message.channel.send(
            f"❌ {message.author.mention} "
            "يجب أن تكتب `ابدا` أولًا.",
            delete_after=7
        )
        return

    # =====================================================
    # قاعدتي
    # =====================================================

    if cmd == "قاعدتي":
        await message.channel.send(
            f"🔒 {message.author.mention} "
            "اضغط الزر لعرض قاعدتك بشكل خاص.",
            view=BasePrivateView(
                message.author.id
            ),
            delete_after=120
        )
        return

    # =====================================================
    # انجازاتي
    # =====================================================

    if cmd == "انجازاتي":
        rank = update_rank(
            message.author.id
        )

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT trophies
            FROM players
            WHERE user_id = ?
            """,
            (message.author.id,)
        )

        row = cur.fetchone()
        trophies = row[0] if row else 0

        conn.close()

        await message.channel.send(
            f"🏆 **سجلك العسكري:**\n"
            f"🎖️ الرتبة: `{rank}`\n"
            f"🏆 الكؤوس: `{trophies:,}`"
        )
        return

    # =====================================================
    # التوب
    # =====================================================

    if cmd == "التوب":
        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                user_id,
                trophies,
                rank_title
            FROM players
            ORDER BY trophies DESC
            LIMIT 10
        """)

        rows = cur.fetchall()
        conn.close()

        embed = discord.Embed(
            title="🏆 TOP 10",
            color=discord.Color.gold()
        )

        text = ""

        for index, (
            uid,
            trophies,
            rank
        ) in enumerate(rows, 1):
            member = message.guild.get_member(
                uid
            )

            name = (
                member.mention
                if member
                else f"<@{uid}>"
            )

            text += (
                f"**{index}.** {name} "
                f"— `{trophies:,}` 🏆 "
                f"— {rank}\n"
            )

        embed.description = (
            text
            if text
            else "لا توجد قواعد."
        )

        await message.channel.send(
            embed=embed
        )
        return

    # =====================================================
    # مكافأة
    # =====================================================

    if cmd in ("مكافاة", "مكافأة", "مكافاه"):
        if not has_base(message.author.id):
            await message.channel.send(
                f"❌ {message.author.mention} يجب أن تكتب `ابدا` أولًا حتى تتمكن من استلام المكافأة."
            )
            return

        now = datetime.now()
        reward_key = (current_guild_id(), message.author.id)
        last_reward = last_reward_times.get(reward_key)

        if last_reward:
            remaining = (
                timedelta(minutes=REWARD_COOLDOWN_MINUTES)
                - (now - last_reward)
            )

            if remaining.total_seconds() > 0:
                await message.channel.send(
                    f"⏳ المكافأة غير جاهزة بعد.\n"
                    f"المتبقي: `{format_remaining(remaining)}`."
                )
                return

        reward = random.randint(3000, 10000)
        last_reward_times[reward_key] = now

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "UPDATE players SET gold = gold + ? WHERE user_id = ?",
            (reward, message.author.id)
        )
        conn.commit()
        conn.close()

        await message.channel.send(
            f"🎁 **مكافأة {message.author.mention}!**\n"
            f"🪙 حصلت على `{reward:,}` ذهب."
        )
        return

    # =====================================================
    # مهمه
    # =====================================================

    if cmd == "مهمه":
        if not has_base(message.author.id):
            await message.channel.send(
                f"❌ {message.author.mention} يجب أن تكتب `ابدا` أولًا حتى تتمكن من تنفيذ المهمة."
            )
            return

        # تأكد من وجود سجل اللاعب حتى يعمل الأمر مع قواعد البيانات القديمة.
        register_user(message.author.id)
        now = datetime.now()

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT last_mission
            FROM cooldowns
            WHERE user_id = ?
            """,
            (message.author.id,)
        )

        row = cur.fetchone()

        if row and row[0]:
            last = datetime.strptime(
                row[0],
                "%Y-%m-%d %H:%M:%S"
            )

            remaining = (
                timedelta(minutes=4)
                - (now - last)
            )

            if remaining.total_seconds() > 0:
                conn.close()

                await message.channel.send(
                    f"⏳ المهمة غير جاهزة.\n"
                    f"المتبقي: "
                    f"`{format_remaining(remaining)}`."
                )
                return

        earned = random.randint(
            10000,
            25000
        )

        cur.execute(
            """
            UPDATE players
            SET gold = gold + ?
            WHERE user_id = ?
            """,
            (
                earned,
                message.author.id
            )
        )

        cur.execute("""
            INSERT INTO cooldowns
            (
                user_id,
                last_mission
            )
            VALUES (?, ?)
            ON CONFLICT(user_id)
            DO UPDATE SET
                last_mission = excluded.last_mission
        """, (
            message.author.id,
            now.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        ))

        conn.commit()
        conn.close()

        progress_daily_task(message.author.id, "mission")
        await message.channel.send(
            f"💼 **نجحت المهمة!** "
            f"حصلت على `{earned:,}` ذهب."
        )
        return

    # =====================================================
    # تحالف
    # =====================================================

    if cmd == "تحالف":
        if not message.mentions:
            await message.channel.send(
                "❌ الاستخدام: "
                "`تحالف @الشخص`"
            )
            return

        ally = message.mentions[0]

        if ally.id == message.author.id:
            await message.channel.send(
                "❌ لا يمكنك التحالف مع نفسك."
            )
            return

        if not has_base(ally.id):
            await message.channel.send(
                "❌ الشخص لا يملك قاعدة."
            )
            return

        if alliance_exists(
            message.author.id,
            ally.id
        ):
            await message.channel.send(
                "❌ يوجد تحالف بينكما بالفعل."
            )
            return

        await message.channel.send(
            f"🤝 {ally.mention}\n"
            f"القائد {message.author.mention} "
            "أرسل لك طلب تحالف.\n"
            "💰 التكلفة: `100,000` ذهب لكل طرف.",
            view=AcceptAllianceView(
                message.author.id,
                ally.id
            )
        )
        return

    # =====================================================
    # الغاء_تحالف
    # =====================================================

    if cmd == "الغاء_تحالف":
        if not message.mentions:
            await message.channel.send(
                "❌ الاستخدام: "
                "`الغاء_تحالف @الشخص`"
            )
            return

        ally = message.mentions[0]

        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            DELETE FROM active_alliances
            WHERE
                (user_id = ? AND ally_id = ?)
                OR
                (user_id = ? AND ally_id = ?)
        """, (
            message.author.id,
            ally.id,
            ally.id,
            message.author.id
        ))

        cur.execute("""
            DELETE FROM defense_alliances
            WHERE
                (user_id = ? AND ally_id = ?)
                OR
                (user_id = ? AND ally_id = ?)
        """, (
            message.author.id,
            ally.id,
            ally.id,
            message.author.id
        ))

        conn.commit()
        conn.close()

        await message.channel.send(
            f"💔 تم إلغاء التحالف بين "
            f"{message.author.mention} "
            f"و {ally.mention}."
        )
        return

    # =====================================================
    # حظر_جوي
    # =====================================================

    if cmd == "حظر_جوي":
        if not message.mentions:
            await message.channel.send(
                "❌ الاستخدام: "
                "`حظر_جوي @الحليف`"
            )
            return

        ally = message.mentions[0]

        await message.channel.send(
            f"🛡️ {message.author.mention} "
            f"خصص دفاعًا جويًا لـ {ally.mention}.",
            view=DefenseButtonView(
                message.author.id,
                ally.id
            )
        )
        return

    # =====================================================
    # قصف
    # =====================================================

    if cmd == "قصف":
        if not message.mentions:
            await message.channel.send(
                "❌ الاستخدام: "
                "`قصف @الشخص`"
            )
            return

        target = message.mentions[0]

        if target.id == message.author.id:
            await message.channel.send(
                "❌ لا يمكنك قصف نفسك."
            )
            return

        if not has_base(target.id):
            await message.channel.send(
                "❌ الهدف لا يملك قاعدة."
            )
            return

        cooldown = get_attack_cooldown(
            message.author.id
        )

        if cooldown:
            remaining = (
                timedelta(minutes=5)
                - (datetime.now() - cooldown)
            )

            if remaining.total_seconds() > 0:
                await message.channel.send(
                    f"⏳ منصاتك في تبريد.\n"
                    f"المتبقي: "
                    f"`{format_remaining(remaining)}`."
                )
                return

        # المطلوب: الرسالة العامة لا تكشف الهدف.
        await message.channel.send(
            "🚨 **تم رصد تحرك عسكري.**"
        )

        key = joint_key(
            message.channel.id,
            target.id
        )

        if key in pending_joint_attacks:
            await message.channel.send(
                "⚠️ يوجد هجوم على هذا الهدف "
                "قيد التجهيز بالفعل. "
                "استخدم رسالة الهجوم الموجودة."
            )
            return

        pending_joint_attacks[key] = {
            "channel_id": message.channel.id,
            "creator_id": message.author.id,
            "target_id": target.id,
            "allowed": [
                message.author.id
            ],
            "selections": {},
            "created_at": datetime.now()
        }

        asyncio.create_task(expire_attack_session(key))

        await message.channel.send(
            "🔒 **تم فتح جلسة الهجوم بشكل خاص.**\n"
            "القائد يستطيع فتح جلسته الخاصة، والحلفاء يستطيعون الانضمام "
            "من خلال الزر دون كشف الهدف في الدردشة.",
            view=AttackGatewayView(
                message.channel.id,
                message.author.id,
                target.id
            ),
            delete_after=ATTACK_SETUP_TIMEOUT_SECONDS
        )
        return

    # =====================================================
    # تجسس
    # =====================================================

    if cmd == "تجسس":
        if not message.mentions:
            await message.channel.send(
                "❌ الاستخدام: "
                "`تجسس @الشخص`"
            )
            return

        target = message.mentions[0]

        if target.id == message.author.id:
            await message.channel.send(
                "❌ لا يمكنك التجسس على نفسك."
            )
            return

        if not has_base(target.id):
            await message.channel.send(
                "❌ الهدف لا يملك قاعدة."
            )
            return

        if get_gold(
            message.author.id
        ) < 5000:
            await message.channel.send(
                "❌ تحتاج `5,000` ذهب "
                "لعملية التجسس."
            )
            return

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE players
            SET gold = gold - 5000
            WHERE user_id = ?
            """,
            (message.author.id,)
        )

        conn.commit()
        conn.close()

        # المطلوب: الرسالة العامة لا تكشف الهدف.
        await message.channel.send(
            "🚨 **تم رصد تحرك عسكري.**"
        )

        inv = get_inventory(
            target.id
        )

        accuracy = random.randint(
            50,
            85
        )

        embed = discord.Embed(
            title="🕵️ تقرير التجسس - خاص",
            color=discord.Color.dark_purple()
        )

        embed.description = (
            "هذا التقرير لا يراه إلا منفذ "
            "عملية التجسس."
        )

        embed.add_field(
            name="📊 دقة الرصد",
            value=f"`{accuracy}%`",
            inline=False
        )

        report = []

        for item, data in WEAPONS.items():
            actual = inv[
                data["column"]
            ]

            estimated = int(
                actual * accuracy / 100
            )

            report.append(
                f"{data['label']}: `{estimated}`"
            )

        embed.add_field(
            name="🎒 الترسانة التقديرية",
            value="\n".join(report),
            inline=False
        )

        class SpyPrivateView(
            discord.ui.View
        ):
            def __init__(
                self,
                owner_id
            ):
                super().__init__(
                    timeout=60
                )

                self.owner_id = owner_id

            @discord.ui.button(
                label="🔒 عرض التقرير الخاص",
                style=discord.ButtonStyle.primary
            )
            async def show(
                self,
                interaction,
                button
            ):
                if interaction.user.id != self.owner_id:
                    await interaction.response.send_message(
                        "❌ هذا التقرير ليس لك.",
                        ephemeral=True
                    )
                    return

                await interaction.response.send_message(
                    embed=embed,
                    ephemeral=True
                )

        await message.channel.send(
            f"🔒 {message.author.mention} "
            "اضغط الزر لرؤية تقرير التجسس بشكل خاص.",
            view=SpyPrivateView(
                message.author.id
            ),
            delete_after=60
        )
        return

    # =====================================================
    # ثار
    # =====================================================

    if cmd == "ثار":
        if not message.mentions:
            await message.channel.send(
                "❌ الاستخدام: "
                "`ثار @الشخص`"
            )
            return

        target = message.mentions[0]

        if target.id == message.author.id:
            await message.channel.send(
                "❌ لا يمكنك أخذ الثأر من نفسك."
            )
            return

        if not has_base(target.id):
            await message.channel.send(
                "❌ الهدف لا يملك قاعدة."
            )
            return

        # الهدف يجب أن يكون قد هاجم اللاعب سابقًا.
        if not was_attacked_by(
            target.id,
            message.author.id
        ):
            await message.channel.send(
                "❌ لا يمكنك أخذ الثأر من هذا الشخص "
                "لأنه لم يسبق له مهاجمتك."
            )
            return

        await message.channel.send(
            "🔥 **تم تفعيل طلب الثأر.**\n"
            "🔒 اختر ترسانة جديدة من مخزونك.\n"
            "لن يتم نسخ ترسانة الهجوم السابق.",
            view=RevengeGatewayView(
                message.author.id,
                target.id
            ),
            delete_after=180
        )
        return

    # =====================================================
    # تعديل - إدارة لاعب للآدمن
    # =====================================================

    if cmd in ("تعديل", "ادارة_اللعبة"):
        if not is_admin(message.author):
            await message.channel.send(
                "❌ هذا الأمر للآدمن فقط."
            )
            return

        if not message.mentions:
            await message.channel.send(
                "⚠️ الاستخدام: `تعديل @اللاعب}`"
            )
            return

        target = message.mentions[0]
        register_user(target.id)

        embed = discord.Embed(
            title="⚙️ إدارة اللاعب",
            description=(
                f"👤 اللاعب: {target.mention}\n\n"
                "اختر العملية التي تريد تنفيذها من الأزرار بالأسفل.\n"
                "بعدها اكتب اسم العنصر والعدد."
            ),
            color=discord.Color.orange()
        )

        await message.channel.send(
            embed=embed,
            view=GameManageView(message.author.id, target.id)
        )
        return

    # =====================================================
    # معلومات
    # =====================================================

    if cmd == "معلومات":
        if not is_admin(
            message.author
        ):
            await message.channel.send(
                "❌ هذا الأمر للآدمن فقط."
            )
            return

        if not message.mentions:
            await message.channel.send(
                "❌ الاستخدام: "
                "`معلومات @اللاعب`"
            )
            return

        target = message.mentions[0]

        register_user(
            target.id
        )

        embed = build_base_embed(
            target.id
        )

        embed.title = (
            f"📊 معلومات {target.name}"
        )

        await message.channel.send(
            embed=embed
        )
        return

    # =====================================================
    # دروب - للآدمن
    # =====================================================

    if cmd == "دروب":
        if not is_admin(message.author):
            await message.channel.send(
                "❌ هذا الأمر للآدمن فقط."
            )
            return

        view = DropAdminView(message.author.id)
        await message.channel.send(
            embed=view.build_embed(),
            view=view
        )
        return

    # =====================================================
    # انزال - للاعبين
    # =====================================================

    if cmd == "انزال":
        if not is_admin(message.author):
            await message.channel.send(
                "❌ هذا الأمر للآدمن فقط."
            )
            return

        drop = pending_drop.get(current_guild_id())
        if not drop:
            await message.channel.send(
                "❌ لا يوجد دروب مجهز حاليًا. اطلب من الآدمن تجهيزه أولًا."
            )
            return

        if len(drop["claimed"]) >= drop["max_claims"]:
            await message.channel.send(
                "❌ انتهى الدروب، تم أخذه من أول 3 لاعبين."
            )
            return

        embed = discord.Embed(
            title="📦 إنزال جوي!",
            description=(
                "🚨 تم إسقاط شحنة عسكرية!\n\n"
                "اضغط الزر للحصول على الدروب.\n"
                "🏃 **أول 3 لاعبين فقط يحصلون عليه.**\n\n"
                f"🎁 المحتوى لكل فائز:\n{drop_selection_text(drop['items'])}"
            ),
            color=discord.Color.gold()
        )

        drop_view = DropClaimView()
        drop_message = await message.channel.send(
            embed=embed,
            view=drop_view
        )
        drop_view.message = drop_message
        return

    # =====================================================
    # سعر
    # =====================================================

    if cmd == "سعر":
        if not is_admin(message.author):
            await message.channel.send(
                "❌ هذا الأمر للآدمن فقط."
            )
            return

        embed = discord.Embed(
            title="💰 تعديل أسعار المتجر",
            description=(
                "استخدم الأزرار لتغيير **جميع أسعار المتجر** دفعة واحدة.\n\n"
                "🟢 **رفع:** من `5%` إلى `100%` (بخطوات 5%).\n"
                "🔴 **خفض:** من `5%` إلى `100%` (بخطوات 5%).\n\n"
                "بعد اختيار النسبة سيتم إرسال قائمة عامة في الروم بالأسعار الجديدة."
            ),
            color=discord.Color.gold()
        )

        for item, data in ALL_SHOP_ITEMS.items():
            embed.add_field(
                name=data["label"],
                value=f"`{get_price(item):,}` ذهب",
                inline=True
            )

        await message.channel.send(
            embed=embed,
            view=PriceAdminView(message.author.id)
        )
        return

    # =====================================================
    # تصفير كل
    # =====================================================

    if cmd == "تصفير_كل" or (cmd == "تصفير" and len(tokens) > 1 and tokens[1] == "كل"):
        if not is_admin(message.author):
            await message.channel.send(
                "❌ هذا الأمر للآدمن فقط."
            )
            return

        reset_all_players()

        await message.channel.send(
            "♻️ **تم تصفير جميع اللاعبين بنجاح.**\n"
            "🪙 الذهب: `50,000`\n"
            "🏆 الكؤوس: `1,000`\n"
            "🎖️ الرتبة: `مُجنّد`\n"
            "🎒 جميع الأسلحة: `0`\n"
            "🛡️ جميع الدفاعات: `0`\n"
            "🤝 تم إلغاء جميع التحالفات.\n"
            "📜 تم تصفير سجل الهجمات والتبريدات."
        )
        return

    # =====================================================
    # أي أوامر Discord مستقبلية
    # =====================================================

    await bot.process_commands(
        message
    )


# =========================================================
# تشغيل البوت
# =========================================================

@bot.event
async def on_ready():
    for guild in bot.guilds:
        init_db(guild.id)

    if not random_event_loop.is_running():
        random_event_loop.start()

    print("==========================================")
    print(
        f"🟢 Logged in successfully as {bot.user}"
    )
    print(
        f"🗄️ Databases: {len(bot.guilds)} separate server database(s)"
    )
    print(
        "🚀 Sky Strike Ultimate is online!"
    )
    print("==========================================")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return

    raise error

bot.run(TOKEN)
