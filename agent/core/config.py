from __future__ import annotations

import json
from pathlib import Path

from logger import build_logger

log = build_logger()

CONFIG_FILE = Path(__file__).resolve().parent.parent / "config" / "config.json"


class Config:
    def __init__(self):
        self.data = {}

    def load(self):
        if not CONFIG_FILE.exists():
            raise FileNotFoundError(CONFIG_FILE)

        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            self.data = json.load(f)

        log.info("Configuration loaded successfully.")
        return self.data

    def get(self, key, default=None):
        return self.data.get(key, default)


config = Config()
