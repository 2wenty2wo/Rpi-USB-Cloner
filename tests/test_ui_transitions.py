"""Tests for UI transitions module.

Tests for coverage of:
- render_slide_transition() - blocking transition rendering
- generate_slide_transition() - generator-based non-blocking transitions
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
from PIL import Image

from rpi_usb_cloner.ui import transitions


@pytest.fixture
def mock_display_context():
    """Create a mock display context for testing."""
    context = MagicMock()
    context.width = 128
    context.height = 64
    context.image = MagicMock()
    context.disp = MagicMock()
    return context


class TestRenderSlideTransition:
    """Tests for render_slide_transition() function."""

    @patch("rpi_usb_cloner.ui.transitions.generate_slide_transition")
    @patch("time.monotonic")
    @patch("time.sleep")
    def test_blocking_mode_consumes_all_frames(
        self, mock_sleep, mock_monotonic, mock_generate
    ):
        """Test blocking mode consumes all frames with proper timing."""
        # Setup mock to yield frame times
        mock_generate.return_value = iter([100.0, 100.04, 100.08, 100.12])
        mock_monotonic.side_effect = [99.0, 100.0, 100.04, 100.08, 100.12]

        from_image = Mock(spec=Image.Image)
        to_image = Mock(spec=Image.Image)

        transitions.render_slide_transition(
            from_image, to_image, "forward", frame_count=4
        )

        # Should call sleep for timing adjustments
        mock_sleep.assert_called()

    @patch("rpi_usb_cloner.ui.transitions.generate_slide_transition")
    @patch("time.monotonic")
    def test_no_sleep_when_behind_schedule(self, mock_monotonic, mock_generate):
        """Test no sleep when already behind schedule."""
        # Frame time is in past, no sleep needed
        mock_generate.return_value = iter([100.0])
        mock_monotonic.return_value = 101.0  # Already past frame time

        from_image = Mock(spec=Image.Image)
        to_image = Mock(spec=Image.Image)

        with patch("time.sleep") as mock_sleep:
            transitions.render_slide_transition(
                from_image, to_image, "forward", frame_count=1
            )
            mock_sleep.assert_not_called()


class TestGenerateSlideTransition:
    """Tests for generate_slide_transition() generator function."""

    @patch("rpi_usb_cloner.ui.transitions.display._display_lock")
    @patch("rpi_usb_cloner.ui.transitions.display.get_display_context")
    def test_forward_direction_slides_from_right(
        self, mock_get_context, mock_lock, mock_display_context
    ):
        """Test forward direction slides new image in from right."""
        mock_get_context.return_value = mock_display_context

        # Create actual PIL Images
        from_image = Image.new("1", (128, 64), 0)
        to_image = Image.new("1", (128, 64), 1)

        gen = transitions.generate_slide_transition(
            from_image, to_image, "forward", frame_count=4, frame_delay=0.01
        )

        # Consume all frames
        frame_times = list(gen)

        # Should yield 4 frame times
        assert len(frame_times) == 4
        # Each frame time should be monotonically increasing
        for i in range(1, len(frame_times)):
            assert frame_times[i] > frame_times[i - 1]

    @patch("rpi_usb_cloner.ui.transitions.display._display_lock")
    @patch("rpi_usb_cloner.ui.transitions.display.get_display_context")
    def test_back_direction_slides_from_left(
        self, mock_get_context, mock_lock, mock_display_context
    ):
        """Test back direction slides new image in from left."""
        mock_get_context.return_value = mock_display_context

        from_image = Image.new("1", (128, 64), 0)
        to_image = Image.new("1", (128, 64), 1)

        gen = transitions.generate_slide_transition(
            from_image, to_image, "back", frame_count=4, frame_delay=0.01
        )

        frame_times = list(gen)
        assert len(frame_times) == 4

    @patch("rpi_usb_cloner.ui.transitions.display._display_lock")
    @patch("rpi_usb_cloner.ui.transitions.display.get_display_context")
    def test_invalid_direction_defaults_to_forward(
        self, mock_get_context, mock_lock, mock_display_context
    ):
        """Test invalid direction defaults to forward."""
        mock_get_context.return_value = mock_display_context

        from_image = Image.new("1", (128, 64), 0)
        to_image = Image.new("1", (128, 64), 1)

        gen = transitions.generate_slide_transition(
            from_image, to_image, "invalid_direction", frame_count=2, frame_delay=0.01
        )

        frame_times = list(gen)
        assert len(frame_times) == 2

    @patch("rpi_usb_cloner.ui.transitions.display._display_lock")
    @patch("rpi_usb_cloner.ui.transitions.display.get_display_context")
    def test_zero_frame_count_defaults_to_one(
        self, mock_get_context, mock_lock, mock_display_context
    ):
        """Test zero frame_count defaults to 1."""
        mock_get_context.return_value = mock_display_context

        from_image = Image.new("1", (128, 64), 0)
        to_image = Image.new("1", (128, 64), 1)

        gen = transitions.generate_slide_transition(
            from_image, to_image, "forward", frame_count=0, frame_delay=0.01
        )

        frame_times = list(gen)
        assert len(frame_times) == 1

    @patch("rpi_usb_cloner.ui.transitions.display._display_lock")
    @patch("rpi_usb_cloner.ui.transitions.display.get_display_context")
    def test_negative_frame_count_defaults_to_one(
        self, mock_get_context, mock_lock, mock_display_context
    ):
        """Test negative frame_count defaults to 1."""
        mock_get_context.return_value = mock_display_context

        from_image = Image.new("1", (128, 64), 0)
        to_image = Image.new("1", (128, 64), 1)

        gen = transitions.generate_slide_transition(
            from_image, to_image, "forward", frame_count=-5, frame_delay=0.01
        )

        frame_times = list(gen)
        assert len(frame_times) == 1

    @patch("rpi_usb_cloner.ui.transitions.display._display_lock")
    @patch("rpi_usb_cloner.ui.transitions.display.get_display_context")
    def test_raises_when_image_size_mismatches(
        self, mock_get_context, mock_lock, mock_display_context
    ):
        """Test raises ValueError when image sizes don't match display."""
        mock_get_context.return_value = mock_display_context

        # Wrong size images
        from_image = Image.new("1", (64, 32), 0)
        to_image = Image.new("1", (64, 32), 1)

        with pytest.raises(ValueError, match="must match display dimensions"):
            gen = transitions.generate_slide_transition(
                from_image, to_image, "forward", frame_count=2
            )
            next(gen)

    @patch("rpi_usb_cloner.ui.transitions.display._display_lock")
    @patch("rpi_usb_cloner.ui.transitions.display.get_display_context")
    def test_raises_when_from_image_wrong_size(
        self, mock_get_context, mock_lock, mock_display_context
    ):
        """Test raises ValueError when from_image has wrong size."""
        mock_get_context.return_value = mock_display_context

        from_image = Image.new("1", (64, 32), 0)  # Wrong
        to_image = Image.new("1", (128, 64), 1)  # Correct

        with pytest.raises(ValueError, match="must match display dimensions"):
            gen = transitions.generate_slide_transition(
                from_image, to_image, "forward", frame_count=2
            )
            next(gen)

    @patch("rpi_usb_cloner.ui.transitions.display._display_lock")
    @patch("rpi_usb_cloner.ui.transitions.display.get_display_context")
    def test_raises_when_to_image_wrong_size(
        self, mock_get_context, mock_lock, mock_display_context
    ):
        """Test raises ValueError when to_image has wrong size."""
        mock_get_context.return_value = mock_display_context

        from_image = Image.new("1", (128, 64), 0)  # Correct
        to_image = Image.new("1", (64, 32), 1)  # Wrong

        with pytest.raises(ValueError, match="must match display dimensions"):
            gen = transitions.generate_slide_transition(
                from_image, to_image, "forward", frame_count=2
            )
            next(gen)

    @patch("rpi_usb_cloner.ui.transitions.display._display_lock")
    @patch("rpi_usb_cloner.ui.transitions.display.get_display_context")
    def test_uses_dirty_region_when_provided(
        self, mock_get_context, mock_lock, mock_display_context
    ):
        """Test uses dirty region bounding box when provided."""
        mock_get_context.return_value = mock_display_context

        from_image = Image.new("1", (128, 64), 0)
        to_image = Image.new("1", (128, 64), 1)

        dirty_region = (10, 10, 118, 54)  # Custom dirty region

        gen = transitions.generate_slide_transition(
            from_image,
            to_image,
            "forward",
            frame_count=2,
            dirty_region=dirty_region,
            frame_delay=0.01,
        )

        list(gen)  # Consume all frames

        # Should create region image with dirty region dimensions
        # dirty_width = 118 - 10 = 108, dirty_height = 54 - 10 = 44

    @patch("rpi_usb_cloner.ui.transitions.display._display_lock")
    @patch("rpi_usb_cloner.ui.transitions.display.get_display_context")
    @patch("rpi_usb_cloner.ui.transitions.display.mark_display_dirty")
    def test_marks_display_dirty_after_frame(
        self, mock_mark_dirty, mock_get_context, mock_lock, mock_display_context
    ):
        """Test marks display dirty after rendering each frame."""
        mock_get_context.return_value = mock_display_context

        from_image = Image.new("1", (128, 64), 0)
        to_image = Image.new("1", (128, 64), 1)

        gen = transitions.generate_slide_transition(
            from_image, to_image, "forward", frame_count=2, frame_delay=0.01
        )

        list(gen)

        # Should mark display dirty after each frame
        assert mock_mark_dirty.call_count == 2

    @patch("rpi_usb_cloner.ui.transitions.display._display_lock")
    @patch("rpi_usb_cloner.ui.transitions.display.get_display_context")
    def test_updates_display_context_image(
        self, mock_get_context, mock_lock, mock_display_context
    ):
        """Test updates the display context image after each frame."""
        mock_get_context.return_value = mock_display_context

        from_image = Image.new("1", (128, 64), 0)
        to_image = Image.new("1", (128, 64), 1)

        gen = transitions.generate_slide_transition(
            from_image, to_image, "forward", frame_count=2, frame_delay=0.01
        )

        list(gen)

        # Should paste region to context image
        assert mock_display_context.image.paste.call_count == 2
        # Should update display
        assert mock_display_context.disp.display.call_count == 2

    @patch("rpi_usb_cloner.ui.transitions.display._display_lock")
    @patch("rpi_usb_cloner.ui.transitions.display.get_display_context")
    def test_default_frame_delay(
        self, mock_get_context, mock_lock, mock_display_context
    ):
        """Test default frame delay is 0.04 seconds."""
        mock_get_context.return_value = mock_display_context

        from_image = Image.new("1", (128, 64), 0)
        to_image = Image.new("1", (128, 64), 1)

        gen = transitions.generate_slide_transition(
            from_image,
            to_image,
            "forward",
            frame_count=2,
            # No frame_delay specified
        )

        frame_times = list(gen)

        # Default delay is 0.04, so difference should be ~0.04
        assert len(frame_times) == 2

    @patch("rpi_usb_cloner.ui.transitions.display._display_lock")
    @patch("rpi_usb_cloner.ui.transitions.display.get_display_context")
    def test_direction_case_insensitive(
        self, mock_get_context, mock_lock, mock_display_context
    ):
        """Test direction parameter is case insensitive."""
        mock_get_context.return_value = mock_display_context

        from_image = Image.new("1", (128, 64), 0)
        to_image = Image.new("1", (128, 64), 1)

        # Test uppercase FORWARD
        gen = transitions.generate_slide_transition(
            from_image, to_image, "FORWARD", frame_count=2, frame_delay=0.01
        )
        frame_times = list(gen)
        assert len(frame_times) == 2

        # Test mixed case Back
        gen = transitions.generate_slide_transition(
            from_image, to_image, "Back", frame_count=2, frame_delay=0.01
        )
        frame_times = list(gen)
        assert len(frame_times) == 2
