from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def user_reply_menu():
    """Постоянное пользовательское меню внизу Telegram-чата."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📱 Мои QR-коды"),
                KeyboardButton(text="➕ Получить новый QR"),
            ],
            [KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите действие…",
    )


def admin_reply_menu():
    """Постоянное меню администратора: пользовательские + административные действия."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📱 Мои QR-коды"),
                KeyboardButton(text="➕ Получить новый QR"),
            ],
            [KeyboardButton(text="ℹ️ Помощь")],
            [
                KeyboardButton(text="👥 Пользователи"),
                KeyboardButton(text="🔔 Запросы"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
        input_field_placeholder="Выберите действие…",
    )


def user_main():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Мои QR-коды", callback_data="user:configs")],
        [InlineKeyboardButton(text="➕ Получить новый QR", callback_data="user:new")],
    ])


def registration():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Запросить регистрацию", callback_data="reg:request")],
    ])


def admin_request(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Разрешить", callback_data=f"admin:approve:{user_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:reject:{user_id}"),
        ],
    ])


def user_configs(configs):
    rows = [
        [InlineKeyboardButton(
            text=f"📱 {row['name']} ({row['vpn_address']})",
            callback_data=f"user:show:{row['id']}",
        )]
        for row in configs
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_configs_compact(configs):
    """Действия с конфигурациями без отдельной навигации."""
    rows = []
    for row in configs:
        rows.append([
            InlineKeyboardButton(
                text=f"📷 {row['name']} ({row['vpn_address']})",
                callback_data=f"menu:qr:{row['id']}",
            ),
            InlineKeyboardButton(
                text="📄 .conf",
                callback_data=f"menu:conf:{row['id']}",
            ),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def config_actions(config_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📷 Показать QR", callback_data=f"user:qr:{config_id}")],
        [InlineKeyboardButton(text="📄 Получить конфигурацию", callback_data=f"user:conf:{config_id}")],
    ])


def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📨 Запросы", callback_data="admin:pending")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin:users")],
    ])


def admin_users(users):
    rows = [
        [InlineKeyboardButton(
            text=f"{'🟢' if u['status'] == 'approved' else '🔴'} "
                 f"{u['first_name'] or ''} @{u['username'] or 'нет'}",
            callback_data=f"admin:user:{u['id']}",
        )]
        for u in users
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_user(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Увеличить лимит", callback_data=f"admin:limitup:{user_id}")],
        [InlineKeyboardButton(text="➖ Уменьшить лимит", callback_data=f"admin:limitdown:{user_id}")],
        [InlineKeyboardButton(text="📱 QR-коды", callback_data=f"admin:configs:{user_id}")],
        [InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"admin:block:{user_id}")],
    ])


def admin_configs(configs):
    rows = [
        [InlineKeyboardButton(
            text=f"🟢 {row['name']} {row['vpn_address']}",
            callback_data=f"admin:delcfg:{row['id']}",
        )]
        for row in configs
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
