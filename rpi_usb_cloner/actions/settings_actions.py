from rpi_usb_cloner.ui import screens


def coming_soon() -> None:
    screens.show_coming_soon(title="SETTINGS")


def wifi_settings() -> None:
    screens.show_wifi_settings(title="WIFI")


def update_version() -> None:
    screens.show_update_version(title="UPDATE / VERSION")
