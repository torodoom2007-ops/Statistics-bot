import asyncio
import json
import logging
import os
import random
import re
import secrets
import string
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatMemberStatus, ChatType, ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (CallbackQuery, ChatMemberUpdated,
                           InlineKeyboardButton, InlineKeyboardMarkup, Message)

# ========================= משתני סביבה (Render) =========================
BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.getenv("ADMIN_ID", "8017590244"))
MAIN_GROUP_ID = int(os.getenv("MAIN_GROUP_ID", "-1004378924328"))
DATA_FILE = os.getenv("DATA_FILE", "data.json")  # עם Render Disk: /data/data.json
TIMEZONE = os.getenv("TIMEZONE", "Asia/Jerusalem")
PORT = int(os.getenv("PORT", "10000"))
BRAND = os.getenv("BRAND_NAME", "Member Flow")
LINKTREE = os.getenv("LINKTREE_URL", "https://linktr.ee/memberflow")
BOT_LINK = os.getenv("BOT_LINK", "https://t.me/add_sud_bot")
BOT_USERNAME = os.getenv("BOT_USERNAME", "add_sud_bot")
GROUP_COOLDOWN = int(os.getenv("GROUP_COOLDOWN", "30"))   # שניות בין פקודות באותה קבוצה
REFRESH_COOLDOWN = int(os.getenv("REFRESH_COOLDOWN", "8"))

# ========================= אימוג'י פרימיום =========================
PREMIUM_IDS = [
    "5780782082108167841", "6231018663319704664", "6231225487469842472",
    "5269470868379026531", "5271998448042785916", "5461136335173598840",
    "5332724926216428039", "5271604874419647061", "5458745082066780620",
    "5199749070830197566",
]
FALLBACK = ["💠", "✨", "👥", "👁", "📦", "✅", "⏱", "🟢", "⭐", "🕐"]


def ce(i: int) -> str:
    return f'<tg-emoji emoji-id="{PREMIUM_IDS[i]}">{FALLBACK[i]}</tg-emoji>'


LINE = "━━━━━━━━━━━━━━━━━━"

# ========================= אחסון =========================
DEFAULT_BASE = {"users": 12480, "views": 1840000, "orders": 9320,
                "completed": 9105, "avg_time": 7, "online": 143, "rating": 4.9}
DEFAULT_CFG = {"discount": 20, "code": "MEMBERFLOW", "offer_until": 0}
D: dict = {}


def load():
    global D
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, encoding="utf-8") as f:
            D = json.load(f)
    D.setdefault("groups", {})
    D.setdefault("mode", "real")
    D.setdefault("base", dict(DEFAULT_BASE))
    D.setdefault("current", dict(D["base"]))
    D.setdefault("cfg", dict(DEFAULT_CFG))
    for k, v in DEFAULT_CFG.items():
        D["cfg"].setdefault(k, v)
    D.setdefault("texts", {})
    D.setdefault("codes", {})
    for old in ("live", "interval"):
        D.pop(old, None)
    D["groups"].setdefault(str(MAIN_GROUP_ID), "קבוצה ראשית")
    save()


def save():
    os.makedirs(os.path.dirname(DATA_FILE) or ".", exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(D, f, ensure_ascii=False, indent=2)


# ========================= מנוע סטטיסטיקה (רק לפי בקשה) =========================
JITTER = {"users": 0.002, "views": 0.004, "orders": 0.002, "completed": 0.002,
          "avg_time": 0.15, "online": 0.08, "rating": 0.008}
BOUNDS = {"users": (0.97, 1.25), "views": (0.97, 1.25), "orders": (0.97, 1.25),
          "completed": (0.97, 1.25), "avg_time": (0.75, 1.3),
          "online": (0.7, 1.3), "rating": (0.985, 1.0)}
UPWARD = {"users", "views", "orders", "completed"}


def tick():
    now = time.time()
    elapsed = now - D.get("last_tick", now)
    D["last_tick"] = now
    base, cur = D["base"], D["current"]
    if D["mode"] == "real":
        for k, b in base.items():
            cur[k] = b * (1 + random.uniform(-JITTER[k], JITTER[k]))
    else:
        steps = max(1, min(25, int(elapsed // 20)))
        for _ in range(steps):
            for k, b in base.items():
                step = b * JITTER[k] * (0.6 if k in UPWARD else 1)
                drift = random.uniform(-0.45, 0.8) if k in UPWARD else random.uniform(-1, 1)
                lo, hi = BOUNDS[k]
                cur[k] = min(max(cur.get(k, b) + drift * step, b * lo), b * hi)
    cur["rating"] = min(5.0, cur["rating"])
    cur["completed"] = min(cur["completed"], cur["orders"])


def n(v) -> str:
    return f"{int(round(v)):,}"


def now_str() -> str:
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%H:%M:%S")


def stats_text() -> str:
    c = D["current"]
    return (
        f"{ce(0)} <b>{BRAND}</b> {ce(1)}\n<i>מצב נתונים</i>\n{LINE}\n"
        f"{ce(2)} <b>משתמשים רשומים:</b> <code>{n(c['users'])}</code>\n"
        f"{ce(3)} <b>צפיות שנשלחו:</b> <code>{n(c['views'])}</code>\n"
        f"{ce(4)} <b>הזמנות שבוצעו:</b> <code>{n(c['orders'])}</code>\n"
        f"{ce(5)} <b>הושלמו בהצלחה:</b> <code>{n(c['completed'])}</code>\n"
        f"{ce(6)} <b>זמן ביצוע משוער:</b> <code>~{max(1, round(c['avg_time']))}</code> דקות\n"
        f"{ce(7)} <b>מחוברים כעת:</b> <code>{n(c['online'])}</code>\n"
        f"{ce(8)} <b>דירוג שירות:</b> <code>{c['rating']:.1f}</code> / 5\n"
        f"{LINE}\n{ce(9)} <i>עודכן: {now_str()}</i>"
    )


def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 לביצוע הזמנה", url=BOT_LINK)],
        [InlineKeyboardButton(text=f"🌐 {BRAND} | כל הקישורים", url=LINKTREE)],
    ])


def kb_stats() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 רענון", callback_data="st:r")],
        *kb_main().inline_keyboard,
    ])


# ========================= תבניות פרסום =========================
def cfg() -> dict:
    return D["cfg"]


def deadline_line() -> str:
    until = cfg().get("offer_until", 0)
    if until > time.time():
        t = datetime.fromtimestamp(until, ZoneInfo(TIMEZONE)).strftime("%d/%m %H:%M")
        return f"{ce(6)} <b>בתוקף עד:</b> <code>{t}</code>"
    return f"{ce(6)} <b>בתוקף:</b> לזמן מוגבל בלבד"


def txt(key: str, default: str) -> str:
    return D["texts"].get(key, default)


def header(title: str) -> str:
    return f"{ce(0)} <b>{BRAND}</b> {ce(1)}\n<b>{title}</b>\n{LINE}\n"


def t_offer(user=None):
    return (header("הצעה בלעדית להצטרפות") +
            f"{ce(1)} התחילו עוד היום וקבלו <b>{cfg()['discount']}% הנחה</b> על ההזמנה הראשונה\n"
            f"{ce(5)} קוד קופון: <code>{cfg()['code']}</code>\n"
            f"{deadline_line()}\n{LINE}\n"
            f"{ce(7)} לחצו על הכפתור, שלחו את הקוד לבוט ותתחילו ברגע זה."), kb_main()


def t_discount(user=None):
    return (header("הנחה פעילה כרגע") +
            f"{ce(8)} <b>{cfg()['discount']}%</b> הנחה לכל הלקוחות החדשים\n"
            f"{ce(5)} הקוד: <code>{cfg()['code']}</code> (לחיצה להעתקה)\n"
            f"{deadline_line()}"), kb_main()


def make_code() -> str:
    a = string.ascii_uppercase + string.digits
    part = lambda: "".join(secrets.choice(a) for _ in range(4))
    return f"MF-{part()}-{part()}"


def t_join(user=None):
    uid = user.id if user else 0
    existing = next((c for c, v in D["codes"].items() if v["uid"] == uid), None)
    code = existing or make_code()
    if not existing and uid:
        D["codes"][code] = {"uid": uid, "name": user.full_name, "ts": int(time.time()), "used": False}
        save()
    link = f"https://t.me/{BOT_USERNAME}?start={code}"
    text = (header("קוד הצטרפות אישי") +
            f"{ce(2)} הקוד האישי שלך: <code>{code}</code>\n"
            f"{ce(1)} פורמט הקוד: <code>MF-XXXX-XXXX</code>\n{LINE}\n"
            f"{ce(5)} לחצו על הכפתור, הקוד יופעל אוטומטית ותקבלו <b>{cfg()['discount']}% הנחה</b>.\n"
            f"{ce(6)} הקוד אישי וחד פעמי.")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 הפעלת הקוד והצטרפות", url=link)],
        [InlineKeyboardButton(text=f"🌐 {BRAND} | כל הקישורים", url=LINKTREE)]])
    return text, kb


def t_price(user=None):
    body = txt("price", f"{ce(4)} מחירים משתלמים וקבועים, מתחילים מכמה שקלים בלבד.\n"
                        f"{ce(8)} לקוחות חדשים: <b>{cfg()['discount']}% הנחה</b> עם הקוד <code>{cfg()['code']}</code>")
    return header("מחירון") + body, kb_main()


def t_services(user=None):
    body = txt("services", f"{ce(2)} חברים אמיתיים לקבוצות וערוצים\n{ce(3)} צפיות לפוסטים\n"
                           f"{ce(4)} שירותי קידום והזמנות מותאמות\n{ce(7)} תמיכה אישית בכל שלב")
    return header("השירותים שלנו") + body, kb_main()


def t_how(user=None):
    body = txt("how", f"{ce(2)} <b>1.</b> פותחים את הבוט\n{ce(4)} <b>2.</b> בוחרים שירות וכמות\n"
                      f"{ce(8)} <b>3.</b> מזינים קוד הנחה\n{ce(6)} <b>4.</b> ההזמנה יוצאת לדרך תוך דקות\n"
                      f"{ce(5)} <b>5.</b> מקבלים עדכון על השלמה")
    return header("איך זה עובד") + body, kb_main()


def t_faq(user=None):
    body = txt("faq", f"<b>כמה זמן לוקח?</b>\nבדרך כלל כמה דקות.\n\n"
                      f"<b>האם זה בטוח?</b>\nכן, ללא צורך בסיסמאות.\n\n"
                      f"<b>איך מקבלים הנחה?</b>\nקוד <code>{cfg()['code']}</code> בבוט.")
    return header("שאלות נפוצות") + body, kb_main()


def t_reviews(user=None):
    c = D["current"]
    body = txt("reviews", f"{ce(8)} דירוג ממוצע: <b>{c['rating']:.1f}/5</b>\n"
                          f"{ce(5)} מעל <b>{n(c['completed'])}</b> הזמנות הושלמו\n"
                          f"{ce(2)} <b>{n(c['users'])}</b> לקוחות מרוצים")
    return header("מה אומרים הלקוחות") + body, kb_main()


def t_guarantee(user=None):
    body = txt("guarantee", f"{ce(5)} שירות אמין ושקוף\n{ce(6)} ביצוע מהיר\n{ce(7)} תמיכה זמינה לכל שאלה")
    return header("האחריות שלנו") + body, kb_main()


def t_support(user=None):
    return (header("תמיכה") + f"{ce(7)} צריכים עזרה? פנו אלינו דרך הבוט או דרך עמוד הקישורים."), kb_main()


def t_bonus(user=None):
    return (header("בונוס חברים") +
            f"{ce(1)} הזמינו חבר והשתמשו בקוד האישי שלכם (/join)\n"
            f"{ce(8)} על כל הצטרפות דרך הקוד תקבלו הטבה מיוחדת\n{deadline_line()}"), kb_main()


def t_vip(user=None):
    body = txt("vip", f"{ce(8)} מסלול VIP: עדיפות בביצוע, מחירים מיוחדים ותמיכה אישית.")
    return header("מועדון VIP") + body, kb_main()


def t_links(user=None):
    return header("קישורים רשמיים") + f"{ce(0)} כל המידע והשירותים במקום אחד:", kb_main()


def t_status(user=None):
    tick()
    save()
    return stats_text(), kb_stats()


def t_help(user=None):
    return (header("פקודות זמינות") +
            "/offer – הצעה להצטרפות בהנחה\n/discount – ההנחה הפעילה\n/join – קוד הצטרפות אישי\n"
            "/price – מחירון\n/services – השירותים\n/how – איך זה עובד\n/faq – שאלות נפוצות\n"
            "/reviews – חוות דעת\n/guarantee – אחריות\n/bonus – בונוס חברים\n/vip – מועדון VIP\n"
            "/support – תמיכה\n/links – קישורים\n/stats – סטטיסטיקה"), kb_main()


PROMO = {
    "offer": t_offer, "discount": t_discount, "join": t_join, "price": t_price,
    "services": t_services, "how": t_how, "faq": t_faq, "reviews": t_reviews,
    "guarantee": t_guarantee, "bonus": t_bonus, "vip": t_vip, "support": t_support,
    "links": t_links, "stats": t_status, "help": t_help,
}
PROMO_NAMES = {
    "offer": "הצעה", "discount": "הנחה", "join": "קוד הצטרפות", "price": "מחירון",
    "services": "שירותים", "how": "איך זה עובד", "faq": "שאלות נפוצות", "reviews": "חוות דעת",
    "guarantee": "אחריות", "bonus": "בונוס", "vip": "VIP", "support": "תמיכה",
    "links": "קישורים", "stats": "סטטיסטיקה",
}

# ========================= עזרים =========================
router = Router()
IS_ADMIN = F.from_user.id == ADMIN_ID
LAST_USE: dict = {}


async def safe_send(bot: Bot, chat_id: int, text: str, kb=None):
    try:
        return await bot.send_message(chat_id, text, reply_markup=kb)
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after + 1)
        return await bot.send_message(chat_id, text, reply_markup=kb)


def cooled(key, seconds) -> bool:
    now = time.time()
    if now - LAST_USE.get(key, 0) < seconds:
        return False
    LAST_USE[key] = now
    return True


# ========================= פקודות קבוצה/ציבוריות =========================
@router.message(Command(*PROMO.keys()))
async def promo_cmd(m: Message, command: CommandObject, bot: Bot):
    key = command.command.lower()
    is_admin = m.from_user and m.from_user.id == ADMIN_ID
    if m.chat.type != ChatType.PRIVATE:
        if str(m.chat.id) not in D["groups"]:
            return
        if not is_admin and not cooled((m.chat.id, key), GROUP_COOLDOWN):
            return
    text, kb = PROMO[key](m.from_user)
    await safe_send(bot, m.chat.id, text, kb)
    if m.chat.type != ChatType.PRIVATE:
        try:
            await m.delete()
        except Exception:
            pass


# ========================= התחלה + קוד הצטרפות =========================
class Post(StatesGroup):
    waiting_msg = State()
    building = State()
    waiting_button = State()


def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 סטטיסטיקה", callback_data="m:stats"),
         InlineKeyboardButton(text="📢 פרסום חופשי", callback_data="m:post")],
        [InlineKeyboardButton(text="🎯 תבניות פרסום", callback_data="m:tpl"),
         InlineKeyboardButton(text="👥 קבוצות", callback_data="m:groups")],
        [InlineKeyboardButton(text="⚙️ הגדרות ונתונים", callback_data="m:data"),
         InlineKeyboardButton(text="🔄 מצב אמיתי/מהונדס", callback_data="m:mode")],
    ])


@router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def start(m: Message, command: CommandObject, bot: Bot, state: FSMContext):
    await state.clear()
    code = (command.args or "").strip().upper()
    if code and code in D["codes"]:
        entry = D["codes"][code]
        if entry["used"] and entry["uid"] != m.from_user.id:
            return await m.answer("⚠️ הקוד כבר נוצל.")
        first = not entry["used"]
        entry["used"] = True
        save()
        await m.answer(
            header("הקוד הופעל בהצלחה") +
            f"{ce(5)} קיבלת <b>{cfg()['discount']}% הנחה</b>\n"
            f"{ce(1)} קוד הקופון להזנה: <code>{cfg()['code']}</code>\n{LINE}\n"
            "בחר/י את השירות וההזמנה בהתאם.", reply_markup=kb_main())
        if first:
            try:
                await bot.send_message(ADMIN_ID, f"🎟 הקוד <code>{code}</code> הופעל על ידי "
                                                 f"{m.from_user.full_name} (<code>{m.from_user.id}</code>)")
            except Exception:
                pass
        return
    if m.from_user.id == ADMIN_ID:
        await m.answer(f"{ce(0)} <b>פאנל ניהול – {BRAND}</b>\nבחר פעולה:", reply_markup=admin_menu())
    else:
        await m.answer(f"{ce(0)} <b>ברוכים הבאים ל-{BRAND}</b>\nכל המידע והשירותים בקישורים:",
                       reply_markup=kb_main())


# ========================= סטטיסטיקה: רענון רק בלחיצה =========================
@router.callback_query(F.data == "st:r")
async def cb_refresh(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID and not cooled(("r", c.message.chat.id), REFRESH_COOLDOWN):
        return await c.answer("עוד רגע...")
    tick()
    save()
    try:
        await c.message.edit_text(stats_text(), reply_markup=kb_stats())
        await c.answer("עודכן")
    except TelegramRetryAfter as e:
        await c.answer(f"נסו שוב בעוד {e.retry_after} שניות")
    except TelegramBadRequest:
        await c.answer()


@router.callback_query(IS_ADMIN, F.data == "m:stats")
async def cb_stats(c: CallbackQuery, bot: Bot):
    tick()
    save()
    await c.message.answer(stats_text(), reply_markup=kb_stats())
    await c.answer()


# ========================= הגדרות ונתונים =========================
def data_text() -> str:
    b, cf = D["base"], cfg()
    mode = "אמיתי (הערכים שהוזנו + תנודה קלה)" if D["mode"] == "real" else "מהונדס (תנועה עדינה בזמן)"
    until = cf["offer_until"]
    until_s = (datetime.fromtimestamp(until, ZoneInfo(TIMEZONE)).strftime("%d/%m %H:%M")
               if until > time.time() else "לא מוגדר")
    return (
        f"<b>⚙️ הגדרות</b>\n\nמצב סטטיסטיקה: <b>{mode}</b>\n"
        f"הנחה: <b>{cf['discount']}%</b> | קוד: <code>{cf['code']}</code>\nמבצע עד: <b>{until_s}</b>\n\n"
        + "\n".join(f"• <code>{k}</code> = {v}" for k, v in b.items())
        + "\n\n<b>פקודות ניהול:</b>\n"
        "<code>/set users 15000</code> – עדכון נתון\n"
        "<code>/mode real</code> / <code>/mode fake</code>\n"
        "<code>/discount_set 25</code> – אחוז הנחה\n"
        "<code>/code_set SUMMER25</code> – קוד קופון\n"
        "<code>/offer_hours 48</code> – מבצע לעוד X שעות (0 = ביטול)\n"
        "<code>/text price ...</code> – עריכת טקסט (גם רב שורות)\n"
        "<code>/texts</code> – רשימת הטקסטים הניתנים לעריכה\n"
        "<code>/text_reset price</code> – חזרה לברירת מחדל\n"
        "<code>/send_stats -100123...</code> – שליחת סטטיסטיקה לקבוצה\n"
        "<code>/codes</code> – קודי הצטרפות שנוצרו"
    )


@router.callback_query(IS_ADMIN, F.data == "m:data")
async def cb_data(c: CallbackQuery):
    await c.message.answer(data_text())
    await c.answer()


@router.callback_query(IS_ADMIN, F.data == "m:mode")
async def cb_mode(c: CallbackQuery):
    D["mode"] = "fake" if D["mode"] == "real" else "real"
    D["current"] = dict(D["base"])
    save()
    await c.answer(f"מצב: {D['mode']}", show_alert=True)


@router.message(IS_ADMIN, Command("set"))
async def cmd_set(m: Message):
    p = (m.text or "").split()
    if len(p) != 3 or p[1] not in D["base"]:
        return await m.reply("שימוש: <code>/set key value</code>\nמפתחות: " + ", ".join(D["base"]))
    try:
        D["base"][p[1]] = float(p[2]) if p[1] == "rating" else int(float(p[2]))
    except ValueError:
        return await m.reply("ערך לא תקין")
    D["current"] = dict(D["base"])
    save()
    await m.reply(f"✅ <code>{p[1]}</code> עודכן ל-<b>{D['base'][p[1]]}</b>")


@router.message(IS_ADMIN, Command("mode"))
async def cmd_mode(m: Message):
    p = (m.text or "").split()
    if len(p) != 2 or p[1] not in ("real", "fake"):
        return await m.reply("שימוש: <code>/mode real</code> או <code>/mode fake</code>")
    D["mode"] = p[1]
    D["current"] = dict(D["base"])
    save()
    await m.reply(f"✅ מצב: <b>{p[1]}</b>")


@router.message(IS_ADMIN, Command("discount_set"))
async def cmd_discount_set(m: Message, command: CommandObject):
    if not (command.args or "").strip().isdigit():
        return await m.reply("שימוש: <code>/discount_set 25</code>")
    cfg()["discount"] = min(90, int(command.args))
    save()
    await m.reply(f"✅ הנחה: <b>{cfg()['discount']}%</b>")


@router.message(IS_ADMIN, Command("code_set"))
async def cmd_code_set(m: Message, command: CommandObject):
    code = (command.args or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9_\-]{3,24}", code):
        return await m.reply("שימוש: <code>/code_set SUMMER25</code> (אותיות באנגלית ומספרים)")
    cfg()["code"] = code
    save()
    await m.reply(f"✅ קוד קופון: <code>{code}</code>")


@router.message(IS_ADMIN, Command("offer_hours"))
async def cmd_offer_hours(m: Message, command: CommandObject):
    a = (command.args or "").strip()
    if not a.isdigit():
        return await m.reply("שימוש: <code>/offer_hours 48</code>")
    h = int(a)
    cfg()["offer_until"] = int((datetime.now() + timedelta(hours=h)).timestamp()) if h else 0
    save()
    await m.reply("✅ המבצע בוטל" if not h else f"✅ המבצע פעיל לעוד <b>{h}</b> שעות")


TEXT_KEYS = ["price", "services", "how", "faq", "reviews", "guarantee", "vip"]


@router.message(IS_ADMIN, Command("texts"))
async def cmd_texts(m: Message):
    await m.reply("הטקסטים הניתנים לעריכה:\n" + "\n".join(f"• <code>{k}</code>" for k in TEXT_KEYS) +
                  "\n\nשימוש: <code>/text price תוכן ההודעה</code>\nתומך HTML: &lt;b&gt;, &lt;i&gt;, &lt;code&gt; ואימוג'י פרימיום.")


@router.message(IS_ADMIN, Command("text"))
async def cmd_text(m: Message, command: CommandObject):
    parts = (command.args or "").split(None, 1)
    if len(parts) != 2 or parts[0] not in TEXT_KEYS:
        return await m.reply("שימוש: <code>/text price תוכן</code>\nמפתחות: " + ", ".join(TEXT_KEYS))
    D["texts"][parts[0]] = parts[1]
    save()
    await m.reply(f"✅ הטקסט <code>{parts[0]}</code> עודכן. בדיקה: /{parts[0] if parts[0] in PROMO else 'help'}")


@router.message(IS_ADMIN, Command("text_reset"))
async def cmd_text_reset(m: Message, command: CommandObject):
    D["texts"].pop((command.args or "").strip(), None)
    save()
    await m.reply("✅ אופס לברירת מחדל")


@router.message(IS_ADMIN, Command("codes"))
async def cmd_codes(m: Message):
    total, used = len(D["codes"]), sum(1 for v in D["codes"].values() if v["used"])
    await m.reply(f"🎟 קודי הצטרפות שנוצרו: <b>{total}</b>\nהופעלו: <b>{used}</b>")


@router.message(IS_ADMIN, Command("send_stats"))
async def cmd_send_stats(m: Message, command: CommandObject, bot: Bot):
    a = (command.args or "").strip()
    if not re.fullmatch(r"-?\d+", a):
        return await m.reply("שימוש: <code>/send_stats -100123456789</code>")
    tick()
    save()
    try:
        await safe_send(bot, int(a), stats_text(), kb_stats())
        await m.reply("✅ נשלח")
    except Exception as e:
        await m.reply(f"❌ {e}")


# ========================= תבניות פרסום (אדמין) =========================
@router.callback_query(IS_ADMIN, F.data == "m:tpl")
async def cb_tpl(c: CallbackQuery):
    keys = [k for k in PROMO if k not in ("help",)]
    rows, row = [], []
    for k in keys:
        row.append(InlineKeyboardButton(text=PROMO_NAMES.get(k, k), callback_data=f"tp:{k}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    await c.message.answer("🎯 <b>איזו תבנית לפרסם?</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await c.answer()


def targets_kb(prefix: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=name, callback_data=f"{prefix}:{gid}")] for gid, name in D["groups"].items()]
    rows.append([InlineKeyboardButton(text="📣 כל הקבוצות", callback_data=f"{prefix}:all")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(IS_ADMIN, F.data.startswith("tp:"))
async def cb_tpl_pick(c: CallbackQuery):
    key = c.data[3:]
    await c.message.answer(f"📍 <b>לאן לשלוח: {PROMO_NAMES.get(key, key)}?</b>", reply_markup=targets_kb(f"tg:{key}"))
    await c.answer()


@router.callback_query(IS_ADMIN, F.data.startswith("tg:"))
async def cb_tpl_send(c: CallbackQuery, bot: Bot):
    _, key, gid = c.data.split(":", 2)
    targets = list(D["groups"]) if gid == "all" else [gid]
    ok, fail = 0, []
    for g in targets:
        try:
            text, kb = PROMO[key](None)
            await safe_send(bot, int(g), text, kb)
            ok += 1
        except Exception as e:
            fail.append(f"{D['groups'].get(g, g)}: {e}")
        await asyncio.sleep(0.5)
    msg = f"✅ נשלח ל-{ok} קבוצות."
    if fail:
        msg += "\n\n❌ נכשל:\n" + "\n".join(fail)
    await c.message.edit_text(msg)
    await c.answer()


# ========================= ניהול קבוצות =========================
def groups_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"🗑 {name} ({gid})", callback_data=f"gd:{gid}")]
            for gid, name in D["groups"].items()]
    return InlineKeyboardMarkup(inline_keyboard=rows or [[InlineKeyboardButton(text="אין קבוצות", callback_data="x")]])


@router.callback_query(IS_ADMIN, F.data == "m:groups")
async def cb_groups(c: CallbackQuery):
    await c.message.answer(
        "👥 <b>הקבוצות המחוברות</b>\n\nלהוספה: קדם את הבוט למנהל בקבוצה (נרשם אוטומטית), "
        "או שלח לכאן את מזהה הקבוצה / הודעה מועברת ממנה.\nלמחיקה לחץ על קבוצה:",
        reply_markup=groups_kb())
    await c.answer()


@router.callback_query(IS_ADMIN, F.data.startswith("gd:"))
async def cb_gdel(c: CallbackQuery):
    D["groups"].pop(c.data[3:], None)
    save()
    await c.message.edit_reply_markup(reply_markup=groups_kb())
    await c.answer("נמחקה")


async def register_group(bot: Bot, chat_id: int) -> str:
    chat = await bot.get_chat(chat_id)
    me = await bot.get_chat_member(chat_id, bot.id)
    if me.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
        return "⚠️ הבוט אינו מנהל בקבוצה. קדם אותו ונסה שוב."
    D["groups"][str(chat_id)] = chat.title or str(chat_id)
    save()
    return f"✅ הקבוצה <b>{chat.title}</b> נוספה."


@router.my_chat_member()
async def on_my_chat_member(u: ChatMemberUpdated, bot: Bot):
    if u.chat.type == ChatType.PRIVATE:
        return
    st = u.new_chat_member.status
    if st == ChatMemberStatus.ADMINISTRATOR:
        D["groups"][str(u.chat.id)] = u.chat.title or str(u.chat.id)
        save()
        try:
            await bot.send_message(ADMIN_ID, f"✅ הבוט קודם למנהל ב-<b>{u.chat.title}</b> "
                                             f"(<code>{u.chat.id}</code>) ונוסף אוטומטית.")
        except Exception:
            pass
    elif st in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
        D["groups"].pop(str(u.chat.id), None)
        save()


@router.message(IS_ADMIN, F.chat.type == ChatType.PRIVATE, F.text.regexp(r"^-?\d{5,}$"))
async def add_by_id(m: Message, bot: Bot):
    try:
        await m.reply(await register_group(bot, int(m.text)))
    except Exception as e:
        await m.reply(f"❌ לא ניתן להוסיף: {e}")


@router.message(IS_ADMIN, F.chat.type == ChatType.PRIVATE, F.forward_origin.chat.as_("fchat"))
async def add_by_forward(m: Message, bot: Bot, fchat):
    try:
        await m.reply(await register_group(bot, fchat.id))
    except Exception as e:
        await m.reply(f"❌ לא ניתן להוסיף: {e}")


# ========================= פרסום חופשי + כפתורי אינליין =========================
@router.callback_query(IS_ADMIN, F.data == "m:post")
async def cb_post(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.answer("📢 <b>לאיזו קבוצה לפרסם?</b>", reply_markup=targets_kb("pg"))
    await c.answer()


@router.callback_query(IS_ADMIN, F.data.startswith("pg:"))
async def cb_pick(c: CallbackQuery, state: FSMContext):
    await state.set_data({"target": c.data[3:], "rows": []})
    await state.set_state(Post.waiting_msg)
    await c.message.answer("✍️ שלח עכשיו את ההודעה לפרסום (טקסט, תמונה, וידאו ועוד, כולל אימוג'י פרימיום).")
    await c.answer()


def build_markup(rows):
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, url=u) for t, u in row] for row in rows])


async def show_builder(bot: Bot, state: FSMContext):
    d = await state.get_data()
    await bot.copy_message(ADMIN_ID, d["src_chat"], d["src_msg"], reply_markup=build_markup(d["rows"]))
    ctrl = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ הוסף כפתור", callback_data="pb:add")],
        [InlineKeyboardButton(text="🧹 נקה כפתורים", callback_data="pb:clear"),
         InlineKeyboardButton(text="❌ ביטול", callback_data="pb:cancel")],
        [InlineKeyboardButton(text="✅ שלח לפרסום", callback_data="pb:send")],
    ])
    await bot.send_message(ADMIN_ID, "👆 <b>תצוגה מקדימה.</b> ניתן להוסיף כפתורי אינליין לפני השליחה:", reply_markup=ctrl)
    await state.set_state(Post.building)


@router.message(IS_ADMIN, Post.waiting_msg)
async def got_msg(m: Message, bot: Bot, state: FSMContext):
    await state.update_data(src_chat=m.chat.id, src_msg=m.message_id)
    await show_builder(bot, state)


@router.callback_query(IS_ADMIN, Post.building, F.data == "pb:add")
async def pb_add(c: CallbackQuery, state: FSMContext):
    await state.set_state(Post.waiting_button)
    await c.message.answer(
        "➕ <b>הוספת כפתור</b>\nשלח בפורמט:\n<code>שם | קישור</code>\n\n"
        "כמה כפתורים בשורות נפרדות. שני כפתורים באותה שורה:\n"
        "<code>שם1 | קישור1 && שם2 | קישור2</code>")
    await c.answer()


@router.message(IS_ADMIN, Post.waiting_button, F.text)
async def pb_got(m: Message, bot: Bot, state: FSMContext):
    d = await state.get_data()
    rows, added = d["rows"], 0
    for line in m.text.splitlines():
        row = []
        for part in line.split("&&"):
            if "|" not in part:
                continue
            title, url = [x.strip() for x in part.split("|", 1)]
            if not re.match(r"^(https?://|tg://)", url):
                url = "https://" + url
            if title and ("." in url or url.startswith("tg://")):
                row.append([title, url])
        if row:
            rows.append(row)
            added += len(row)
    if not added:
        return await m.reply("❌ לא זוהה כפתור תקין. נסה שוב: <code>שם | קישור</code>")
    await state.update_data(rows=rows)
    await show_builder(bot, state)


@router.callback_query(IS_ADMIN, Post.building, F.data == "pb:clear")
async def pb_clear(c: CallbackQuery, bot: Bot, state: FSMContext):
    await state.update_data(rows=[])
    await show_builder(bot, state)
    await c.answer("נוקה")


@router.callback_query(IS_ADMIN, F.data == "pb:cancel")
async def pb_cancel(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.edit_text("❌ בוטל.")
    await c.answer()


@router.callback_query(IS_ADMIN, Post.building, F.data == "pb:send")
async def pb_send(c: CallbackQuery, bot: Bot, state: FSMContext):
    d = await state.get_data()
    targets = list(D["groups"]) if d["target"] == "all" else [d["target"]]
    ok, fail = 0, []
    for gid in targets:
        try:
            try:
                await bot.copy_message(int(gid), d["src_chat"], d["src_msg"], reply_markup=build_markup(d["rows"]))
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
                await bot.copy_message(int(gid), d["src_chat"], d["src_msg"], reply_markup=build_markup(d["rows"]))
            ok += 1
        except Exception as e:
            fail.append(f"{D['groups'].get(gid, gid)}: {e}")
        await asyncio.sleep(0.5)
    await state.clear()
    msg = f"✅ נשלח ל-{ok} קבוצות."
    if fail:
        msg += "\n\n❌ נכשל:\n" + "\n".join(fail)
    await c.message.edit_text(msg)
    await c.answer()


# ========================= הרצה =========================
async def health(_):
    return web.Response(text="ok")


async def main():
    logging.basicConfig(level=logging.INFO)
    load()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)

    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=["message", "callback_query", "my_chat_member"])


if __name__ == "__main__":
    asyncio.run(main())
