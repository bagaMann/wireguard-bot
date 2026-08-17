import asyncio
import logging

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, Message

from bot import keyboards as kb

logger = logging.getLogger(__name__)


def _reply_menu(message: Message, app):
    if message.from_user.id in app.settings.admin_ids:
        return kb.admin_reply_menu()
    return kb.user_reply_menu()


def _is_admin(message: Message, app):
    return message.from_user.id in app.settings.admin_ids


def _approved(row):
    return row and row["status"] == "approved"


async def _delete_user_message(message: Message):
    try:
        await message.delete()
    except Exception:
        pass


async def _send_home(message: Message, app):
    await _delete_user_message(message)

    row = app.db.get_user(message.from_user.id)
    menu = _reply_menu(message, app)

    if _is_admin(message, app):
        await message.bot.send_message(
            message.chat.id,
            "👋 Добро пожаловать в BGVmann!\n\n"
            "Выберите нужное действие в меню ниже.",
            reply_markup=menu,
        )
        return

    if _approved(row):
        await message.bot.send_message(
            message.chat.id,
            "👋 Добро пожаловать в WireGuard-бот!\n\n"
            "Выберите нужное действие в меню ниже.",
            reply_markup=menu,
        )
        return

    if row and row["status"] == "blocked":
        await message.bot.send_message(
            message.chat.id,
            "🚫 Доступ заблокирован.",
            reply_markup=menu,
        )
        return

    if row and row["status"] == "pending":
        await message.bot.send_message(
            message.chat.id,
            "⏳ Ваша заявка уже ожидает решения администратора.",
            reply_markup=menu,
        )
        return

    await message.bot.send_message(
        message.chat.id,
        "👋 Добро пожаловать!\n\n"
        "Для получения WireGuard-доступа необходимо зарегистрироваться.",
        reply_markup=kb.registration(),
    )


async def _show_configs(message: Message, app):
    row = app.db.get_user(message.from_user.id)
    menu = _reply_menu(message, app)

    if not _approved(row):
        await message.bot.send_message(
            message.chat.id,
            "❌ Доступ к WireGuard пока не разрешён.",
            reply_markup=menu,
        )
        return

    configs = app.db.active_configs(row["id"])
    if not configs:
        await message.bot.send_message(
            message.chat.id,
            "📱 У вас пока нет активных WireGuard-конфигураций.",
            reply_markup=menu,
        )
        return

    await message.bot.send_message(
        message.chat.id,
        "📱 Ваши WireGuard-конфигурации:\n\n"
        "Выберите QR-код или конфигурацию:",
        reply_markup=kb.user_configs_compact(configs),
    )


async def _create_config(message: Message, app):
    row = app.db.get_user(message.from_user.id)
    menu = _reply_menu(message, app)

    if not _approved(row):
        await message.bot.send_message(
            message.chat.id,
            "❌ Доступ к WireGuard пока не разрешён.",
            reply_markup=menu,
        )
        return

    active = app.db.count_active_configs(row["id"])
    if active >= row["qr_limit"]:
        await message.bot.send_message(
            message.chat.id,
            f"⚠️ Лимит достигнут: {active}/{row['qr_limit']}.\n\n"
            "Чтобы получить новый QR-код, администратор должен увеличить ваш лимит "
            "или удалить одну из существующих конфигураций.",
            reply_markup=menu,
        )
        return

    try:
        config_id, config, qr_path = await app.wireguard.create(
            row["id"],
            message.from_user.id,
        )
        config_row = app.db.get_config(config_id)

        await message.bot.send_photo(
            message.chat.id,
            FSInputFile(qr_path),
            caption=(
                f"✅ WireGuard #{config_id} создан.\n"
                f"Адрес: {config_row['vpn_address']}"
            ),
        )

        conf_path = app.settings.qr_dir / f"{config_id}.conf"
        conf_path.write_text(config, encoding="utf-8")
        conf_path.chmod(0o600)

        await message.bot.send_document(
            message.chat.id,
            FSInputFile(conf_path),
            caption=f"📄 Конфигурация WireGuard #{config_id}",
            reply_markup=menu,
        )

    except Exception as exc:
        logger.exception("WireGuard creation failed")
        await message.bot.send_message(
            message.chat.id,
            f"❌ Не удалось создать конфигурацию: {exc}",
            reply_markup=menu,
        )


async def _show_help(message: Message, app):
    menu = _reply_menu(message, app)
    text = (
        "ℹ️ Помощь\n\n"
        "📱 Мои QR-коды — просмотр активных конфигураций.\n"
        "➕ Получить новый QR — создание дополнительной конфигурации, если доступен лимит.\n\n"
        "QR-код можно отсканировать приложением WireGuard, а файл .conf — импортировать вручную."
    )
    if not _approved(app.db.get_user(message.from_user.id)) and not _is_admin(message, app):
        text = (
            "ℹ️ Помощь\n\n"
            "Для получения WireGuard-доступа сначала отправьте заявку на регистрацию."
        )
    await message.bot.send_message(message.chat.id, text, reply_markup=menu)


async def _show_admin_users(message: Message, app):
    users = app.db.approved_users()
    if not users:
        await message.bot.send_message(
            message.chat.id,
            "👥 Разрешённых пользователей нет.",
            reply_markup=kb.admin_reply_menu(),
        )
        return

    await message.bot.send_message(
        message.chat.id,
        "👥 Пользователи:\n\nВыберите пользователя для просмотра подробной информации.",
        reply_markup=kb.admin_users(users),
    )


async def _show_admin_pending(message: Message, app):
    users = app.db.pending_users()
    if not users:
        await message.bot.send_message(
            message.chat.id,
            "🔔 Новых запросов нет.",
            reply_markup=kb.admin_reply_menu(),
        )
        return

    for user in users:
        await message.bot.send_message(
            message.chat.id,
            _user_text(user),
            reply_markup=kb.admin_request(user["id"]),
        )

    await message.bot.send_message(
        message.chat.id,
        "🔔 Заявки на регистрацию показаны выше.",
        reply_markup=kb.admin_reply_menu(),
    )


def register_menu_handlers(router: Router, app):
    @router.message(CommandStart())
    async def menu_start(message: Message):
        await _send_home(message, app)

    @router.message(Command("admin"))
    async def menu_admin(message: Message):
        if not _is_admin(message, app):
            await message.answer("Нет доступа.", reply_markup=kb.user_reply_menu())
            return
        await _send_home(message, app)

    @router.message(F.text == "📱 Мои QR-коды")
    async def menu_configs(message: Message):
        await _show_configs(message, app)

    @router.message(F.text == "➕ Получить новый QR")
    async def menu_new(message: Message):
        await _create_config(message, app)

    @router.message(F.text == "ℹ️ Помощь")
    async def menu_help(message: Message):
        await _show_help(message, app)

    @router.message(F.text == "👥 Пользователи")
    async def menu_users(message: Message):
        if not _is_admin(message, app):
            return
        await _show_admin_users(message, app)

    @router.message(F.text == "🔔 Запросы")
    async def menu_pending(message: Message):
        if not _is_admin(message, app):
            return
        await _show_admin_pending(message, app)

    @router.callback_query(F.data.startswith("menu:qr:"))
    async def menu_qr(call: CallbackQuery):
        config_id = int(call.data.split(":")[2])
        row = app.db.get_user(call.from_user.id)
        config = app.db.get_config(config_id)
        if not _owns_config(row, config):
            await call.answer("Конфигурация недоступна.", show_alert=True)
            return

        qr_path = app.settings.qr_dir / f"{config_id}.png"
        if not qr_path.exists():
            config_text = app.wireguard.get_config_text(config)
            from bot.wireguard import write_qr
            await asyncio.to_thread(write_qr, config_text, qr_path)

        await call.message.answer_photo(
            FSInputFile(qr_path),
            caption=f"📷 WireGuard #{config_id}",
            reply_markup=_reply_menu(call.message, app),
        )
        await call.answer()

    @router.callback_query(F.data.startswith("menu:conf:"))
    async def menu_conf(call: CallbackQuery):
        config_id = int(call.data.split(":")[2])
        row = app.db.get_user(call.from_user.id)
        config = app.db.get_config(config_id)
        if not _owns_config(row, config):
            await call.answer("Конфигурация недоступна.", show_alert=True)
            return

        config_text = app.wireguard.get_config_text(config)
        path = app.settings.qr_dir / f"{config_id}.conf"
        path.write_text(config_text, encoding="utf-8")
        path.chmod(0o600)

        await call.message.answer_document(
            FSInputFile(path),
            caption=f"📄 WireGuard #{config_id}",
            reply_markup=_reply_menu(call.message, app),
        )
        await call.answer()


def _owns_config(user, config):
    return (
        user
        and config
        and user["status"] == "approved"
        and config["user_id"] == user["id"]
        and config["status"] == "active"
    )


def _user_text(user):
    first_name = (user["first_name"] or "").strip()
    last_name = (user["last_name"] or "").strip()
    full_name = " ".join(x for x in (first_name, last_name) if x)
    username = f"@{user['username']}" if user["username"] else "нет"
    status = {
        "approved": "🟢 Разрешён",
        "pending": "🟡 Ожидает решения",
        "rejected": "🔴 Отклонён",
        "blocked": "🚫 Заблокирован",
    }.get(user["status"], user["status"])
    return (
        "👤 Пользователь\n\n"
        f"Имя: {full_name or 'Без имени'}\n"
        f"Username: {username}\n"
        f"Telegram ID: {user['telegram_id']}\n\n"
        f"Статус: {status}\n"
        f"Лимит QR: {user['qr_limit']}\n"
    )
