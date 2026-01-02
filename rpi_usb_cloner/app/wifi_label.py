def make_wifi_labeler(display_module, renderer_module, wifi_service, cache_ttl=2.0):
    def get_wifi_item_label():
        status = wifi_service.get_status_snapshot()
        if status and status.get("connected"):
            return "WIFI: Connected"
        return "WIFI"

    return get_wifi_item_label
