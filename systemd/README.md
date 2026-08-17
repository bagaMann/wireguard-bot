# Systemd

Создать пользователя:

```bash
useradd --system --home /opt/wireguard-bot --shell /usr/sbin/nologin wireguard-bot
chown -R wireguard-bot:wireguard-bot /opt/wireguard-bot
chmod 600 /opt/wireguard-bot/.env
```

Установить unit:

```bash
cp /opt/wireguard-bot/systemd/wireguard-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now wireguard-bot
```

Важно: `wireguard-tools` и `wg` должны быть доступны сервисному пользователю.
