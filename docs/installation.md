# Установка

## 1. Debian

```bash
apt update
apt install -y python3 python3-venv python3-pip wireguard-tools unzip
```

## 2. Проект

```bash
mkdir -p /opt
cd /opt
unzip wireguard-telegram-bot.zip
mv wireguard-telegram-bot wireguard-bot
cd /opt/wireguard-bot
```

## 3. Python

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .
```

## 4. Секреты

```bash
cp .env.example .env
chmod 600 .env
```

Сгенерировать Fernet:

```bash
.venv/bin/python -m bot.cli generate-fernet-key
```

## 5. База

```bash
.venv/bin/python -m bot.cli init-db
```

## 6. Проверка

```bash
.venv/bin/python -m bot.cli check-config
```

## 7. Запуск

```bash
.venv/bin/python -m bot
```

## 8. systemd

```bash
cp systemd/wireguard-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now wireguard-bot
```
