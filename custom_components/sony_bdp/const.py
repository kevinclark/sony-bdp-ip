"""Constants for the Sony BDP-CE integration."""

DOMAIN = "sony_bdp"

CONF_MAC = "mac"
CONF_CLIENT_ID = "client_id"
CONF_PIN = "pin"
CONF_NICKNAME = "nickname"  # name the *player* shows for this paired controller
CONF_MODEL = "model"  # e.g. "BDP-2018", from the player's own UPnP descriptor

DEFAULT_NICKNAME = "Home Assistant"
DEFAULT_CLIENT_ID = "home-assistant"

UPDATE_INTERVAL_SECONDS = 10
