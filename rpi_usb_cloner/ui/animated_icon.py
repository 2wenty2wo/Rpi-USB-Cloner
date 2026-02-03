"""Animated GIF icon support for OLED display.

This module provides smooth, independent animated icon rendering using a
background thread. Animations run fluidly regardless of what else is
happening on screen - blocking operations, user input waits, etc.

Architecture:
    - AnimatedIcon: Manages a single GIF's frames, timing, and state
    - AnimationManager: Coordinates all active animated icons with background thread
    - Background thread: Ticks animations every 20ms independently

Usage:
    from rpi_usb_cloner.ui.animated_icon import get_animation_manager

    # Start an animation (background thread auto-starts)
    manager = get_animation_manager()
    manager.start_icon("icons/12px-usb-ani.gif", position=(0, 0))

    # Stop all animations (background thread auto-stops when idle)
    manager.stop_all()

Performance:
    - Frames are pre-loaded and converted to 1-bit on first use
    - Only the icon region (~12x12 pixels) is updated per frame
    - Background thread sleeps efficiently between frames
    - Thread-safe with display lock coordination
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageSequence


if TYPE_CHECKING:
    from rpi_usb_cloner.ui.display import DisplayContext

# Default frame duration if GIF doesn't specify (100ms)
DEFAULT_FRAME_DURATION_MS = 100

# Background thread tick interval (20ms = 50fps max)
TICK_INTERVAL = 0.020

# Assets directory for resolving relative paths
ASSETS_DIR = Path(__file__).parent / "assets"


@dataclass
class AnimatedIcon:
    """Manages a single animated GIF icon.

    Attributes:
        path: Path to the GIF file.
        frames: Pre-loaded 1-bit PIL Image frames.
        durations: Per-frame duration in seconds.
        frame_index: Current frame being displayed.
        next_frame_time: Monotonic timestamp for next frame advance.
        position: (x, y) screen coordinates where icon is drawn.
        active: Whether animation is currently running.
    """

    path: Path
    frames: list[Image.Image] = field(default_factory=list)
    durations: list[float] = field(default_factory=list)
    frame_index: int = 0
    next_frame_time: float = 0.0
    position: tuple[int, int] | None = None
    active: bool = False

    @classmethod
    def load(cls, path: Path) -> AnimatedIcon:
        """Load a GIF and pre-convert all frames to 1-bit images.

        Args:
            path: Path to the GIF file.

        Returns:
            AnimatedIcon instance with pre-loaded frames.

        Raises:
            FileNotFoundError: If GIF file doesn't exist.
            ValueError: If file is not a valid GIF or has no frames.
        """
        if not path.exists():
            raise FileNotFoundError(f"Animated icon not found: {path}")

        frames: list[Image.Image] = []
        durations: list[float] = []

        with Image.open(path) as img:
            for frame in ImageSequence.Iterator(img):
                # Convert to 1-bit for OLED display
                converted = frame.convert("1")
                frames.append(converted.copy())

                # Get frame duration from GIF metadata
                duration_ms = frame.info.get("duration", DEFAULT_FRAME_DURATION_MS)
                if not isinstance(duration_ms, (int, float)) or duration_ms <= 0:
                    duration_ms = DEFAULT_FRAME_DURATION_MS
                durations.append(duration_ms / 1000.0)

        if not frames:
            raise ValueError(f"No frames found in GIF: {path}")

        return cls(path=path, frames=frames, durations=durations)

    def start(self, position: tuple[int, int]) -> None:
        """Start animation at the given screen position.

        Args:
            position: (x, y) coordinates on the display.
        """
        self.position = position
        self.frame_index = 0
        self.next_frame_time = time.monotonic()
        self.active = True

    def stop(self) -> None:
        """Stop the animation."""
        self.active = False
        self.position = None

    def get_current_frame(self) -> Image.Image:
        """Return the current frame image.

        Returns:
            PIL Image for the current frame.
        """
        return self.frames[self.frame_index]

    def advance_frame(self) -> float:
        """Advance to the next frame and return time for next advance.

        Returns:
            Monotonic timestamp when next frame should be rendered.
        """
        current_duration = self.durations[self.frame_index]
        self.frame_index = (self.frame_index + 1) % len(self.frames)
        self.next_frame_time = time.monotonic() + current_duration
        return self.next_frame_time

    @property
    def width(self) -> int:
        """Width of the icon in pixels."""
        return self.frames[0].width if self.frames else 0

    @property
    def height(self) -> int:
        """Height of the icon in pixels."""
        return self.frames[0].height if self.frames else 0


class AnimationManager:
    """Coordinates all animated icons on the display with background thread.

    This manager handles:
    - Loading and caching animated icons
    - Tracking active animations and their positions
    - Running a background thread for smooth, independent animation
    - Stopping animations when screens change

    The background thread ensures animations run fluidly regardless of
    what else is happening in the application (blocking operations,
    user input waits, etc).
    """

    def __init__(self) -> None:
        self._cache: dict[Path, AnimatedIcon] = {}
        self._active: dict[str, AnimatedIcon] = {}  # key -> icon mapping
        self._lock = threading.RLock()  # Protects _active and _cache
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._context: DisplayContext | None = None

    def get_or_load(self, icon_path: str | Path) -> AnimatedIcon:
        """Get an animated icon, loading from cache or disk.

        Args:
            icon_path: Path to the GIF file (absolute or relative to assets).

        Returns:
            AnimatedIcon instance (may be shared from cache).
        """
        path = Path(icon_path)
        if not path.is_absolute():
            path = ASSETS_DIR / path

        with self._lock:
            if path not in self._cache:
                self._cache[path] = AnimatedIcon.load(path)
            return self._cache[path]

    def start_icon(
        self, icon_path: str | Path, position: tuple[int, int], key: str | None = None
    ) -> AnimatedIcon:
        """Start an animated icon at the given position.

        Automatically starts the background animation thread if not running.

        Args:
            icon_path: Path to the GIF file.
            position: (x, y) screen coordinates.
            key: Optional unique key for this animation instance.
                 Defaults to the icon path string.

        Returns:
            The AnimatedIcon instance that was started.
        """
        icon = self.get_or_load(icon_path)
        key = key or str(icon_path)

        with self._lock:
            # Avoid restarting if same icon already active at same position
            if key in self._active:
                existing = self._active[key]
                if existing.active and existing.position == position:
                    return existing
                existing.stop()

            icon.start(position)
            self._active[key] = icon

            # Start background thread if needed
            self._ensure_thread_running()

        return icon

    def stop_icon(self, key: str) -> None:
        """Stop a specific animated icon.

        Args:
            key: The key used when starting the icon.
        """
        with self._lock:
            if key in self._active:
                self._active[key].stop()
                del self._active[key]

    def stop_all(self) -> None:
        """Stop all active animations.

        Call this when changing screens to ensure clean transitions.
        The background thread will automatically stop when idle.
        """
        with self._lock:
            for icon in self._active.values():
                icon.stop()
            self._active.clear()

    def set_context(self, context: DisplayContext) -> None:
        """Set the display context for rendering.

        Must be called before animations can render. Usually called
        once during application startup.

        Args:
            context: The display context.
        """
        self._context = context

    def tick(self, context: DisplayContext | None = None) -> bool:
        """Process animation frames that are due for update.

        This is called automatically by the background thread, but can
        also be called manually for immediate updates.

        Args:
            context: Optional display context (uses stored context if None).

        Returns:
            True if any frame was updated (display was refreshed).
        """
        ctx = context or self._context
        if ctx is None:
            return False

        # Store context for background thread
        if context is not None:
            self._context = context

        with self._lock:
            if not self._active:
                return False

            now = time.monotonic()
            updated = False

            for icon in list(self._active.values()):
                if not icon.active or icon.position is None:
                    continue

                if now >= icon.next_frame_time:
                    # Time to advance this icon's frame
                    icon.advance_frame()
                    self._render_icon_frame(ctx, icon)
                    updated = True

            return updated

    def _render_icon_frame(self, context: DisplayContext, icon: AnimatedIcon) -> None:
        """Render a single icon frame to the display.

        This performs a partial update, only touching the icon's region.

        Args:
            context: The display context.
            icon: The animated icon to render.
        """
        if icon.position is None:
            return

        frame = icon.get_current_frame()
        x, y = icon.position

        # Import here to avoid circular dependency
        from rpi_usb_cloner.ui import display

        with display._display_lock:
            # Paste the frame at the icon's position
            context.image.paste(frame, (x, y))
            # Update the display
            context.disp.display(context.image)
            display.mark_display_dirty()

    def _ensure_thread_running(self) -> None:
        """Start the background animation thread if not already running."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._animation_loop,
            name="AnimatedIconThread",
            daemon=True,
        )
        self._thread.start()

    def _animation_loop(self) -> None:
        """Background thread loop that ticks animations."""
        while not self._stop_event.is_set():
            # Check if we have active animations
            with self._lock:
                has_active = any(
                    icon.active and icon.position is not None
                    for icon in self._active.values()
                )

            if not has_active:
                # No active animations, stop the thread
                break

            # Tick animations
            if self._context is not None:
                self.tick()

            # Sleep until next tick
            time.sleep(TICK_INTERVAL)

    def has_active_animations(self) -> bool:
        """Check if there are any active animations.

        Returns:
            True if at least one animation is active.
        """
        with self._lock:
            return any(icon.active for icon in self._active.values())

    def get_next_frame_time(self) -> float | None:
        """Get the earliest next frame time across all active animations.

        Returns:
            Monotonic timestamp, or None if no animations are active.
        """
        with self._lock:
            times = [
                icon.next_frame_time
                for icon in self._active.values()
                if icon.active and icon.position is not None
            ]
            return min(times) if times else None


# Module-level singleton
_animation_manager: AnimationManager | None = None


def get_animation_manager() -> AnimationManager:
    """Get the global animation manager singleton.

    Returns:
        The AnimationManager instance.
    """
    global _animation_manager
    if _animation_manager is None:
        _animation_manager = AnimationManager()
    return _animation_manager


def reset_animation_manager() -> None:
    """Reset the animation manager (primarily for testing).

    This stops all animations and clears the cache.
    """
    global _animation_manager
    if _animation_manager is not None:
        _animation_manager._stop_event.set()
        _animation_manager.stop_all()
        _animation_manager._cache.clear()
    _animation_manager = None
