"""Example script tool — greets a user by name.

Protocol: reads JSON from stdin, writes JSON to stdout.
"""

import json
import sys


def main() -> None:
    data = json.loads(sys.stdin.read())
    name = data.get("name", "World")
    result = {
        "display_text": f"Hello, {name}! Nice to meet you.",
        "data": {"greeted": name},
    }
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
