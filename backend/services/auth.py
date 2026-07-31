"""
Telegram identity verification — the single seam for resolving a Telegram
identity to a User record.

Three behaviors live at this seam (previously duplicated across 4 route files):

1. **External Mini App auth** (items.py, channels.py, alerts.py)
   Parse Telegram WebApp initData ("user=" query string), get-or-create the
   User record. Fails with 403 on invalid input.

2. **Internal listener bypass** (alerts.py)
   The index-listener worker authenticates with a plain telegram_id integer
   plus the X-Internal-Service: index-listener header — no Mini App context.

3. **Cryptographic verification** (reviews.py)
   HMAC-SHA256 signature check over the initData payload (Telegram WebApp
   standard), used for actions that need proof of identity (reviews).

Error contract (preserved exactly from the four original implementations):
  - external path, "user=" missing -> 403 "Restricted: Alerts can only be
    managed from inside the Telegram Mini App."
  - any other auth failure        -> 403 "Authentication Failed"
  - verify_init_data, no BOT_TOKEN -> 500 "Server config error: Missing Bot Token"
  - verify_init_data, bad signature -> 401 "Authentication Failed: <reason>"
"""

import json
import hmac
import hashlib
import os
from typing import Optional
from urllib.parse import parse_qs, unquote

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from models import User

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


def authenticate(
    init_data: str,
    db: Session,
    x_internal_service: Optional[str] = None,
) -> User:
    """
    Resolve a Telegram identity to a User record.

    - If x_internal_service == "index-listener" and init_data.isdigit():
      internal bypass — treat init_data as the raw telegram_id.
    - Else: require "user=" in init_data, parse the JSON payload,
      get-or-create the User record.

    Raises HTTPException(403) on failure. Auto-registers unknown users.
    """
    try:
        tg_id = None
        username = "unknown"

        # --- INTERNAL BYPASS ---
        # The index-listener (bot) authenticates with a plain integer telegram ID.
        is_internal = (x_internal_service == "index-listener")

        if is_internal and init_data.isdigit():
            tg_id = int(init_data)

        # --- EXTERNAL (WEBAPP) STRICT CHECK ---
        else:
            # Valid Telegram WebApp data is a query string containing "user="
            if "user=" not in init_data:
                raise HTTPException(
                    status_code=403,
                    detail="Restricted: Alerts can only be managed from inside the Telegram Mini App.",
                )

            parsed = parse_qs(init_data)
            if 'user' in parsed:
                user_json = parsed['user'][0]
                user_data = json.loads(user_json)
                tg_id = user_data.get('id')
                username = user_data.get('username', 'unknown')
            else:
                raise ValueError("init_data missing 'user' field")

        if not tg_id:
            raise ValueError("Could not extract Telegram ID from init_data")

        # Database Lookup or Auto-Create
        user = db.scalar(select(User).where(User.telegram_id == tg_id))

        if not user:
            user = User(telegram_id=tg_id, username=username)
            db.add(user)
            db.commit()
            db.refresh(user)

        return user

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=403, detail="Authentication Failed")


def verify_init_data(init_data: str) -> dict:
    """
    HMAC-SHA256 cryptographic verification of Mini App initData (reviews).

    Raises HTTPException(500) if BOT_TOKEN missing, HTTPException(401) on
    invalid signature. Returns the parsed user dict.
    """
    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="Server config error: Missing Bot Token")

    try:
        # 1. Parse query string into a dict
        data = dict(qc.split("=") for qc in unquote(init_data).split("&"))

        if "hash" not in data:
            raise ValueError("No hash found")

        received_hash = data.pop("hash")

        # 2. Sort keys alphabetically
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))

        # 3. Calculate HMAC-SHA256 Signature
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        # 4. Compare
        if calculated_hash != received_hash:
            raise ValueError("Invalid Signature")

        # 5. Extract User Data
        user_data = json.loads(data["user"])
        return user_data

    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication Failed: {str(e)}")
