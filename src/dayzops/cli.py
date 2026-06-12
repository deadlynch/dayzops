import sys

from pathlib import Path

from dayzops import __version__
from dayzops.config import load_config, ConfigError
from dayzops.constants import DEFAULT_CONFIG


def cmd_version():
    print(f"dayzops {__version__}")


def cmd_validate_config():
    try:
        load_config(DEFAULT_CONFIG)
        print("Configuration valid")
        return 0

    except ConfigError as exc:
        print(f"Configuration invalid: {exc}")
        return 1


def cmd_status():
    print("DayZOPS Status")
    print("----------------")
    print(f"Config File: {DEFAULT_CONFIG}")

    if DEFAULT_CONFIG.exists():
        print("Configuration: OK")
    else:
        print("Configuration: Missing")

    print("Server: Not Installed")
    print("Mods: Unknown")


def main():
    if len(sys.argv) < 2:
        print(
            "Usage: dayzops "
            "[version|validate-config|status]"
        )
        return 1

    command = sys.argv[1]

    if command == "version":
        cmd_version()
        return 0

    if command == "validate-config":
        return cmd_validate_config()

    if command == "status":
        cmd_status()
        return 0

    print(f"Unknown command: {command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())