from __future__ import annotations

import argparse
import json
import logging

from shorts.config import load_config
from shorts.pipeline import run


def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube Shorts automation")
    parser.add_argument("--slot", default="07:00", help="Scheduled slot")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = run(load_config(args.config), args.slot)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
