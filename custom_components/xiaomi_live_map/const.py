"""Constants for Xiaomi Live Map."""

from __future__ import annotations

DOMAIN = "xiaomi_live_map"
SOURCE_DOMAIN = "xiaomi_cloud_map_extractor"

CONF_SOURCE = "source_entry_id"
CONF_VACUUM_ENTITY = "vacuum_entity"
CONF_ACTIVE_ENTITY = "active_entity"
CONF_MAP_NAME_ENTITY = "map_name_entity"
CONF_WATCH_INTERVAL = "watch_interval"
CONF_ACTIVE_INTERVAL = "active_interval"
CONF_IDLE_INTERVAL = "idle_interval"

DEFAULT_WATCH_INTERVAL = 3  # seconds, while cleaning and a card is open
DEFAULT_ACTIVE_INTERVAL = 10  # seconds, while cleaning and no card is open
DEFAULT_IDLE_INTERVAL = 300  # seconds, while docked and no card is open
IDLE_VIEW_INTERVAL = 30  # seconds, while docked and a card is open
ERROR_MIN_INTERVAL = 15  # seconds between retries after a failure

ACTIVE_STATES = ("cleaning", "returning", "paused")
LINGER = 120  # keep polling fast for this long after a job ends, to catch the final map
MIN_JOB_POINTS = 30  # a path at least this long counts as a real clean and is kept as "last clean"
DOWNLOAD_TIMEOUT = 25

CARD_URL = f"/{DOMAIN}/xiaomi-live-map-card.js"
