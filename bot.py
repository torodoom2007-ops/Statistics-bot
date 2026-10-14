import asyncio
import json
import logging
import os
import random
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatMemberStatus, ChatType, ParseMode
from aiogram.exceptions import (TelegramBadRequest, TelegramForbiddenError,
                                TelegramRetryAfter)
from aiogram.filters import Command, CommandStart
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


# ========================= אחסון =========================
DEFAULT_BASE = {
    "users": 12480, "views": 1840000, "orders": 9320,
    "completed": 9105, "avg_time": 7, "online": 143, "rating": 4.9,
}
D: dict = {}


def load():
    global D
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, encoding="utf-8") as f:
            D = json.load(f)
    D.setdefault("groups", {})
    D.setdefault("mode", "real")           # real | fake
    D.setdefault("interval", 15)
    D.setdefault("base", dict(DEFAULT_BASE))
    D.setdefault("current", dict(D["base"]))
    D.setdefault("live", {})               # chat_id -> message_id
    D["groups"].setdefault(str(MAIN_GROUP_ID), "קבוצה ראשית")
    save()


def save():
    os.makedirs(os.path.dirname(DATA_FILE) or ".", exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(D, f, ensure_ascii=False, indent=2)


# ========================= מנוע סטטיסטיקה =========================
JITTER = {"users": 0.002, "views": 0.004, "orders": 0.002, "completed": 0.002,
          "avg_time": 0.15, "online": 0.08, "rating": 0.008}
BOUNDS = {"users": (0.97, 1.15), "views": (0.97, 1.15), "orders": (0.97, 1.15),
          "completed": (0.97, 1.15), "avg_time": (0.75, 1.3),
          "online": (0.7, 1.3), "rating": (0.985, 1.0)}
UPWARD = {"users", "views", "orders", "completed"}


def tick():
    base, cur = D["base"], D["current"]
    for k, b in base.items():
        if D["mode"] == "real":
            # סביב הערך שהוזן, רנדומלי למעלה ולמטה
            cur[k] = b * (1 + random.uniform(-JITTER[k], JITTER[k]))
        else:
            # הליכה אקראית עדינה עם נטייה לעלייה במדדי צמיחה
            step = b * JITTER[k] * (0.6 if k in UPWARD else 1)
            lo_b, hi_b = BOUNDS[k]
            lo = random.uniform(-0.45, 0.8) if k in UPWARD else random.uniform(-1, 1)
            v = cur.get(k, b) + lo * step
            cur[k] = min(max(v, b * lo_b), b * hi_b)
        if k == "rating":
            cur[k] = min(5.0, cur[k])
    cur["completed"] = min(cur["completed"], cur["orders"])


def n(v) -> str:
    return f"{int(round(v)):,}"


def build_text() -> str:
    c = D["current"]
    now = datetime.now(ZoneInfo(TIMEZONE)).strftime("%H:%M:%S")
    line = "━━━━━━━━━━━━━━━━━━"
    return (
        f"{ce(0)} <b>{BRAND}</b> {ce(1)}\n"
        f"<i>מצב נתונים בזמן אמת</i>\n{line}\n"
        f"{ce(2)} <b>משתמשים רשומים:</b> <code>{n(c['users'])}</code>\n"
        f"{ce(3)} <b>צפיות שנשלחו:</b> <code>{n(c['views'])}</code>\n"
        f"{ce(4)} <b>הזמנות שבוצעו:</b> <code>{n(c['orders'])}</code>\n"
        f"{ce(5)} <b>הושלמו בהצלחה:</b> <code>{n(c['completed'])}</code>\n"
        f"{ce(6)} <b>זמן ביצוע משוער:</b> <code>~{max(1, round(c['avg_time']))}</code> דקות\n"
        f"{ce(7)} <b>מחוברים כעת:</b> <code>{n(c['online'])}</code>\n"
        f"{ce(8)} <b>דירוג שירות:</b> <code>{c['rating']:.1f}</code> / 5\n"
        f"{line}\n"
        f"{ce(9)} <i>עודכן לאחרונה: {now}</i>"
    )


def stats_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 לביצוע הזמנה", url=BOT_LINK)],
        [InlineKeyboardButton(text=f"🌐 {BRAND} | כל הקישורים", url=LINKTREE)],
    ])


# ========================= עדכון חי =========================
async def start_live(bot: Bot, chat_id: int):
    old = D["live"].pop(str(chat_id), None)
    if old:
        try:
            await bot.delete_message(chat_id, old)
        except Exception:
            pass
    tick()
    m = await bot.send_message(chat_id, build_text(), reply_markup=stats_kb())
    D["live"][str(chat_id)] = m.message_id
    save()


async def live_loop(bot: Bot):
    while True:
        await asyncio.sleep(max(5, int(D["interval"])))
        if not D["live"]:
            continue
        tick()
        text = build_text()
        for chat_id, mid in list(D["live"].items()):
            try:
                await bot.edit_message_text(text, chat_id=int(chat_id), message_id=mid,
                                            reply_markup=stats_kb())
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
            except TelegramBadRequest as e:
                if "not modified" in str(e):
                    continue
                logging.warning("live %s removed: %s", chat_id, e)
                D["live"].pop(chat_id, None)
            except TelegramForbiddenError:
                D["live"].pop(chat_id, None)
            except Exception as e:
                logging.error("live error %s: %s", chat_id, e)
            await asyncio.sleep(0.3)
        save()


# ========================= הנתב =========================
router = Router()
IS_ADMIN = F.from_user.id == ADMIN_ID


class Post(StatesGroup):
    waiting_msg = State()
    building = State()
    waiting_button = State()


def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 סטטיסטיקה חיה כאן", callback_data="m:live"),
         InlineKeyboardButton(text="📢 פרסום הודעה", callback_data="m:post")],
        [InlineKeyboardButton(text="👥 קבוצות", callback_data="m:groups"),
         InlineKeyboardButton(text="⚙️ נתונים", callback_data="m:data")],
        [InlineKeyboardButton(text="🔄 החלף מצב אמיתי/מהונדס", callback_data="m:mode")],
    ])


def data_text() -> str:
    b = D["base"]
    mode = "אמיתי (לפי הנתונים שהוזנו)" if D["mode"] == "real" else "מהונדס (תנועה עדינה)"
    return (
        f"<b>⚙️ הגדרות נתונים</b>\n\nמצב: <b>{mode}</b>\n"
        f"מרווח עדכון: <b>{D['interval']}</b> שניות\n\n"
        + "\n".join(f"• <code>{k}</code> = {v}" for k, v in b.items())
        + "\n\n<b>פקודות:</b>\n"
        "<code>/set users 15000</code> – עדכון נתון\n"
        "<code>/mode real</code> או <code>/mode fake</code>\n"
        "<code>/interval 10</code> – שניות בין עדכונים (מינימום 5)\n"
        "<code>/live -100123...</code> – שליחת סטטיסטיקה חיה לקבוצה\n"
        "<code>/stoplive -100123...</code> – עצירה\n"
        "<code>/stats</code> – סטטיסטיקה חיה בצ'אט הנוכחי"
    )


# ---------- התחלה ----------
@router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def start(m: Message, state: FSMContext):
    await state.clear()
    if m.from_user.id == ADMIN_ID:
        await m.answer(f"{ce(0)} <b>פאנל ניהול – {BRAND}</b>\nבחר פעולה:", reply_markup=admin_menu())
    else:
        await m.answer(f"{ce(0)} <b>ברוכים הבאים ל-{BRAND}</b>\nכל המידע והשירותים בקישורים:",
                       reply_markup=stats_kb())


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


@router.callback_query(IS_ADMIN, F.data == "m:live")
async def cb_live(c: CallbackQuery, bot: Bot):
    await start_live(bot, c.message.chat.id)
    await c.answer()


# ---------- פקודות נתונים ----------
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


@router.message(IS_ADMIN, Command("interval"))
async def cmd_interval(m: Message):
    p = (m.text or "").split()
    if len(p) != 2 or not p[1].isdigit():
        return await m.reply("שימוש: <code>/interval 10</code>")
    D["interval"] = max(5, int(p[1]))
    save()
    await m.reply(f"✅ מרווח עדכון: <b>{D['interval']}</b> שניות")


@router.message(IS_ADMIN, Command("stats"))
async def cmd_stats(m: Message, bot: Bot):
    await start_live(bot, m.chat.id)
    if m.chat.type != ChatType.PRIVATE:
        try:
            await m.delete()
        except Exception:
            pass


@router.message(IS_ADMIN, Command("live"))
async def cmd_live(m: Message, bot: Bot):
    p = (m.text or "").split()
    if len(p) != 2 or not re.fullmatch(r"-?\d+", p[1]):
        return await m.reply("שימוש: <code>/live -100123456789</code>")
    try:
        await start_live(bot, int(p[1]))
        await m.reply("✅ נשלח")
    except Exception as e:
        await m.reply(f"❌ {e}")


@router.message(IS_ADMIN, Command("stoplive"))
async def cmd_stoplive(m: Message):
    p = (m.text or "").split()
    target = p[1] if len(p) == 2 else str(m.chat.id)
    D["live"].pop(target, None)
    save()
    await m.reply("⏹ הופסק העדכון החי")


# ---------- ניהול קבוצות ----------
def groups_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"🗑 {name} ({gid})", callback_data=f"gd:{gid}")]
            for gid, name in D["groups"].items()]
    return InlineKeyboardMarkup(inline_keyboard=rows or [[InlineKeyboardButton(text="אין קבוצות", callback_data="x")]])


@router.callback_query(IS_ADMIN, F.data == "m:groups")
async def cb_groups(c: CallbackQuery):
    await c.message.answer(
        "👥 <b>הקבוצות המחוברות</b>\n\nכדי להוסיף קבוצה: קדם את הבוט למנהל בקבוצה, "
        "ואז שלח לכאן את מזהה הקבוצה או הודעה מועברת ממנה.\nלמחיקה לחץ על קבוצה:",
        reply_markup=groups_kb())
    await c.answer()


@router.callback_query(IS_ADMIN, F.data.startswith("gd:"))
async def cb_gdel(c: CallbackQuery):
    D["groups"].pop(c.data[3:], None)
    D["live"].pop(c.data[3:], None)
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
    elif st in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED, ChatMemberStatus.MEMBER):
        if str(u.chat.id) in D["groups"] and st != ChatMemberStatus.MEMBER:
            D["groups"].pop(str(u.chat.id), None)
            D["live"].pop(str(u.chat.id), None)
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


# ---------- פרסום הודעות ----------
@router.callback_query(IS_ADMIN, F.data == "m:post")
async def cb_post(c: CallbackQuery, state: FSMContext):
    await state.clear()
    rows = [[InlineKeyboardButton(text=name, callback_data=f"pg:{gid}")]
            for gid, name in D["groups"].items()]
    rows.append([InlineKeyboardButton(text="📣 כל הקבוצות", callback_data="pg:all")])
    await c.message.answer("📢 <b>לאיזו קבוצה לפרסם?</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await c.answer()


@router.callback_query(IS_ADMIN, F.data.startswith("pg:"))
async def cb_pick(c: CallbackQuery, state: FSMContext):
    await state.set_data({"target": c.data[3:], "rows": []})
    await state.set_state(Post.waiting_msg)
    await c.message.answer("✍️ שלח עכשיו את ההודעה לפרסום (טקסט, תמונה, וידאו ועוד – כולל אימוג'י פרימיום).")
    await c.answer()


def build_markup(rows) -> InlineKeyboardMarkup | None:
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t, url=u) for t, u in row] for row in rows])


async def show_builder(m_or_c, bot: Bot, state: FSMContext):
    d = await state.get_data()
    chat_id = ADMIN_ID
    await bot.copy_message(chat_id, d["src_chat"], d["src_msg"], reply_markup=build_markup(d["rows"]))
    ctrl = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ הוסף כפתור", callback_data="pb:add")],
        [InlineKeyboardButton(text="🧹 נקה כפתורים", callback_data="pb:clear"),
         InlineKeyboardButton(text="❌ ביטול", callback_data="pb:cancel")],
        [InlineKeyboardButton(text="✅ שלח לפרסום", callback_data="pb:send")],
    ])
    await bot.send_message(chat_id, "👆 <b>תצוגה מקדימה.</b> ניתן להוסיף כפתורי אינליין לפני השליחה:", reply_markup=ctrl)
    await state.set_state(Post.building)


@router.message(IS_ADMIN, Post.waiting_msg)
async def got_msg(m: Message, bot: Bot, state: FSMContext):
    await state.update_data(src_chat=m.chat.id, src_msg=m.message_id)
    await show_builder(m, bot, state)


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
    rows = d["rows"]
    added = 0
    for line in m.text.splitlines():
        row = []
        for part in line.split("&&"):
            if "|" not in part:
                continue
            title, url = [x.strip() for x in part.split("|", 1)]
            if not re.match(r"^(https?://|tg://)", url):
                url = "https://" + url
            if title and "." in url or url.startswith("tg://"):
                row.append([title, url])
        if row:
            rows.append(row)
            added += len(row)
    if not added:
        return await m.reply("❌ לא זוהה כפתור תקין. נסה שוב: <code>שם | קישור</code>")
    await state.update_data(rows=rows)
    await show_builder(m, bot, state)


@router.callback_query(IS_ADMIN, Post.building, F.data == "pb:clear")
async def pb_clear(c: CallbackQuery, bot: Bot, state: FSMContext):
    await state.update_data(rows=[])
    await show_builder(c, bot, state)
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
            await bot.copy_message(int(gid), d["src_chat"], d["src_msg"], reply_markup=build_markup(d["rows"]))
            ok += 1
        except Exception as e:
            fail.append(f"{D['groups'].get(gid, gid)}: {e}")
        await asyncio.sleep(0.3)
    await state.clear()
    txt = f"✅ נשלח ל-{ok} קבוצות."
    if fail:
        txt += "\n\n❌ נכשל:\n" + "\n".join(fail)
    await c.message.edit_text(txt)
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

    asyncio.create_task(live_loop(bot))
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=["message", "callback_query", "my_chat_member"])


if __name__ == "__main__":
    asyncio.run(main())
