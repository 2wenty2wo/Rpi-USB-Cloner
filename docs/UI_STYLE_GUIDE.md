# UI Style Guide

> **Purpose**: OLED display layout conventions for the Raspberry Pi USB Cloner.
> Follow these patterns when creating new screens or menus to maintain visual consistency.

**Related**: See `CLAUDE.md` for project conventions and `COMMON_TASKS.md` for implementation tutorials.

---

## Display Specifications

| Property | Value | Notes |
|----------|-------|-------|
| **Resolution** | 128x64 pixels | SSD1306 OLED |
| **Color Mode** | 1-bit monochrome | `Image.new("1", (128, 64), 0)` |
| **I2C Address** | 0x3C or 0x3D | Configured in display.py |

---

## Screen Layout Structure

All screens follow a 3-zone vertical layout:

```
+--------------------------------+
| TITLE AREA         (~14px)     |  <- Icon (optional) + title text
+--------------------------------+
|                                |
| CONTENT AREA       (~38px)     |  <- Menu items (4 rows) or content
|                                |
+--------------------------------+
| FOOTER/STATUS      (~12px)     |  <- Status bar (WiFi, BT, drives)
+--------------------------------+
```

---

## Key Layout Constants

**Location**: `app/state.py`, `ui/renderer.py`, `ui/display.py`

```python
# Menu rendering
VISIBLE_ROWS = 4                    # Menu items visible per screen
DEFAULT_VISIBLE_ROWS = 4            # Same as above (renderer.py)

# Display geometry (from DisplayContext)
width = 128                         # Display width
height = 64                         # Display height
x = 12                              # Left margin for text content
top = -2                            # Vertical start (allows slight overflow)
bottom = 66                         # Vertical end

# Title area
TITLE_PADDING = 0                   # Padding after title
TITLE_TEXT_Y_OFFSET = -2            # Fine-tune title vertical position
TITLE_ICON_PADDING = 2              # Space between icon and title text

# Menu items
ROW_HEIGHT = line_height + 1        # Each menu row height
SELECTOR = "> "                     # Selected item prefix
SCROLLBAR_WIDTH = 2                 # Pixels for scrollbar
SCROLLBAR_PADDING = 1               # Gap from right edge

# Toggle switches
TOGGLE_WIDTH = 12                   # Toggle icon width
TOGGLE_HEIGHT = 5                   # Toggle icon height

# Status bar icons
STATUS_ICON_SIZE = 7                # 7px status icons (WiFi, BT, Web)
```

---

## Font System

**Location**: `ui/display.py:283-304`

| Font Name | File | Size | Usage |
|-----------|------|------|-------|
| `title` | Born2bSportyFS.otf | 16pt | Screen titles |
| `items` | slkscr.ttf | 8pt | Menu items, content |
| `items_bold` | slkscrb.ttf | 8pt | Bold menu text |
| `footer` | slkscr.ttf | 8pt | Status bar text |
| `icons` | lucide.ttf | 16pt | Lucide icons |

**Line height calculation**: Use `_get_cached_line_height(font)` from `ui/renderer.py`

---

## Menu Rendering Pattern

**Location**: `ui/renderer.py:182-280`

```python
# Standard menu layout
def render_menu(context, items, selected_index, title, ...):
    # 1. Create image buffer
    image = Image.new("1", (128, 64), 0)
    draw = ImageDraw.Draw(image)

    # 2. Draw title with optional icon
    content_top = draw_title_with_icon(draw, title, icon=title_icon)

    # 3. Calculate visible items (scroll window)
    start_idx = max(0, selected_index - (VISIBLE_ROWS - 1))
    visible_items = items[start_idx : start_idx + VISIBLE_ROWS]

    # 4. Draw menu items
    y = content_top
    for i, item in enumerate(visible_items):
        actual_idx = start_idx + i
        prefix = "> " if actual_idx == selected_index else "  "
        draw.text((1, y), prefix + item.label, font=items_font, fill=1)
        y += line_height + 1

    # 5. Draw scrollbar if needed
    if len(items) > VISIBLE_ROWS:
        draw_scrollbar(draw, start_idx, len(items), VISIBLE_ROWS)

    # 6. Draw status bar footer
    draw_status_bar(draw, context)

    # 7. Update display
    context.device.display(image)
```

---

## Screen Type Patterns

### Progress Screen

**Location**: `ui/screens/progress.py`

```
+--------------------------------+
| CLONING...                     |  <- Title
+--------------------------------+
|                                |
| sda -> sdb                     |  <- Upper 65%: message text
| 45% complete                   |
|                                |
| ████████████░░░░░░░░░░░░       |  <- Lower 35%: progress bar
+--------------------------------+
```

- Progress bar Y position: `content_top + (height - content_top) * 0.65`
- Bar margins: 8px on each side
- Bar height: `max(10, line_height + 4)`

### Confirmation Dialog

**Location**: `ui/screens/confirmation.py`

```
+--------------------------------+
| ! FORMAT DRIVE?                |  <- Title with icon
+--------------------------------+
|                                |
| All data will be erased.       |  <- Centered prompt (upper 55%)
|                                |
|   [ NO ]      [ YES ]          |  <- Buttons (lower 35%)
+--------------------------------+
```

- Button width: `max(36, label_width + 16)`
- Button gap: 18px (auto-adjusts if tight)
- Selected button: inverted (white bg, black text)

### Error Screen

**Location**: `ui/screens/error.py`

```
+--------------------------------+
| ERROR                          |  <- Title
+--------------------------------+
|                                |
|   !  Clone failed:             |  <- Icon + message (centered)
|      Device not found          |
|                                |
+--------------------------------+
```

- Icon padding: 6px from message text
- Content centered vertically in available space

### Info/Status Screen

**Location**: `ui/screens/status.py`, `ui/screens/info.py`

```
+--------------------------------+
| SYSTEM INFO                    |  <- Title
+--------------------------------+
| CPU: 45%                       |
| RAM: 128MB / 512MB             |  <- Multi-line content
| Temp: 52C                      |
| Uptime: 2h 15m                 |
+--------------------------------+
```

- Left-aligned text at x=2
- Line spacing: line_height + 1

---

## Status Bar Footer

**Location**: `ui/status_bar.py`

The status bar is **consistent across all screens** that display it. Some screens (e.g., progress, error) may omit the footer entirely, but when present it always uses the same layout and indicators.

The status bar displays system indicators right-aligned:
```
|                    W  BT  U2 R1|
                     ^   ^   ^  ^
                   WiFi BT USB Repo
```

- Icons: 7px PNG images (`7px-wifi.png`, `7px-bluetooth.png`, `7px-pointer.png`)
- Drive counts: Text boxes "U#" (USB) and "R#" (Repo)
- Spacing: 1px between indicators
- Priority: Lower number = further right

---

## Toggle Switches

**Location**: `ui/toggle.py`

Toggle switches provide visual ON/OFF indicators for boolean settings.

- Dimensions: 12x5 pixels
- Images: `toggle-on.png`, `toggle-off.png`
- Usage: `format_toggle_label("SCREENSAVER", True)` returns `"SCREENSAVER {{TOGGLE:ON}}"`
- Renderer detects `{{TOGGLE:ON}}` / `{{TOGGLE:OFF}}` markers and replaces with images

---

## Reference Files

| File | What to Study |
|------|---------------|
| `ui/renderer.py` | Menu rendering, scrollbar, text layout |
| `ui/display.py:449-560` | Title rendering with icons |
| `ui/screens/progress.py` | Progress bar layout |
| `ui/screens/confirmation.py` | Button dialog layout |
| `ui/screens/error.py` | Error message centering |
| `ui/status_bar.py` | Footer indicator system |
| `ui/toggle.py` | Toggle switch rendering |
| `menu/definitions/main.py` | Menu structure example |
