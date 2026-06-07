from __future__ import annotations

import sys
from pathlib import Path


DEFAULT_PORT = 8003


def read_server_port(config_path: Path) -> int:
    try:
        text = config_path.read_text(encoding="utf-8")
    except Exception:
        return DEFAULT_PORT

    in_server_block = False
    server_indent = -1

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = line.strip()

        if not in_server_block:
            if stripped == "server:":
                in_server_block = True
                server_indent = indent
            continue

        if indent <= server_indent and stripped.endswith(":"):
            break

        if indent > server_indent and stripped.startswith("port:"):
            value = stripped.split(":", 1)[1].strip().strip("'\"")
            try:
                return int(value)
            except Exception:
                return DEFAULT_PORT

    return DEFAULT_PORT


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    config_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else project_root / "config.yaml"
    print(read_server_port(config_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
