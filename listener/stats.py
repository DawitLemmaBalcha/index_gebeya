"""
NB-50: process-global listener stats — the heartbeat payload source (D9).

The listener is HTTP-only; everything the backend needs to know about
listener health rides the heartbeat payload built from this module state.
Epoch timestamps; converted to ISO by client.send_heartbeat.
"""

import time

stats = {
    "started_at": time.time(),
    "items_processed_total": 0,
    "last_update_at": None,  # epoch ts of the last successful ingest
    "photo_refresher": {
        "last_run_at": None,
        "last_success_at": None,
        "last_error": None,
    },
}
