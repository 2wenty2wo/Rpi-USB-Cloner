import time

from rpi_usb_cloner.ui import display


def show_coming_soon(title="COMING SOON", delay=1) -> None:
    display.display_lines([title, "Not implemented", "yet"])
    if delay:
        time.sleep(delay)
