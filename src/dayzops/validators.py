from typing import Any


class ValidationError(Exception):
    pass


def require(config: dict, path: str) -> Any:
    current: Any = config

    for part in path.split("."):
        if not isinstance(current, dict):
            raise ValidationError(path)

        if part not in current:
            raise ValidationError(path)

        current = current[part]

    return current