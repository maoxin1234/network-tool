#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""历史记录持久化模块"""

import json
import os
from datetime import datetime

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "check_history.json")
MAX_RECORDS = 50


def load_all():
    try:
        with open(_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def append(results: dict) -> list:
    records = load_all()
    records.insert(0, {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "results": {k: dict(v) for k, v in results.items()},
    })
    records = records[:MAX_RECORDS]
    try:
        with open(_PATH, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return records
