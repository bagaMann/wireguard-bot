import asyncio
import logging

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, Message

from bot import keyboards as kb

logger = logging.getLogger(__name__)

# Сообщения текущего экрана меню. Они удаляются при выборе другого пункта.
# QR-коды и .conf сюда не попадают и поэтому остаются в чате.
_menu_message_ids: dict[int, set[int]] = {}

# Отдельно храним сообщение-якорь, которое несёт ReplyKeyboard.
# Его НЕЛЬЗЯ удалять при обычной навигации: иначе Telegram-клиент может
# убрать постоянную клавиатуру.
_keyboard_anchor_ids: dict[int, int] = {}


def _reply_menu_for_user(user_id: int, app):
    if user_id in app.settings.admin_ids:
        return kb.admin_reply_menu()
    return kb.user_reply_menu()


def _reply_menu(message: Message, app):
    return _reply_menu_for_user(message.from_user.id, app)


def _is_admin(message: Message, app):
    return message.from_user.id in app.settings.admin_ids


def _approved(row):
    return row and row["status"] == "approved"


async def _delete_user_message(message: Message):
    try:
        await message.delete()
    except Exception:
        pass


async def _clear_menu_messages(bot, chat_id: int):
    """Удалить только сменяемый экран меню, не трогая ReplyKeyboard-якорь."""
    message_ids = _menu_message_ids.pop(chat_id, set())
    for message_id in message_ids:
        try:
            await bot.delete_message(chat_id, message_id)
        except Exception:
            pass


async def _prepare_menu_screen(message: Message, app):
    """Удалить предыдущий экран меню и сообщение нажатой ReplyKeyboard-кнопки."""
    await _clear_menu_messages(message.bot, message.chat.id)
    await _delete_user_message(message)


async def _send_screen(message: Message, text: str, reply_markup=None):
    """Отправить сменяемый экран меню и запомнить его ID."""
    sent = await message.bot.send_message(
        message.chat.id,
        text,
        reply_markup=reply_markup,
    )
    _menu_message_ids.setdefault(message.chat.id, set()).add(sent.message_id)
    return sent


async def _replace_keyboard_anchor(message: Message, app, text: str):
    """Создать новое постоянное ReplyKeyboard-сообщение и удалить старый якорь."""
    chat_id = message.chat.id
    old_id = _keyboard_anchor_ids.get(chat_id)

    # Сначала отправляем новый якорь. Так ReplyKeyboard уже установлена,
    # прежде чем будет удалено старое сообщение.
    sent = await message.bot.send_message(
        chat_id,
        text,
        reply_markup=_reply_menu(message, app),
    )
    _keyboard_anchor_ids[chat_id] = sent.message_id

    if old_id and old_id != sent.message_id:
        try:
            await message.bot.delete_message(chat_id, old_id)
        except Exception:
            pass

    return sent


async def _send_home(message: Message, app):
    await _clear_menu_messages(message.bot, message.chat.id)
    await _delete_user_message(message)

    row = app.db.get_user(message.from_user.id)

    if _is_admin(message, app):
        await _replace_keyboard_anchor(
            message,
            app,
            "👋 Добро пожаловать в BGVmann!\n\n"
            "Выберите нужное действие в меню ниже.",
        )
        return

    if _approved(row):
        await _replace_keyboard_anchor(
            message,
            app,
            "👋 Добро пожаловать в WireGuard-бот!\n\n"
            "Выберите нужное действие в меню ниже.",
        )
        return

    if row and row["status"] == "blocked":
        await _send_screen(
            message,
            "🚫 Доступ заблокирован.",
        )
        return

    if row and row["status"] == "pending":
        await _send_screen(
            message,
            "⏳ Ваша заявка уже ожидает решения администратора.",
        )
        return

    await _send_screen(
        message,
        "👋 Добро пожаловать!\n\n"
        "Для получения WireGuard-доступа необходимо зарегистрироваться.",
        kb.registration(),
    )


async def _show_configs(message: Message, app):
    await _prepare_menu_screen(message, app)

    row = app.db.get_user(message.from_user.id)
    if not _approved(row):
        await _send_screen(
            message,
            "❌ Доступ к WireGuard пока не разрешён.",
        )
        return

    configs = app.db.active_configs(row["id"])
    if not configs:
        await _send_screen(
            message,
            "📱 У вас пока нет активных WireGuard-конфигураций.",
        )
        return

    await _send_screen(
        message,
        "📱 Ваши WireGuard-конфигурации:\n\n"
        "Выберите QR-код или конфигурацию:",
        kb.user_configs_compact(configs),
    )


async def _create_config(message: Message, app):
    await _prepare_menu_screen(message, app)

    row = app.db.get_user(message.from_user.id)

    if not _approved(row):
        await _send_screen(
            message,
            "❌ Доступ к WireGuard пока не разрешён.",
        )
        return

    active = app.db.count_active_configs(row["id"])
    if active >= row["qr_limit"]:
        await _send_screen(
            message,
            f"⚠️ Лимит достигнут: {active}/{row['qr_limit']}.\n\n"
            "Чтобы получить новый QR-код, администратор должен увеличить ваш лимит "
            "или удалить одну из существующих конфигураций.",
        )
        return

    try:
        config_id, config, qr_path = await app.wireguard.create(
            row["id"],
            message.from_user.id,
        )
        config_row = app.db.get_config(config_id)

        # QR и .conf — доставка, а не экран меню. Они остаются в истории.
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
        )

    except Exception as exc:
        logger.exception("WireGuard creation failed")
        await _send_screen(
            message,
            f"❌ Не удалось создать конфигурацию: {exc}",
        )


async def _show_help(message: Message, app):
    await _prepare_menu_screen(message, app)

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

    await _send_screen(message, text)


async def _show_admin_users(message: Message, app):
    await _prepare_menu_screen(message, app)

    users = app.db.approved_users()
    if not users:
        await _send_screen(
            message,
            "👥 Разрешённых пользователей нет.",
        )
        return

    await _send_screen(
        message,
        "👥 Пользователи:\n\n"
        "Выберите пользователя для просмотра подробной информации.",
        kb.admin_users(users),
    )


async def _show_admin_pending(message: Message, app):
    await _prepare_menu_screen(message, app)

    users = app.db.pending_users()
    if not users:
        await _send_screen(
            message,
            "🔔 Новых запросов нет.",
        )
        return

    for user in users:
        await _send_screen(
            message,
            _user_text(user),
            kb.admin_request(user["id"]),
        )

    await _send_screen(
        message,
        "🔔 Заявки на регистрацию показаны выше.",
    )


def register_menu_handlers(router: Router, app):
    @router.message(CommandStart())
    async def menu_start(message: Message):
        await _send_home(message, app)

    @router.message(Command("admin"))
    async def menu_admin(message: Message):
        if not _is_admin(message, app):
            await _delete_user_message(message)
            await _send_screen(message, "Нет доступа.")
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
            await _delete_user_message(message)
            return
        await _show_admin_users(message, app)

    @router.message(F.text == "🔔 Запросы")
    async def menu_pending(message: Message):
        if not _is_admin(message, app):
            await _delete_user_message(message)
            return
        await _show_admin_pending(message, app)

    @router.callback_query(F.data.startswith("admin:approve:"))
    async def menu_admin_approve(call: CallbackQuery):
        if call.from_user.id not in app.settings.admin_ids:
            return

        user_id = int(call.data.split(":")[2])
        user = app.db.get_user_by_id(user_id)
        if not user:
            await call.answer("Пользователь не найден.", show_alert=True)
            return

        if user["status"] == "approved":
            await call.answer("Пользователь уже разрешён.", show_alert=True)
            return

        app.db.approve_user(
            user_id,
            call.from_user.id,
            app.settings.default_qr_limit,
        )
        user = app.db.get_user_by_id(user_id)

        try:
            await call.message.edit_text(_user_text(user) + "\n\n✅ Разрешён.")
        except Exception:
            pass

        sent = await app.bot.send_message(
            user["telegram_id"],
            "✅ Ваша регистрация подтверждена.\n\n"
            "Теперь вы можете получать WireGuard-конфигурации.",
            reply_markup=_reply_menu_for_user(user["telegram_id"], app),
        )
        _keyboard_anchor_ids[user["telegram_id"]] = sent.message_id
        await call.answer("Пользователь разрешён.")

    @router.callback_query(F.data.startswith("admin:reject:"))
    async def menu_admin_reject(call: CallbackQuery):
        if call.from_user.id not in app.settings.admin_ids:
            return

        user_id = int(call.data.split(":")[2])
        user = app.db.get_user_by_id(user_id)
        if not user:
            await call.answer("Пользователь не найден.", show_alert=True)
            return

        if user["status"] != "pending":
            await call.answer("Заявка уже обработана.", show_alert=True)
            return

        app.db.reject_user(user_id, call.from_user.id)
        user = app.db.get_user_by_id(user_id)

        try:
            await call.message.edit_text(_user_text(user) + "\n\n❌ Отклонён.")
        except Exception:
            pass

        await app.bot.send_message(
            user["telegram_id"],
            "❌ Ваша заявка на регистрацию отклонена.",
        )
        await call.answer("Отклонено.")

    @router.callback_query(F.data.startswith("menu:qr:"))
    async def menu_qr(call: CallbackQuery):
        config_id = int(call.data.split(":")[2])
        row = app.db.get_user(call.from_user.id)
        config = app.db.get_config(config_id)
        if not _owns_config(row, config):
            await call.answer("Конфигурация недоступна.", show_alert=True)
            return

        await _clear_menu_messages(call.bot, call.message.chat.id)

        qr_path = app.settings.qr_dir / f"{config_id}.png"
        if not qr_path.exists():
            config_text = app.wireguard.get_config_text(config)
            from bot.wireguard import write_qr
            await asyncio.to_thread(write_qr, config_text, qr_path)

        await call.message.answer_photo(
            FSInputFile(qr_path),
            caption=f"📷 WireGuard #{config_id}",
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

        await _clear_menu_messages(call.bot, call.message.chat.id)

        config_text = app.wireguard.get_config_text(config)
        path = app.settings.qr_dir / f"{config_id}.conf"
        path.write_text(config_text, encoding="utf-8")
        path.chmod(0o600)

        await call.message.answer_document(
            FSInputFile(path),
            caption=f"📄 WireGuard #{config_id}",
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
