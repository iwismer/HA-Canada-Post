"""Constants for the Canada Post My Mail integration."""

from __future__ import annotations

DOMAIN = "canadapost"

CLIENT_ID = "cpc-nativeapp-2020"
OAUTH_SCOPE = "openid profile"

URL_AUTH = "https://sso-osu.canadapost-postescanada.ca/mga/sps/oauth/oauth20/token"
URL_REVOKE = "https://sso-osu.canadapost-postescanada.ca/mga/sps/oauth/oauth20/revoke"
URL_MAIL = "https://1i5z3519d0.execute-api.ca-central-1.amazonaws.com/mailmanager/v1/notifications/{topic_id}"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_TOPIC_ID = "topic_id"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_ID_TOKEN = "id_token"
CONF_EXPIRES_AT = "expires_at"
CONF_INCLUDE_ADS = "include_ads"

TOKEN_REFRESH_MARGIN_SECONDS = 300
DEFAULT_DAY_SPAN = -7

SERVICE_TYPE_GENERAL_MAIL = 0
SERVICE_TYPE_NEIGHBOURHOOD_MAIL = 25

QUIET_HOUR_START = 22
QUIET_HOUR_END = 6
SCAN_INTERVAL_DAY_MINUTES = 60
SCAN_INTERVAL_NIGHT_MINUTES = 240
