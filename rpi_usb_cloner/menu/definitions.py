from rpi_usb_cloner.menu.model import MenuItem, MenuScreen

ACTIONS_MENU = MenuScreen(
    screen_id="actions",
    title="ACTIONS",
    items=[
        MenuItem(label="COPY", action="copy"),
        MenuItem(label="VIEW", action="view"),
        MenuItem(label="ERASE", action="erase"),
    ],
)

MAIN_MENU = MenuScreen(
    screen_id="devices",
    title="USB DEVICES",
)

SCREENS = {
    MAIN_MENU.screen_id: MAIN_MENU,
    ACTIONS_MENU.screen_id: ACTIONS_MENU,
}
