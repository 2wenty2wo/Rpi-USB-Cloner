from rpi_usb_cloner.menu.model import MenuItem, MenuScreen

ACTIONS_MENU = MenuScreen(
    screen_id="actions",
    title="ACTIONS",
    items=[
        MenuItem(label="SELECT DRIVE", next_screen="devices"),
        MenuItem(label="COPY DRIVE", action="drive.copy"),
        MenuItem(label="DRIVE INFO", action="drive.info"),
        MenuItem(label="ERASE DRIVE", action="drive.erase"),
        MenuItem(label="IMAGES", action="image.coming_soon"),
        MenuItem(label="TOOLS", action="tools.coming_soon"),
        MenuItem(label="SETTINGS", action="settings.coming_soon"),
    ],
)

MAIN_MENU = MenuScreen(
    screen_id="devices",
    title="SELECT DRIVE",
)

SCREENS = {
    MAIN_MENU.screen_id: MAIN_MENU,
    ACTIONS_MENU.screen_id: ACTIONS_MENU,
}
