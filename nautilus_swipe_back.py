"""Two-finger history navigation for Nautilus 4.x, using GTK scroll events."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Nautilus", "4.1")
from gi.repository import Gdk, GObject, Gtk, Nautilus


class Swipe:
    """Lock each touchpad sequence to its initial intentional axis."""

    THRESHOLD = 100  # GTK logical surface pixels
    AXIS_THRESHOLD = 12
    AXIS_RATIO = 1.5

    def __init__(self):
        self.x = self.y = 0.0
        self.axis = None

    def update(self, dx, dy):
        self.x += dx
        self.y += dy
        if self.axis is None:
            if abs(self.y) >= self.AXIS_THRESHOLD and abs(self.y) >= abs(self.x):
                self.axis = "vertical"
            elif (
                abs(self.x) >= self.AXIS_THRESHOLD
                and abs(self.x) >= self.AXIS_RATIO * abs(self.y)
            ):
                self.axis = "horizontal"
        return self.axis == "horizontal"

    def finish(self):
        if self.axis == "horizontal" and abs(self.x) >= self.THRESHOLD:
            return "slot.back" if self.x > 0 else "slot.forward"
        return None


class WindowSwipe:
    def __init__(self, window):
        self.swipe = Swipe()
        self.target = None
        self.controller = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.BOTH_AXES
        )
        self.controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.controller.connect("scroll-begin", self.begin)
        self.controller.connect("scroll", self.scroll)
        self.controller.connect("scroll-end", self.end)
        window.add_controller(self.controller)

    def begin(self, controller):
        self.swipe = Swipe()
        self.target = None

    def scroll(self, controller, dx, dy):
        event = controller.get_current_event()
        if (
            event is None
            or event.get_unit() != Gdk.ScrollUnit.SURFACE
            or event.get_device().get_source() != Gdk.InputSource.TOUCHPAD
            or controller.get_current_event_state()
            & Gtk.accelerator_get_default_mod_mask()
        ):
            # Modified scrolling (for example Ctrl+scroll zoom) stays native.
            self.begin(controller)
            return False

        if self.target is None:
            valid, x, y = event.get_position()
            if not valid:
                return False
            widget = controller.get_widget().pick(x, y, Gtk.PickFlags.DEFAULT)
            while widget is not None:
                if GObject.type_name(widget) == "NautilusFilesView":
                    self.target = widget
                    break
                widget = widget.get_parent()
            if self.target is None:
                return False

        # Normalize to physical finger motion, independently of natural scrolling.
        if event.get_relative_direction() == Gdk.ScrollRelativeDirection.INVERTED:
            dx, dy = -dx, -dy
        return self.swipe.update(dx, dy)

    def end(self, controller):
        action = self.swipe.finish()
        target = self.target
        self.begin(controller)
        if target is not None and action is not None:
            target.activate_action(action, None)


class SwipeNavigation(GObject.GObject, Nautilus.MenuProvider):
    def __init__(self):
        super().__init__()
        self.windows = Gtk.Window.get_toplevels()
        self.windows.connect("items-changed", self.windows_changed)
        self.windows_changed(self.windows, 0, 0, self.windows.get_n_items())

    def windows_changed(self, windows, position, removed, added):
        for index in range(position, position + added):
            window = windows.get_item(index)
            if GObject.type_name(window) == "NautilusWindow":
                if not hasattr(window, "_swipe_navigation"):
                    window._swipe_navigation = WindowSwipe(window)

    def get_file_items(self, files):
        return []

    def get_background_items(self, current_folder):
        return []
