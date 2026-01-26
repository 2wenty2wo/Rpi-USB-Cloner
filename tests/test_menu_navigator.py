import pytest
from unittest.mock import Mock
from rpi_usb_cloner.menu.navigator import MenuNavigator, ScreenState
from rpi_usb_cloner.menu.model import MenuScreen, MenuItem

# Fixtures for common test data
@pytest.fixture
def empty_screen():
    return MenuScreen(screen_id="empty", title="Empty", items=[])

@pytest.fixture
def simple_screen():
    return MenuScreen(
        screen_id="root",
        title="Root",
        items=[
            MenuItem(label="Item 1", action=lambda: None),
            MenuItem(label="Item 2", action=lambda: None),
            MenuItem(label="Item 3", action=lambda: None),
        ]
    )

@pytest.fixture
def submenu_item():
    return MenuItem(
        label="Submenu",
        submenu=MenuScreen(
            screen_id="child",
            title="Child",
            items=[MenuItem(label="Child Item 1", action=lambda: None)]
        )
    )

@pytest.fixture
def complex_screens(simple_screen, submenu_item):
    child_screen = submenu_item.submenu
    # Add submenu item to root screen
    simple_screen.items.append(submenu_item)
    
    return {
        "root": simple_screen,
        "child": child_screen,
        "empty": MenuScreen(screen_id="empty", title="Empty", items=[])
    }

class TestMenuNavigator:
    """Test the pure logic of MenuNavigator without hardware dependencies."""

    def test_initialization(self, simple_screen):
        """Test that navigator initializes correctly with a root screen."""
        screens = {"root": simple_screen}
        navigator = MenuNavigator(screens, root_screen_id="root")
        
        assert navigator.current_screen().screen_id == "root"
        assert navigator.current_state().selected_index == 0
        assert navigator.current_state().scroll_offset == 0
        assert len(navigator._stack) == 1

    def test_initialization_invalid_root(self):
        """Test that unknown root screen raises ValueError."""
        with pytest.raises(ValueError, match="Unknown root screen"):
            MenuNavigator({}, root_screen_id="missing")

    def test_items_provider(self, simple_screen):
        """Test that dynamic item providers override static items."""
        dynamic_items = [MenuItem(label="Dynamic", action=lambda: None)]
        provider_mock = Mock(return_value=dynamic_items)
        
        screens = {"root": simple_screen}
        navigator = MenuNavigator(
            screens, 
            root_screen_id="root",
            items_providers={"root": provider_mock}
        )
        
        assert navigator.current_items() == dynamic_items
        provider_mock.assert_called_once()
        # Should not be simple_screen.items
        assert navigator.current_items() != simple_screen.items

    def test_move_selection_within_bounds(self, simple_screen):
        """Test moving selection up and down within bounds."""
        screens = {"root": simple_screen}
        navigator = MenuNavigator(screens, root_screen_id="root")
        visible_rows = 4

        # Initial state
        assert navigator.current_state().selected_index == 0

        # Move down (next item)
        navigator.move_selection(1, visible_rows)
        assert navigator.current_state().selected_index == 1

        # Move down again
        navigator.move_selection(1, visible_rows)
        assert navigator.current_state().selected_index == 2

        # Move up (previous item)
        navigator.move_selection(-1, visible_rows)
        assert navigator.current_state().selected_index == 1

    def test_move_selection_clamping(self, simple_screen):
        """Test that selection stops at start and end of list."""
        screens = {"root": simple_screen}
        navigator = MenuNavigator(screens, root_screen_id="root")
        visible_rows = 4
        num_items = len(simple_screen.items) # 3 items

        # Try to move up from index 0
        navigator.move_selection(-1, visible_rows)
        assert navigator.current_state().selected_index == 0

        # Move beyond last item
        for _ in range(num_items + 5):
            navigator.move_selection(1, visible_rows)
        
        assert navigator.current_state().selected_index == num_items - 1

    def test_move_selection_empty_list(self, empty_screen):
        """Test moving selection in an empty list does nothing."""
        screens = {"empty": empty_screen}
        navigator = MenuNavigator(screens, root_screen_id="empty")
        
        navigator.move_selection(1, visible_rows=4)
        assert navigator.current_state().selected_index == 0
        
        navigator.move_selection(-1, visible_rows=4)
        assert navigator.current_state().selected_index == 0

    def test_scrolling_logic_move_down(self):
        """Test that scroll offset increases when moving down past visible rows."""
        # Create 10 items
        items = [MenuItem(label=f"Item {i}", action=lambda: None) for i in range(10)]
        screen = MenuScreen(screen_id="long", title="Long", items=items)
        screens = {"long": screen}
        
        navigator = MenuNavigator(screens, root_screen_id="long")
        visible_rows = 3
        
        # Move down to index 2 (still visible, 3rd item)
        # [0, 1, 2] -> Visible
        navigator.set_selection("long", 2, visible_rows)
        assert navigator.current_state().scroll_offset == 0
        
        # Move down to index 3 (4th item, should push scroll)
        # Scroll should be 1: [1, 2, 3] visible
        navigator.move_selection(1, visible_rows)
        assert navigator.current_state().selected_index == 3
        assert navigator.current_state().scroll_offset == 1
        
        # Move to end
        navigator.set_selection("long", 9, visible_rows)
        # Max scroll = len(10) - visible(3) = 7
        assert navigator.current_state().scroll_offset == 7

    def test_scrolling_logic_move_up(self):
        """Test that scroll offset decreases when moving up past visible rows."""
        items = [MenuItem(label=f"Item {i}", action=lambda: None) for i in range(10)]
        screen = MenuScreen(screen_id="long", title="Long", items=items)
        screens = {"long": screen}
        
        navigator = MenuNavigator(screens, root_screen_id="long")
        visible_rows = 3
        
        # Start at end
        navigator.set_selection("long", 9, visible_rows)
        assert navigator.current_state().scroll_offset == 7
        
        # Move up to index 6 (7th item)
        # Visible range at end: 7, 8, 9 (Indices) -> Scroll offset 7
        navigator.set_selection("long", 6, visible_rows)
        # Target index 6 is < scroll offset 7
        # New scroll should be 6. Visible: 6, 7, 8
        assert navigator.current_state().scroll_offset == 6

    def test_activate_leaf_item(self, variable_screens=None):
        """Test activating a leaf item returns its action string."""
        # Setup specific screen for this test
        mock_action = Mock()
        item = MenuItem(label="Leaf", action=mock_action)
        screen = MenuScreen(screen_id="root", title="Root", items=[item])
        screens = {"root": screen}
        
        navigator = MenuNavigator(screens, root_screen_id="root")
        
        action = navigator.activate(visible_rows=4)
        assert action == mock_action
        # Stack should remain unchanged
        assert len(navigator._stack) == 1

    def test_activate_submenu_item(self, complex_screens):
        """Test activating a submenu item acts as navigation."""
        navigator = MenuNavigator(complex_screens, root_screen_id="root")
        
        # Navigate to the submenu item (Item 1, Item 2, Item 3, Submenu)
        # Index 3 is the submenu
        navigator.set_selection("root", 3, visible_rows=4)
        
        # Activate should return None (consumed by navigator)
        result = navigator.activate(visible_rows=4)
        assert result is None
        
        # Should have pushed to stack
        assert len(navigator._stack) == 2
        assert navigator.current_screen().screen_id == "child"
        assert navigator.last_navigation_action() == "forward"

    def test_back_navigation(self, complex_screens):
        """Test back() pops the stack."""
        navigator = MenuNavigator(complex_screens, root_screen_id="root")
        
        # Enter submenu
        navigator.set_selection("root", 3, visible_rows=4)
        navigator.activate(visible_rows=4)
        assert navigator.current_screen().screen_id == "child"
        
        # Go back
        success = navigator.back()
        assert success is True
        assert navigator.current_screen().screen_id == "root"
        assert len(navigator._stack) == 1
        assert navigator.last_navigation_action() == "back"

    def test_back_at_root(self, simple_screen):
        """Test back() at root level returns False and does nothing."""
        screens = {"root": simple_screen}
        navigator = MenuNavigator(screens, root_screen_id="root")
        
        success = navigator.back()
        assert success is False
        assert len(navigator._stack) == 1
        assert navigator.current_screen().screen_id == "root"

    def test_selection_persistence(self, complex_screens):
        """Test that parent menu remembers selection when returning from child."""
        navigator = MenuNavigator(complex_screens, root_screen_id="root")
        
        # Select index 3 (Submenu)
        navigator.set_selection("root", 3, visible_rows=4)
        
        # Enter submenu
        navigator.activate(visible_rows=4)
        
        # Do stuff in submenu (move around)
        navigator.move_selection(1, visible_rows=4)
        
        # Go back
        navigator.back()
        
        # Should be back at index 3
        assert navigator.current_state().screen_id == "root"
        assert navigator.current_state().selected_index == 3
