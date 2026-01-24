from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from rpi_usb_cloner.menu.model import MenuItem, MenuScreen


@dataclass
class ScreenState:
    screen_id: str
    selected_index: int = 0
    scroll_offset: int = 0


class MenuNavigator:
    def __init__(
        self,
        screens: dict[str, MenuScreen],
        root_screen_id: str,
        items_providers: dict[str, Callable[[], list[MenuItem]]] | None = None,
    ) -> None:
        self._screens = screens
        self._items_providers = items_providers or {}
        if root_screen_id not in screens:
            raise ValueError(f"Unknown root screen: {root_screen_id}")
        self._stack: list[ScreenState] = [ScreenState(screen_id=root_screen_id)]
        self._last_navigation_action: str | None = None

    def last_navigation_action(self) -> str | None:
        return self._last_navigation_action

    def consume_last_navigation_action(self) -> str | None:
        action = self._last_navigation_action
        self._last_navigation_action = None
        return action

    def current_state(self) -> ScreenState:
        return self._stack[-1]

    def current_screen(self) -> MenuScreen:
        return self._screens[self.current_state().screen_id]

    def current_items(self) -> list[MenuItem]:
        screen_id = self.current_state().screen_id
        provider = self._items_providers.get(screen_id)
        if provider is not None:
            return provider()
        return list(self._screens[screen_id].items)

    def set_selection(self, screen_id: str, index: int, visible_rows: int) -> None:
        for state in self._stack:
            if state.screen_id == screen_id:
                state.selected_index = max(0, index)
                state.scroll_offset = self._ensure_scroll(state, visible_rows)
                return

    def move_selection(self, delta: int, visible_rows: int) -> None:
        state = self.current_state()
        items = self.current_items()
        if not items:
            state.selected_index = 0
            state.scroll_offset = 0
            return
        new_index = max(0, min(len(items) - 1, state.selected_index + delta))
        state.selected_index = new_index
        state.scroll_offset = self._ensure_scroll(state, visible_rows)

    def _ensure_scroll(self, state: ScreenState, visible_rows: int) -> int:
        items = self.current_items_for(state.screen_id)
        if not items:
            state.selected_index = 0
            return 0
        if state.selected_index >= len(items):
            state.selected_index = max(len(items) - 1, 0)
        scroll = state.scroll_offset
        if state.selected_index < scroll:
            scroll = state.selected_index
        elif state.selected_index >= scroll + visible_rows:
            scroll = max(state.selected_index - visible_rows + 1, 0)
        max_scroll = max(len(items) - visible_rows, 0)
        return min(scroll, max_scroll)

    def current_items_for(self, screen_id: str) -> list[MenuItem]:
        provider = self._items_providers.get(screen_id)
        if provider is not None:
            return provider()
        return list(self._screens[screen_id].items)

    def activate(self, visible_rows: int) -> Callable[[], None] | None:
        self._last_navigation_action = None
        state = self.current_state()
        items = self.current_items()
        if not items:
            return None
        if state.selected_index >= len(items):
            state.selected_index = max(len(items) - 1, 0)
        selected_item = items[state.selected_index]
        if selected_item.submenu:
            submenu_id = selected_item.submenu.screen_id
            if submenu_id not in self._screens:
                raise ValueError(f"Unknown screen: {submenu_id}")
            self._stack.append(ScreenState(screen_id=submenu_id))
            self._ensure_scroll(self.current_state(), visible_rows)
            self._last_navigation_action = "forward"
            return None
        return selected_item.action

    def back(self) -> bool:
        self._last_navigation_action = None
        if len(self._stack) <= 1:
            return False
        self._stack.pop()
        self._last_navigation_action = "back"
        return True

    def sync_visible_rows(self, visible_rows: int) -> None:
        state = self.current_state()
        state.scroll_offset = self._ensure_scroll(state, visible_rows)
