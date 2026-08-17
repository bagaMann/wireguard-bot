import argparse

from bot.config import load_settings
from bot.database import Database
from bot.security import generate_fernet_key


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("generate-fernet-key")
    sub.add_parser("init-db")
    sub.add_parser("check-config")

    args = parser.parse_args()

    if args.command == "generate-fernet-key":
        print(generate_fernet_key())
        return

    settings = load_settings()

    if args.command == "init-db":
        Database(settings.database_path).init()
        print(f"Database initialized: {settings.database_path}")
    elif args.command == "check-config":
        print("Configuration OK")
        print(f"Database: {settings.database_path}")
        print(f"QR directory: {settings.qr_dir}")
        print(f"RouterOS: {settings.routeros_host}:{settings.routeros_port}")
        print(f"WireGuard interface: {settings.routeros_interface}")


if __name__ == "__main__":
    main()
