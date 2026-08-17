import asyncio
import ipaddress
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

import qrcode

from bot.config import Settings
from bot.database import Database
from bot.security import SecretBox


logger = logging.getLogger(__name__)


@dataclass
class KeyPair:
    private_key: str
    public_key: str


def _run(
    command: list[str],
    input_text: str | None = None,
) -> str:
    result = subprocess.run(
        command,
        input=input_text,
        text=True,
        capture_output=True,
        check=True,
    )

    return result.stdout.strip()


def generate_keypair() -> KeyPair:
    private_key = _run(["wg", "genkey"])
    public_key = _run(
        ["wg", "pubkey"],
        private_key + "\n",
    )

    return KeyPair(
        private_key,
        public_key,
    )


def next_client_address(
    network: str,
    used: list[str],
    server_address: str,
) -> str:
    net = ipaddress.ip_network(
        network,
        strict=False,
    )

    used_set = {
        ipaddress.ip_interface(x).ip
        for x in used
    }

    server_ip = ipaddress.ip_interface(
        server_address
    ).ip

    used_set.add(server_ip)

    for host in net.hosts():
        if host not in used_set:
            return f"{host}/32"

    raise RuntimeError(
        "No free WireGuard client addresses remain"
    )


def build_config(
    settings: Settings,
    private_key: str,
    vpn_address: str,
) -> str:
    lines = [
        "[Interface]",
        f"PrivateKey = {private_key}",
        f"Address = {vpn_address}",
    ]

    if settings.wg_dns:
        lines.append(
            f"DNS = {settings.wg_dns}"
        )

    lines += [
        "",
        "[Peer]",
        f"PublicKey = {settings.wg_server_public_key}",
        f"AllowedIPs = {settings.wg_client_allowed_ips}",
        f"Endpoint = {settings.wg_endpoint}",
        (
            "PersistentKeepalive = "
            f"{settings.wg_client_keepalive}"
        ),
        "",
    ]

    return "\n".join(lines)


def write_qr(
    config: str,
    path: Path,
) -> None:
    img = qrcode.make(config)
    img.save(path)


class WireGuardService:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        routeros,
    ):
        self.settings = settings
        self.db = db
        self.routeros = routeros
        self.box = SecretBox(settings.fernet_key)

    async def create(
        self,
        user_id: int,
        telegram_id: int,
    ):
        user = self.db.get_user_by_id(user_id)

        if not user or user["status"] != "approved":
            raise RuntimeError(
                "User is not approved"
            )

        active = self.db.count_active_configs(
            user_id
        )

        if active >= user["qr_limit"]:
            raise RuntimeError(
                "QR limit reached"
            )

        keypair = await asyncio.to_thread(
            generate_keypair
        )

        vpn_address = next_client_address(
            self.settings.wg_client_network,
            self.db.active_vpn_addresses(),
            self.settings.wg_server_address,
        )

        number = self.db.next_config_number(
            telegram_id
        )

        name = (
            f"wg-{telegram_id}-{number}"
        )

        comment = (
            f"telegram:{telegram_id}:wg"
        )

        peer_id = None
        config_id = None
        qr_path = None

        try:
            peer_id = await self.routeros.add_peer(
                public_key=keypair.public_key,
                allowed_address=vpn_address,
                comment=comment,
                name=name,
            )

            encrypted = self.box.encrypt(
                keypair.private_key
            )

            config_id = self.db.create_config(
                user_id=user_id,
                name=name,
                private_key_encrypted=encrypted,
                public_key=keypair.public_key,
                vpn_address=vpn_address,
                routeros_peer_id=peer_id,
            )

            config = build_config(
                self.settings,
                keypair.private_key,
                vpn_address,
            )

            qr_path = (
                self.settings.qr_dir
                / f"{config_id}.png"
            )

            await asyncio.to_thread(
                write_qr,
                config,
                qr_path,
            )

            return (
                config_id,
                config,
                qr_path,
            )

        except Exception:
            logger.exception(
                "WireGuard creation failed; "
                "rolling back"
            )

            if qr_path is not None:
                qr_path.unlink(
                    missing_ok=True
                )

            if peer_id is not None:
                try:
                    await self.routeros.remove_peer(
                        peer_id
                    )
                except Exception:
                    logger.exception(
                        "Failed to rollback "
                        "RouterOS peer %s",
                        peer_id,
                    )

            if config_id is not None:
                try:
                    self.db.mark_config_deleted(
                        config_id,
                        telegram_id,
                    )
                except Exception:
                    logger.exception(
                        "Failed to rollback "
                        "database config %s",
                        config_id,
                    )

            raise

    def get_config_text(
        self,
        config_row,
    ):
        private_key = self.box.decrypt(
            config_row[
                "private_key_encrypted"
            ]
        )

        return build_config(
            self.settings,
            private_key,
            config_row["vpn_address"],
        )
