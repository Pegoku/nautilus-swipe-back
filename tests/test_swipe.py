import unittest
from unittest.mock import Mock, patch

from nautilus_swipe_back import Gdk, Gtk, Swipe, WindowSwipe


class SwipeTests(unittest.TestCase):
    def test_horizontal_motion_navigates_in_both_directions(self):
        for dx, action in ((25, "slot.forward"), (-25, "slot.back")):
            with self.subTest(action=action):
                swipe = Swipe()
                for _ in range(5):
                    self.assertTrue(swipe.update(dx, 1))
                self.assertEqual(swipe.finish(), action)

    def test_short_swipe_and_diagonal_scroll_do_not_navigate(self):
        for deltas in ([(45, 2)], [(20, 20)] * 10, [(2, 25)] * 10):
            swipe = Swipe()
            for dx, dy in deltas:
                swipe.update(dx, dy)
            self.assertIsNone(swipe.finish())

    def test_vertical_scroll_cannot_turn_into_back_navigation(self):
        swipe = Swipe()
        self.assertFalse(swipe.update(1, 30))
        self.assertFalse(swipe.update(200, 0))
        self.assertIsNone(swipe.finish())

    def test_reversing_before_release_cancels_navigation(self):
        swipe = Swipe()
        swipe.update(140, 0)
        swipe.update(-90, 0)
        self.assertIsNone(swipe.finish())


class ControllerTests(unittest.TestCase):
    def setUp(self):
        # Avoid opening a desktop window during unit tests.
        self.binding = WindowSwipe.__new__(WindowSwipe)
        self.binding.indicator = None
        self.binding.get_indicator = Mock(return_value=Mock())
        self.binding.action_available = Mock(return_value=True)
        self.controller = Mock()
        self.binding.begin(self.controller)
        self.target = Mock()
        self.binding.target = self.target
        self.event = self.controller.get_current_event.return_value
        self.event.get_unit.return_value = Gdk.ScrollUnit.SURFACE
        self.event.get_device.return_value.get_source.return_value = Gdk.InputSource.TOUCHPAD
        self.event.get_relative_direction.return_value = Gdk.ScrollRelativeDirection.INVERTED
        self.controller.get_current_event_state.return_value = Gdk.ModifierType(0)

    def test_natural_scrolling_normalizes_to_physical_finger_direction(self):
        self.assertTrue(self.binding.scroll(self.controller, -120, 0))
        self.target.activate_action.assert_not_called()
        self.binding.end(self.controller)
        self.target.activate_action.assert_called_once_with("slot.forward", None)
        # A repeated end event or inertia cannot repeat navigation.
        self.binding.end(self.controller)
        self.target.activate_action.assert_called_once()

    def test_non_natural_left_swipe_goes_back(self):
        self.event.get_relative_direction.return_value = Gdk.ScrollRelativeDirection.IDENTICAL
        self.binding.scroll(self.controller, -120, 0)
        self.binding.end(self.controller)
        self.target.activate_action.assert_called_once_with("slot.back", None)

    def test_mouse_wheels_and_modified_scrolling_do_not_navigate(self):
        cases = ("wheel", "mouse", "ctrl", "shift")
        for case in cases:
            with self.subTest(case=case):
                self.setUp()
                if case == "wheel":
                    self.event.get_unit.return_value = Gdk.ScrollUnit.WHEEL
                elif case == "mouse":
                    self.event.get_device.return_value.get_source.return_value = Gdk.InputSource.MOUSE
                else:
                    self.controller.get_current_event_state.return_value = (
                        Gdk.ModifierType.CONTROL_MASK if case == "ctrl" else Gdk.ModifierType.SHIFT_MASK
                    )
                self.assertFalse(self.binding.scroll(self.controller, -200, 0))
                self.binding.end(self.controller)
                self.target.activate_action.assert_not_called()

    def test_vertical_scroll_is_passed_through(self):
        self.assertFalse(self.binding.scroll(self.controller, -2, -200))
        self.binding.end(self.controller)
        self.target.activate_action.assert_not_called()

    def test_indicator_tracks_swipe_and_completes_on_release(self):
        indicator = self.binding.get_indicator.return_value
        self.binding.scroll(self.controller, -120, 0)
        indicator.update.assert_called_once_with(120)
        self.binding.end(self.controller)
        indicator.finish.assert_called_once_with(True)

    def test_short_swipe_animates_cancellation_without_navigation(self):
        indicator = self.binding.get_indicator.return_value
        self.binding.scroll(self.controller, -40, 0)
        self.binding.end(self.controller)
        indicator.finish.assert_called_once_with(False)
        self.target.activate_action.assert_not_called()

    def test_vertical_scroll_does_not_show_indicator(self):
        self.binding.scroll(self.controller, 0, -120)
        self.binding.get_indicator.assert_not_called()

    def test_coordinate_less_scroll_uses_surface_pointer_to_find_file_view(self):
        self.binding.target = None
        # Actual GdkScrollEvents always return False and NaN coordinates.
        self.event.get_position.return_value = (False, float("nan"), float("nan"))
        window = self.controller.get_widget.return_value
        surface = window.get_surface.return_value
        pointer = surface.get_display.return_value.get_default_seat.return_value.get_pointer.return_value
        surface.get_device_position.return_value = (True, 340, 200, 0)
        window.get_surface_transform.return_value = (-10, -10)
        window.pick.return_value = self.target
        with patch("nautilus_swipe_back.GObject.type_name", return_value="NautilusFilesView"):
            self.assertTrue(self.binding.scroll(self.controller, -120, 0))
        surface.get_device_position.assert_called_once_with(pointer)
        window.pick.assert_called_once_with(330, 190, Gtk.PickFlags.DEFAULT)
        self.event.get_position.assert_not_called()
        self.binding.end(self.controller)
        self.target.activate_action.assert_called_once_with("slot.forward", None)

    def test_pointer_outside_window_does_not_start_swipe(self):
        self.binding.target = None
        surface = self.controller.get_widget.return_value.get_surface.return_value
        surface.get_device_position.return_value = (False, 0, 0, 0)
        self.assertFalse(self.binding.scroll(self.controller, -120, 0))
        self.binding.get_indicator.assert_not_called()

    def test_missing_direction_metadata_uses_natural_scrolling(self):
        self.event.get_relative_direction.return_value = Gdk.ScrollRelativeDirection.UNKNOWN
        self.binding.scroll(self.controller, -120, 0)
        self.binding.end(self.controller)
        self.target.activate_action.assert_called_once_with("slot.forward", None)

    def test_unavailable_history_has_no_arrow_or_navigation(self):
        for dx, action in ((-120, "slot.forward"), (120, "slot.back")):
            with self.subTest(action=action):
                self.setUp()
                self.binding.action_available.return_value = False
                self.assertTrue(self.binding.scroll(self.controller, dx, 0))
                self.binding.action_available.assert_called_with(action)
                self.binding.get_indicator.assert_not_called()
                self.binding.end(self.controller)
                self.target.activate_action.assert_not_called()

    def test_history_disabled_before_release_cancels_navigation(self):
        self.binding.scroll(self.controller, -120, 0)
        self.binding.action_available.return_value = False
        self.binding.end(self.controller)
        self.target.activate_action.assert_not_called()
        self.binding.get_indicator.return_value.finish.assert_called_once_with(False)


if __name__ == "__main__":
    unittest.main()
