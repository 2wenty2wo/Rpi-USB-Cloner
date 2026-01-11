"""Centralized Lucide icon definitions for UI rendering.

This module provides a single source of truth for all Lucide icon assignments
used throughout the application. Icons are stored as Unicode characters using
their decimal codepoints from the Lucide font.

Usage:
    from rpi_usb_cloner.ui.icons import DRIVES_ICON, ALERT_ICON

    screens.render_error_screen(
        title="ERROR",
        message="Something went wrong",
        title_icon=ALERT_ICON
    )
"""

# Screen-level icons (used in menu navigation)
MAIN_ICON = chr(59059)  # layers-plus - main menu
SETTINGS_ICON = chr(57925)  # settings icon
TOOLS_ICON = chr(57580)  # tools icon
FILE_BROWSER_ICON = chr(58175)  # folders icon
IMAGES_ICON = chr(57559)  # images icon
DRIVES_ICON = chr(57581)  # hard-drive icon
ICONS_DEMO_ICON = chr(57922)  # icons icon
SCREENS_ICON = chr(57629)  # screens icon

# Action icons (used in operations and confirmations)
ALERT_ICON = chr(57639)  # octagon-alert - warnings and errors
EJECT_ICON = chr(57444)  # eject icon - unmount operations
SPARKLES_ICON = chr(58367)  # sparkles - format and special operations
USB_ICON = chr(57516)  # usb drive icon - USB selection
KEYBOARD_ICON = chr(57618)  # keyboard icon - text input
INFO_ICON = chr(57487)  # info icon - information displays
WRITE_ICON = chr(58597)  # write/backup icon - write operations

# File browser icons
FILE_ICON = chr(58099)  # file icon - regular files
FOLDER_ICON = chr(58174)  # folder icon - directories

# Keyboard mode icons
UPPERCASE_ICON = chr(58330)  # uppercase mode selector
LOWERCASE_ICON = chr(58328)  # lowercase mode selector
SYMBOLS_ICON = chr(57422)  # symbols mode selector

# Screen icons dictionary (for backward compatibility with menu system)
SCREEN_ICONS = {
    "main": MAIN_ICON,
    "settings": SETTINGS_ICON,
    "develop": "",  # No icon assigned
    "update": "",  # No icon assigned
    "power": "",  # No icon assigned
    "screensaver": "",  # No icon assigned
    "wifi": "",  # No icon assigned
    "tools": TOOLS_ICON,
    "logs": "",  # No icon assigned
    "file_browser": FILE_BROWSER_ICON,
    "images": IMAGES_ICON,
    "drives": DRIVES_ICON,
    "drive_list": DRIVES_ICON,
    "icons": ICONS_DEMO_ICON,
    "screens": SCREENS_ICON,
}
