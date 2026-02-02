"""Animated GIF icon support for smooth UI animations.

This module provides time-based animated icon rendering that stays smooth
regardless of UI load. Animation frames are determined by real-time sampling
rather than frame counters, ensuring fluid animation even during heavy operations.

Usage:
    from rpi_usb_cloner.ui.animated_icons import AnimatedIcon, get_animated_icon
    
    # Pre-defined animated icons
    icon = get_animated_icon("usb")
    
    # Custom animated icon
    icon = AnimatedIcon("icons/custom-ani.gif", size=(12, 12))
    
    # Get frame for current time
    frame = icon.get_frame(time.monotonic())
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image

# Base path for UI assets
ASSETS_DIR = Path(__file__).resolve().parent / "assets"

# Cache for loaded animated icons
_icon_cache: Dict[str, "AnimatedIcon"] = {}


@dataclass(frozen=True)
class AnimatedIconRef:
    """Reference to an animated icon that can be used in icon constants.
    
    This lightweight reference is stored in icons.py constants. The actual
    AnimatedIcon object is loaded on first use and cached.
    
    Attributes:
        path: Relative path to the GIF file from the assets directory
        size: Target size (width, height) to resize frames to
    """
    path: str
    size: Tuple[int, int] = (12, 12)
    
    def resolve(self) -> AnimatedIcon:
        """Resolve this reference to a loaded AnimatedIcon instance."""
        return get_animated_icon_by_path(self.path, self.size)


class AnimatedIcon:
    """Pre-loaded animated GIF with time-based frame sampling.
    
    Frames are loaded once at initialization and cached. The current frame
    is determined by sampling time.monotonic(), ensuring the animation
    stays synchronized with real time regardless of rendering load.
    
    Args:
        gif_path: Path to the GIF file (absolute or relative to assets dir)
        size: Target size (width, height) to resize frames to
        
    Example:
        icon = AnimatedIcon("icons/12px-usb-ani.gif", size=(12, 12))
        frame = icon.get_frame(time.monotonic())  # Returns PIL Image
    """
    
    def __init__(self, gif_path: str | Path, size: Tuple[int, int] = (12, 12)):
        self.size = size
        self.frames: List[Image.Image] = []
        self.frame_durations_ms: List[int] = []
        self.total_duration_ms: int = 0
        
        # Resolve path
        path = Path(gif_path)
        if not path.is_absolute():
            path = ASSETS_DIR / path
        
        self._load_gif(path)
    
    def _load_gif(self, path: Path) -> None:
        """Load all frames from the GIF file.
        
        Args:
            path: Absolute path to the GIF file
            
        Raises:
            FileNotFoundError: If the GIF file doesn't exist
            IOError: If the GIF cannot be loaded
        """
        if not path.exists():
            raise FileNotFoundError(f"Animated icon not found: {path}")
        
        with Image.open(path) as gif:
            # Handle single-frame GIFs gracefully
            frame_count = getattr(gif, "n_frames", 1)
            
            for frame_index in range(frame_count):
                gif.seek(frame_index)
                
                # Convert to 1-bit monochrome for display compatibility
                frame = gif.convert("1")
                
                # Resize if needed
                if frame.size != self.size:
                    frame = frame.resize(self.size, Image.Resampling.LANCZOS)
                
                self.frames.append(frame)
                
                # Extract frame duration (default to 100ms if not specified)
                duration = gif.info.get("duration", 100)
                # Handle duration=0 (some GIFs use this for "infinite")
                if duration == 0:
                    duration = 100
                self.frame_durations_ms.append(duration)
        
        self.total_duration_ms = sum(self.frame_durations_ms)
        
        # Handle edge case: empty GIF or all zero durations
        if self.total_duration_ms == 0:
            self.total_duration_ms = 100 * len(self.frames)
            self.frame_durations_ms = [100] * len(self.frames)
    
    def get_frame(self, timestamp: float | None = None) -> Image.Image:
        """Get the frame that should be displayed at the given timestamp.
        
        Uses time-based sampling to ensure animation stays synchronized
        with real time, preventing drift or stutter under load.
        
        Args:
            timestamp: Monotonic timestamp (defaults to time.monotonic())
            
        Returns:
            PIL Image in 1-bit mode, sized to the target dimensions
            
        Note:
            If the GIF has only one frame, that frame is always returned.
        """
        if not self.frames:
            # Return empty image as fallback
            return Image.new("1", self.size, 0)
        
        if len(self.frames) == 1:
            return self.frames[0]
        
        if timestamp is None:
            timestamp = time.monotonic()
        
        # Convert to milliseconds and wrap to loop duration
        elapsed_ms = int((timestamp * 1000) % self.total_duration_ms)
        
        # Find the frame for this timestamp
        cumulative_ms = 0
        for i, duration in enumerate(self.frame_durations_ms):
            cumulative_ms += duration
            if elapsed_ms < cumulative_ms:
                return self.frames[i]
        
        # Fallback to last frame (shouldn't reach here)
        return self.frames[-1]
    
    @property
    def is_animated(self) -> bool:
        """True if this icon has multiple frames."""
        return len(self.frames) > 1
    
    @property
    def loop_duration(self) -> float:
        """Total loop duration in seconds."""
        return self.total_duration_ms / 1000.0


def get_animated_icon(name: str, size: Tuple[int, int] = (12, 12)) -> AnimatedIcon:
    """Get a cached animated icon by name.
    
    Pre-defined animated icons:
        - "usb": icons/12px-usb-ani.gif (12x12)
    
    Args:
        name: Short name of the animated icon
        size: Target size (defaults to 12x12)
        
    Returns:
        Cached AnimatedIcon instance
        
    Raises:
        KeyError: If the icon name is not recognized
    """
    cache_key = f"{name}:{size[0]}x{size[1]}"
    
    if cache_key not in _icon_cache:
        # Pre-defined icon mappings
        icon_paths = {
            "usb": "icons/12px-usb-ani.gif",
        }
        
        if name not in icon_paths:
            raise KeyError(f"Unknown animated icon: {name}. Available: {list(icon_paths.keys())}")
        
        _icon_cache[cache_key] = AnimatedIcon(icon_paths[name], size)
    
    return _icon_cache[cache_key]


def get_animated_icon_by_path(path: str, size: Tuple[int, int] = (12, 12)) -> AnimatedIcon:
    """Get a cached animated icon by file path.
    
    Args:
        path: Relative path from assets directory
        size: Target size (defaults to 12x12)
        
    Returns:
        Cached AnimatedIcon instance
    """
    cache_key = f"path:{path}:{size[0]}x{size[1]}"
    
    if cache_key not in _icon_cache:
        _icon_cache[cache_key] = AnimatedIcon(path, size)
    
    return _icon_cache[cache_key]


def is_animated_icon_path(path: str) -> bool:
    """Check if a path refers to an animated GIF.
    
    Args:
        path: Icon path or string to check
        
    Returns:
        True if the path ends with .gif (case-insensitive)
    """
    return path.lower().endswith(".gif")


def clear_animated_icon_cache() -> None:
    """Clear the animated icon cache.
    
    Useful for testing or memory-constrained scenarios.
    """
    _icon_cache.clear()
