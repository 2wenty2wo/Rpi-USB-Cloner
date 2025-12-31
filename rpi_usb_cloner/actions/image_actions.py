import time

from rpi_usb_cloner.ui import screens


def coming_soon() -> None:
    screens.show_coming_soon(title="IMAGES")


def backup_image() -> None:
    screens.render_status_template("BACKUP", "Running...", progress_line="Preparing image...")
    time.sleep(1)
    screens.render_status_template("BACKUP", "Done", progress_line="Image saved.")
    time.sleep(1)


def write_image() -> None:
    screens.render_status_template("WRITE", "Running...", progress_line="Preparing media...")
    time.sleep(1)
    screens.render_status_template("WRITE", "Done", progress_line="Image written.")
    time.sleep(1)
