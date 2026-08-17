from dataclasses import dataclass
from pathlib import Path
import os

from cryptography.fernet import Fernet
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int]
    fernet_key: bytes
    database_path: Path
    qr_dir: Path
    routeros_host: str
    routeros_port: int
    routeros_ssl: bool
    routeros_username: str
    routeros_password: str
    routeros_interface: str
    wg_server_public_key: str
    wg_endpoint: str
    wg_client_network: str
    wg_server_address: str
    wg_dns: str
    wg_client_allowed_ips: str
    wg_client_keepalive: int
    default_qr_limit: int


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_settings() -> Settings:
    load_dotenv()

    admin_ids = frozenset(
        int(x.strip())
        for x in _required("ADMIN_IDS").split(",")
        if x.strip()
    )

    fernet_key = _required("APP_FERNET_KEY").encode()
    Fernet(fernet_key)

    settings = Settings(
        bot_token=_required("BOT_TOKEN"),
        admin_ids=admin_ids,
        fernet_key=fernet_key,
        database_path=Path(os.getenv("DATABASE_PATH", "./data/bot.db")),
        qr_dir=Path(os.getenv("QR_DIR", "./data/qr")),
        routeros_host=_required("ROUTEROS_HOST"),
        routeros_port=int(os.getenv("ROUTEROS_PORT", "8728")),
        routeros_ssl=os.getenv("ROUTEROS_SSL", "false").lower() == "true",
        routeros_username=_required("ROUTEROS_USERNAME"),
        routeros_password=_required("ROUTEROS_PASSWORD"),
        routeros_interface=_required("ROUTEROS_INTERFACE"),
        wg_server_public_key=_required("WG_SERVER_PUBLIC_KEY"),
        wg_endpoint=_required("WG_ENDPOINT"),
        wg_client_network=_required("WG_CLIENT_NETWORK"),
        wg_server_address=_required("WG_SERVER_ADDRESS"),
        wg_dns=os.getenv("WG_DNS", ""),
        wg_client_allowed_ips=os.getenv("WG_CLIENT_ALLOWED_IPS", "0.0.0.0/0"),
        wg_client_keepalive=int(os.getenv("WG_CLIENT_KEEPALIVE", "25")),
        default_qr_limit=int(os.getenv("DEFAULT_QR_LIMIT", "1")),
    )

    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    settings.qr_dir.mkdir(parents=True, exist_ok=True)
    return settings
