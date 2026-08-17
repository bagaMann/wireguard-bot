import asyncio
import logging

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    FSInputFile,
)

from bot import keyboards as kb


logger = logging.getLogger(__name__)


async def safe_edit(
    message,
    text: str,
    reply_markup=None,
):
    """
    Безопасное редактирование сообщения.

    Telegram возвращает 'message is not modified',
    если текст и клавиатура полностью совпадают.
    Для нас это не ошибка.
    """
    try:
        await message.edit_text(
            text,
            reply_markup=reply_markup,
        )
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return

        raise


def register_handlers(
    router: Router,
    app,
):
    @router.message(CommandStart())
    async def start(message: Message):
        await show_user_start(
            message,
            app,
        )

    @router.message(Command("admin"))
    async def admin(message: Message):
        if (
            message.from_user.id
            not in app.settings.admin_ids
        ):
            await message.answer(
                "Нет доступа."
            )
            return

        await message.answer(
            "🔐 Администрирование",
            reply_markup=kb.admin_menu(),
        )

    # --------------------------------------------------
    # REGISTRATION
    # --------------------------------------------------

    @router.callback_query(
        F.data == "reg:request"
    )
    async def registration_request(
        call: CallbackQuery,
    ):
        user = call.from_user

        user_id = app.db.upsert_pending_user(
            user.id,
            user.username,
            user.first_name,
            user.last_name,
        )

        row = app.db.get_user(
            user.id
        )

        if row["status"] == "approved":
            await call.answer(
                "Вы уже зарегистрированы.",
                show_alert=True,
            )
            return

        if row["status"] == "pending":
            await call.answer(
                "Заявка уже отправлена.",
                show_alert=True,
            )
            return

        await safe_edit(
            call.message,
            (
                "Запрос на регистрацию "
                "отправлен администратору.\n\n"
                "Ожидайте подтверждения."
            ),
        )

        text = (
            "📨 Новый запрос на регистрацию\n\n"
            f"👤 {_user_identity(user)}\n"
            f"Telegram ID: {user.id}\n"
        )

        for admin_id in app.settings.admin_ids:
            await app.bot.send_message(
                admin_id,
                text,
                reply_markup=kb.admin_request(
                    user_id
                ),
            )

        await call.answer()

    # --------------------------------------------------
    # USER
    # --------------------------------------------------

    @router.callback_query(
        F.data == "user:main"
    )
    async def user_main(
        call: CallbackQuery,
    ):
        await safe_edit(
            call.message,
            "Главное меню WireGuard.",
            reply_markup=kb.user_main(),
        )

        await call.answer()

    @router.callback_query(
        F.data == "user:configs"
    )
    async def user_configs(
        call: CallbackQuery,
    ):
        row = app.db.get_user(
            call.from_user.id
        )

        if not _approved(row):
            await call.answer(
                "Доступ не разрешён.",
                show_alert=True,
            )
            return

        configs = app.db.active_configs(
            row["id"]
        )

        if not configs:
            await safe_edit(
                call.message,
                (
                    "У вас пока нет активных "
                    "WireGuard-конфигураций."
                ),
                reply_markup=kb.user_main(),
            )
        else:
            await safe_edit(
                call.message,
                "Ваши WireGuard-конфигурации:",
                reply_markup=kb.user_configs(
                    configs
                ),
            )

        await call.answer()

    @router.callback_query(
        F.data == "user:new"
    )
    async def user_new(
        call: CallbackQuery,
    ):
        row = app.db.get_user(
            call.from_user.id
        )

        if not _approved(row):
            await call.answer(
                "Доступ не разрешён.",
                show_alert=True,
            )
            return

        active = app.db.count_active_configs(
            row["id"]
        )

        if active >= row["qr_limit"]:
            await call.answer(
                (
                    "Лимит достигнут: "
                    f"{active}/{row['qr_limit']}."
                ),
                show_alert=True,
            )
            return

        await call.answer(
            "Создаю WireGuard-конфигурацию..."
        )

        try:
            (
                config_id,
                config,
                qr_path,
            ) = await app.wireguard.create(
                row["id"],
                call.from_user.id,
            )

            config_row = app.db.get_config(
                config_id
            )

            await call.message.answer_photo(
                FSInputFile(qr_path),
                caption=(
                    f"✅ WireGuard "
                    f"#{config_id} создан.\n"
                    f"Адрес: "
                    f"{config_row['vpn_address']}"
                ),
            )

            conf_path = _write_temp_conf(
                app,
                config_id,
                config,
            )

            await call.message.answer_document(
                document=FSInputFile(
                    conf_path
                ),
                caption=(
                    "📄 Конфигурация "
                    f"WireGuard #{config_id}"
                ),
            )

        except Exception as exc:
            logger.exception(
                "WireGuard creation failed"
            )

            await call.message.answer(
                "❌ Не удалось создать "
                f"конфигурацию: {exc}"
            )

    @router.callback_query(
        F.data.startswith("user:show:")
    )
    async def user_show(
        call: CallbackQuery,
    ):
        config_id = int(
            call.data.split(":")[2]
        )

        row = app.db.get_user(
            call.from_user.id
        )

        config = app.db.get_config(
            config_id
        )

        if not _owns_config(
            row,
            config,
        ):
            await call.answer(
                "Конфигурация недоступна.",
                show_alert=True,
            )
            return

        await safe_edit(
            call.message,
            (
                f"WireGuard #{config_id}\n\n"
                f"Имя: {config['name']}\n"
                f"Адрес: {config['vpn_address']}\n"
                f"Создан: {config['created_at']}"
            ),
            reply_markup=kb.config_actions(
                config_id
            ),
        )

        await call.answer()

    @router.callback_query(
        F.data.startswith("user:qr:")
    )
    async def user_qr(
        call: CallbackQuery,
    ):
        config_id = int(
            call.data.split(":")[2]
        )

        row = app.db.get_user(
            call.from_user.id
        )

        config = app.db.get_config(
            config_id
        )

        if not _owns_config(
            row,
            config,
        ):
            await call.answer(
                "Конфигурация недоступна.",
                show_alert=True,
            )
            return

        qr_path = (
            app.settings.qr_dir
            / f"{config_id}.png"
        )

        if not qr_path.exists():
            config_text = (
                app.wireguard.get_config_text(
                    config
                )
            )

            from bot.wireguard import write_qr

            await asyncio.to_thread(
                write_qr,
                config_text,
                qr_path,
            )

        await call.message.answer_photo(
            FSInputFile(qr_path),
            caption=(
                f"📷 WireGuard #{config_id}"
            ),
        )

        await call.answer()

    @router.callback_query(
        F.data.startswith("user:conf:")
    )
    async def user_conf(
        call: CallbackQuery,
    ):
        config_id = int(
            call.data.split(":")[2]
        )

        row = app.db.get_user(
            call.from_user.id
        )

        config = app.db.get_config(
            config_id
        )

        if not _owns_config(
            row,
            config,
        ):
            await call.answer(
                "Конфигурация недоступна.",
                show_alert=True,
            )
            return

        config_text = (
            app.wireguard.get_config_text(
                config
            )
        )

        path = _write_temp_conf(
            app,
            config_id,
            config_text,
        )

        await call.message.answer_document(
            FSInputFile(path),
            caption=(
                f"📄 WireGuard #{config_id}"
            ),
        )

        await call.answer()

    # --------------------------------------------------
    # ADMIN
    # --------------------------------------------------

    @router.callback_query(
        F.data == "admin:menu"
    )
    async def admin_menu(
        call: CallbackQuery,
    ):
        if not _is_admin(
            call,
            app,
        ):
            return

        await safe_edit(
            call.message,
            "🔐 Администрирование",
            reply_markup=kb.admin_menu(),
        )

        await call.answer()

    @router.callback_query(
        F.data.startswith("admin:user:")
    )
    async def admin_user(
        call: CallbackQuery,
    ):
        if not _is_admin(
            call,
            app,
        ):
            return

        user_id = int(
            call.data.split(":")[2]
        )

        user = app.db.get_user_by_id(
            user_id
        )

        if not user:
            await call.answer(
                "Пользователь не найден.",
                show_alert=True,
            )
            return

        await safe_edit(
            call.message,
            _user_text(user),
            reply_markup=kb.admin_user(
                user_id
            ),
        )

        await call.answer()

    @router.callback_query(
        F.data == "admin:pending"
    )
    async def admin_pending(
        call: CallbackQuery,
    ):
        if not _is_admin(
            call,
            app,
        ):
            return

        users = app.db.pending_users()

        if not users:
            await safe_edit(
                call.message,
                "📨 Новых запросов нет.",
                reply_markup=kb.admin_menu(),
            )
        else:
            for user in users:
                await call.message.answer(
                    _user_text(user),
                    reply_markup=kb.admin_request(
                        user["id"]
                    ),
                )

            await safe_edit(
                call.message,
                (
                    "📨 Заявки на регистрацию "
                    "отправлены выше."
                ),
                reply_markup=kb.admin_menu(),
            )

        await call.answer()

    @router.callback_query(
        F.data.startswith("admin:approve:")
    )
    async def admin_approve(
        call: CallbackQuery,
    ):
        if not _is_admin(
            call,
            app,
        ):
            return

        user_id = int(
            call.data.split(":")[2]
        )

        user = app.db.get_user_by_id(
            user_id
        )

        if not user:
            await call.answer(
                "Пользователь не найден.",
                show_alert=True,
            )
            return

        if user["status"] == "approved":
            await call.answer(
                "Пользователь уже разрешён.",
                show_alert=True,
            )
            return

        app.db.approve_user(
            user_id,
            call.from_user.id,
            app.settings.default_qr_limit,
        )

        user = app.db.get_user_by_id(
            user_id
        )

        await safe_edit(
            call.message,
            _user_text(user)
            + (
                "\n\n✅ Разрешён."
            ),
        )

        await app.bot.send_message(
            user["telegram_id"],
            (
                "✅ Ваша регистрация "
                "подтверждена.\n\n"
                "Теперь вы можете получать "
                "WireGuard-конфигурации."
            ),
            reply_markup=kb.user_main(),
        )

        await call.answer(
            "Пользователь разрешён."
        )

    @router.callback_query(
        F.data.startswith("admin:reject:")
    )
    async def admin_reject(
        call: CallbackQuery,
    ):
        if not _is_admin(
            call,
            app,
        ):
            return

        user_id = int(
            call.data.split(":")[2]
        )

        user = app.db.get_user_by_id(
            user_id
        )

        if not user:
            await call.answer(
                "Пользователь не найден.",
                show_alert=True,
            )
            return

        if user["status"] != "pending":
            await call.answer(
                "Заявка уже обработана.",
                show_alert=True,
            )
            return

        app.db.reject_user(
            user_id,
            call.from_user.id,
        )

        user = app.db.get_user_by_id(
            user_id
        )

        await safe_edit(
            call.message,
            _user_text(user)
            + "\n\n❌ Отклонён.",
        )

        await app.bot.send_message(
            user["telegram_id"],
            (
                "❌ Ваша заявка на "
                "регистрацию отклонена."
            ),
        )

        await call.answer(
            "Отклонено."
        )

    @router.callback_query(
        F.data == "admin:users"
    )
    async def admin_users(
        call: CallbackQuery,
    ):
        if not _is_admin(
            call,
            app,
        ):
            return

        users = app.db.approved_users()

        if not users:
            text = (
                "👥 Разрешённых "
                "пользователей нет."
            )
        else:
            text = (
                "👥 Пользователи:\n\n"
                + "\n".join(
                    (
                        f"🟢 {_user_identity_row(u)}\n"
                        f"   QR: "
                        f"{app.db.count_active_configs(u['id'])}"
                        f"/{u['qr_limit']}"
                    )
                    for u in users
                )
            )

        await safe_edit(
            call.message,
            text,
            reply_markup=(
                kb.admin_users(users)
                if users
                else kb.admin_menu()
            ),
        )

        await call.answer()

    @router.callback_query(
        F.data.startswith("admin:limitup:")
    )
    async def admin_limit_up(
        call: CallbackQuery,
    ):
        if not _is_admin(
            call,
            app,
        ):
            return

        user_id = int(
            call.data.split(":")[2]
        )

        user = app.db.get_user_by_id(
            user_id
        )

        if not user:
            await call.answer(
                "Пользователь не найден.",
                show_alert=True,
            )
            return

        app.db.set_qr_limit(
            user_id,
            user["qr_limit"] + 1,
        )

        user = app.db.get_user_by_id(
            user_id
        )

        await safe_edit(
            call.message,
            _user_text(user),
            reply_markup=kb.admin_user(
                user_id
            ),
        )

        await call.answer(
            "Лимит увеличен."
        )

    @router.callback_query(
        F.data.startswith("admin:limitdown:")
    )
    async def admin_limit_down(
        call: CallbackQuery,
    ):
        if not _is_admin(
            call,
            app,
        ):
            return

        user_id = int(
            call.data.split(":")[2]
        )

        user = app.db.get_user_by_id(
            user_id
        )

        if not user:
            await call.answer(
                "Пользователь не найден.",
                show_alert=True,
            )
            return

        active = (
            app.db.count_active_configs(
                user_id
            )
        )

        new_limit = max(
            active,
            user["qr_limit"] - 1,
        )

        app.db.set_qr_limit(
            user_id,
            new_limit,
        )

        user = app.db.get_user_by_id(
            user_id
        )

        await safe_edit(
            call.message,
            _user_text(user),
            reply_markup=kb.admin_user(
                user_id
            ),
        )

        await call.answer(
            "Лимит уменьшен."
        )

    @router.callback_query(
        F.data.startswith("admin:configs:")
    )
    async def admin_configs(
        call: CallbackQuery,
    ):
        if not _is_admin(
            call,
            app,
        ):
            return

        user_id = int(
            call.data.split(":")[2]
        )

        configs = app.db.active_configs(
            user_id
        )

        if not configs:
            await safe_edit(
                call.message,
                "Активных конфигураций нет.",
                reply_markup=kb.admin_user(
                    user_id
                ),
            )
        else:
            await safe_edit(
                call.message,
                (
                    "📱 Активные "
                    "WireGuard-конфигурации:\n\n"
                    "Нажмите на конфигурацию, "
                    "чтобы удалить её."
                ),
                reply_markup=kb.admin_configs(
                    configs
                ),
            )

        await call.answer()

    @router.callback_query(
        F.data.startswith("admin:delcfg:")
    )
    async def admin_delete_config(
        call: CallbackQuery,
    ):
        if not _is_admin(
            call,
            app,
        ):
            return

        config_id = int(
            call.data.split(":")[2]
        )

        config = app.db.get_config(
            config_id
        )

        if (
            not config
            or config["status"] != "active"
        ):
            await call.answer(
                "Конфигурация уже удалена.",
                show_alert=True,
            )
            return

        user = app.db.get_user_by_id(
            config["user_id"]
        )

        try:
            await app.routeros.remove_peer(
                config["routeros_peer_id"]
            )

            app.db.mark_config_deleted(
                config_id,
                call.from_user.id,
            )

            qr_path = (
                app.settings.qr_dir
                / f"{config_id}.png"
            )

            qr_path.unlink(
                missing_ok=True
            )

            conf_path = (
                app.settings.qr_dir
                / f"{config_id}.conf"
            )

            conf_path.unlink(
                missing_ok=True
            )

            configs = app.db.active_configs(
                config["user_id"]
            )

            if configs:
                await safe_edit(
                    call.message,
                    (
                        "🗑 Конфигурация "
                        f"WireGuard #{config_id} "
                        "удалена.\n\n"
                        "Оставшиеся конфигурации:"
                    ),
                    reply_markup=kb.admin_configs(
                        configs
                    ),
                )
            else:
                await safe_edit(
                    call.message,
                    (
                        "🗑 Конфигурация "
                        f"WireGuard #{config_id} "
                        "удалена.\n\n"
                        "Активных QR-кодов больше нет."
                    ),
                    reply_markup=kb.admin_user(
                        config["user_id"]
                    ),
                )

            if user:
                await app.bot.send_message(
                    user["telegram_id"],
                    (
                        f"🗑 WireGuard #{config_id} "
                        "был удалён администратором.\n\n"
                        "Одно место в вашем лимите "
                        "снова доступно."
                    ),
                )

        except Exception as exc:
            logger.exception(
                "Delete failed"
            )

            await call.answer(
                f"Ошибка: {exc}",
                show_alert=True,
            )
            return

        await call.answer(
            "Удалено."
        )

    @router.callback_query(
        F.data.startswith("admin:block:")
    )
    async def admin_block(
        call: CallbackQuery,
    ):
        if not _is_admin(
            call,
            app,
        ):
            return

        user_id = int(
            call.data.split(":")[2]
        )

        user = app.db.get_user_by_id(
            user_id
        )

        if not user:
            await call.answer(
                "Пользователь не найден.",
                show_alert=True,
            )
            return

        app.db.set_status(
            user_id,
            "blocked",
        )

        user = app.db.get_user_by_id(
            user_id
        )

        await safe_edit(
            call.message,
            _user_text(user)
            + "\n\n🚫 Заблокирован.",
            reply_markup=kb.admin_user(
                user_id
            ),
        )

        await call.answer(
            "Пользователь заблокирован."
        )


async def show_user_start(
    message: Message,
    app,
):
    row = app.db.get_user(
        message.from_user.id
    )

    # Администратор сразу получает
    # админское меню.
    if (
        message.from_user.id
        in app.settings.admin_ids
    ):
        await message.answer(
            "🔐 Администрирование",
            reply_markup=kb.admin_menu(),
        )
        return

    if (
        row
        and row["status"] == "approved"
    ):
        await message.answer(
            "Добро пожаловать в WireGuard.",
            reply_markup=kb.user_main(),
        )
        return

    if (
        row
        and row["status"] == "blocked"
    ):
        await message.answer(
            "🚫 Доступ заблокирован."
        )
        return

    if (
        row
        and row["status"] == "pending"
    ):
        await message.answer(
            "⏳ Ваша заявка уже ожидает "
            "решения администратора."
        )
        return

    await message.answer(
        (
            "Добро пожаловать.\n\n"
            "Для получения WireGuard-доступа "
            "необходимо зарегистрироваться."
        ),
        reply_markup=kb.registration(),
    )


def _approved(row):
    return (
        row
        and row["status"] == "approved"
    )


def _owns_config(
    user,
    config,
):
    return (
        user
        and config
        and user["status"] == "approved"
        and config["user_id"] == user["id"]
        and config["status"] == "active"
    )


def _is_admin(
    call: CallbackQuery,
    app,
):
    return (
        call.from_user.id
        in app.settings.admin_ids
    )


def _user_identity(user):
    first_name = (
        user.first_name or ""
    ).strip()

    last_name = (
        user.last_name or ""
    ).strip()

    full_name = " ".join(
        x
        for x in (
            first_name,
            last_name,
        )
        if x
    )

    if user.username:
        if full_name:
            return (
                f"{full_name} "
                f"(@{user.username})"
            )

        return f"@{user.username}"

    return full_name or "Без имени"


def _user_identity_row(user):
    first_name = (
        user["first_name"] or ""
    ).strip()

    last_name = (
        user["last_name"] or ""
    ).strip()

    full_name = " ".join(
        x
        for x in (
            first_name,
            last_name,
        )
        if x
    )

    if user["username"]:
        if full_name:
            return (
                f"{full_name} "
                f"(@{user['username']}) "
                f"— ID {user['telegram_id']}"
            )

        return (
            f"@{user['username']} "
            f"— ID {user['telegram_id']}"
        )

    return (
        f"{full_name or 'Без имени'} "
        f"— ID {user['telegram_id']}"
    )


def _user_text(user):
    first_name = (
        user["first_name"] or ""
    ).strip()

    last_name = (
        user["last_name"] or ""
    ).strip()

    full_name = " ".join(
        x
        for x in (
            first_name,
            last_name,
        )
        if x
    )

    username = (
        f"@{user['username']}"
        if user["username"]
        else "нет"
    )

    status = {
        "approved": "🟢 Разрешён",
        "pending": "🟡 Ожидает решения",
        "rejected": "🔴 Отклонён",
        "blocked": "🚫 Заблокирован",
    }.get(
        user["status"],
        user["status"],
    )

    return (
        "👤 Пользователь\n\n"
        f"Имя: {full_name or 'Без имени'}\n"
        f"Username: {username}\n"
        f"Telegram ID: {user['telegram_id']}\n\n"
        f"Статус: {status}\n"
        f"Лимит QR: {user['qr_limit']}\n"
    )

def _write_temp_conf(
    app,
    config_id,
    text,
):
    path = (
        app.settings.qr_dir
        / f"{config_id}.conf"
    )

    path.write_text(
        text,
        encoding="utf-8",
    )

    path.chmod(0o600)

    return path
