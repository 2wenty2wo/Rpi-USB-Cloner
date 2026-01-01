import time


def make_wifi_labeler(display_module, renderer_module, wifi_service, cache_ttl=2.0):
    wifi_ssid_cache = {"ssid": None, "expires_at": 0.0}

    def get_cached_ssid():
        now = time.monotonic()
        if now >= wifi_ssid_cache["expires_at"]:
            wifi_ssid_cache["ssid"] = wifi_service.get_active_ssid()
            wifi_ssid_cache["expires_at"] = now + cache_ttl
        return wifi_ssid_cache["ssid"]

    def get_wifi_item_label():
        ssid = get_cached_ssid()
        if not ssid:
            return "WIFI"
        context = display_module.get_display_context()
        list_font = context.fonts.get("items", context.fontdisks)
        left_margin = context.x - 11
        max_item_width = context.width - left_margin - 1
        prefix = "WIFI ("
        suffix = ")"
        label = f"{prefix}{ssid}{suffix}"
        if renderer_module._measure_text_width(list_font, label) <= max_item_width:
            return label
        available_width = max_item_width - renderer_module._measure_text_width(
            list_font,
            f"{prefix}{suffix}",
        )
        truncated_ssid = renderer_module._truncate_text(
            ssid,
            list_font,
            max(0, int(available_width)),
        )
        if not truncated_ssid:
            return "WIFI"
        return f"{prefix}{truncated_ssid}{suffix}"

    return get_wifi_item_label
