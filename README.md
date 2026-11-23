# 📬 Canada Post - My Mail for Home Assistant

A Home Assistant custom integration for **Canada Post My Mail (Mon Courrier)** (forked and hardened from `Miloud-H/HA-Canada-Post`).

## Improvements in this fork (v2.0.0)
- **Token-only auth (no stored passwords):** Exchanges your username and password once during setup, stores only OAuth2 tokens, rotates them via `refresh_token`, prompts for HA reauth if expired, and revokes the refresh token when the integration is removed.
- **Read-only setup:** Extracts your `topic_id` directly from the `id_token` JWT `sub` claim—no dummy tracking items created or deleted on your account.
- **Matches the official My Mail app:** Separates **Out for delivery** (`ServiceType != 25`, e.g., general mail and barcoded letters) from **Arriving soon** (`ServiceType == 25`, e.g., flyers and neighbourhood mail).
- **Rich mailpiece metadata:** Exposes percent-encoded sender logos (`image_url` + `logos`), digital flyer flags (`has_digital_flyer` / `digital_flyer_count`), campaign names (`campaign_name`), `actual_start_date`, `mail_type`, and localized English/French sender names.
- **Smarter polling & controls:** Polls hourly during daytime (06:00–22:00) and every 4 hours overnight, includes a manual **Refresh** button, and provides redacted **Diagnostics**.

## Entities Created
- `sensor.canada_post_my_mail_<user>_out_for_delivery` — Lettermail & general mail out for delivery today
- `sensor.canada_post_my_mail_<user>_arriving_soon` — Flyers / neighbourhood mail arriving soon
- `sensor.canada_post_my_mail_<user>_in_transit` — Combined active mail (`out_for_delivery` + `arriving_soon`)
- `sensor.canada_post_my_mail_<user>_delivered` — Recently delivered mail (past 7 days)
- `sensor.canada_post_my_mail_<user>_mail_updated` — Compatibility sensor for *Mail and Packages* cards
- `button.canada_post_my_mail_<user>_refresh` — Force an immediate refresh

## Installation (HACS Custom Repository)
1. Open **HACS** → **⋮** → **Custom repositories**.
2. Add `https://github.com/iwismer/HA-Canada-Post` with category **Integration**.
3. Install **Canada Post My Mail** and restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration → Canada Post My Mail**.

## License
MIT License — see [LICENSE](LICENSE).
