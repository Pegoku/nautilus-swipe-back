"""Two-finger history navigation for Nautilus 4.x, using GTK scroll events."""

import math

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


class SwipeIndicator(Gtk.DrawingArea):
    """A non-interactive overlay that follows the swipe and fades on release."""

    def __init__(self):
        super().__init__()
        self.set_can_target(False)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.FILL)
        self.set_draw_func(self.draw)
        self.distance = 0
        self.fade = 1.0
        self.released = False
        self.tick = 0
        self.set_visible(False)

    def cancel(self):
        if self.tick:
            self.remove_tick_callback(self.tick)
            self.tick = 0
        self.set_visible(False)

    def update(self, distance):
        self.cancel()
        self.distance = distance
        self.fade = 1.0
        self.released = False
        self.set_visible(True)
        self.queue_draw()

    def finish(self, navigated):
        if not self.get_visible():
            return
        self.released = navigated
        if not self.get_settings().get_property("gtk-enable-animations"):
            self.cancel()
            return
        self.start_time = None
        self.tick = self.add_tick_callback(self.animate)

    def animate(self, widget, clock):
        now = clock.get_frame_time()
        if self.start_time is None:
            self.start_time = now
        self.fade = max(0.0, 1.0 - (now - self.start_time) / 180_000)
        self.queue_draw()
        if self.fade == 0:
            self.tick = 0
            self.set_visible(False)
            return False
        return True

    def draw(self, area, cr, width, height):
        progress = min(abs(self.distance) / Swipe.THRESHOLD, 1.0)
        ready = progress >= 1.0
        eased = 1.0 - (1.0 - progress) ** 2
        offset = 16 + 52 * eased
        # A cancelled swipe retreats to its edge; a completed swipe pulses.
        if not self.released:
            offset *= self.fade
        x = offset if self.distance > 0 else width - offset
        y = height / 2
        radius = 20 + (3 * (1 - self.fade) if self.released else 0)
        found, accent = self.get_style_context().lookup_color("accent_bg_color")
        rgb = (accent.red, accent.green, accent.blue) if found else (0.20, 0.52, 0.89)
        alpha = self.fade * min(progress * 3, 1.0)
        cr.set_source_rgba(*rgb, 0.17 * alpha)
        cr.arc(x, y, radius + 10, 0, math.tau)
        cr.fill()
        cr.set_source_rgba(*rgb, (1.0 if ready else 0.65) * alpha)
        cr.arc(x, y, radius, 0, math.tau)
        cr.fill()
        if ready:
            found, fg = self.get_style_context().lookup_color("accent_fg_color")
            foreground = (fg.red, fg.green, fg.blue) if found else (1, 1, 1)
        else:
            foreground = (1, 1, 1)
        cr.set_source_rgba(*foreground, alpha)
        cr.set_line_width(2)
        cr.set_line_cap(1)  # CAIRO_LINE_CAP_ROUND
        direction = -1 if self.distance > 0 else 1
        cr.move_to(x - direction * 5, y)
        cr.line_to(x + direction * 5, y)
        cr.move_to(x, y - 4)
        cr.line_to(x + direction * 5, y)
        cr.line_to(x, y + 4)
        cr.stroke()


class WindowSwipe:
    def __init__(self, window):
        self.swipe = Swipe()
        self.target = None
        self.indicator = None
        self.controller = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.BOTH_AXES
        )
        self.controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.controller.connect("scroll-begin", self.begin)
        self.controller.connect("scroll", self.scroll)
        self.controller.connect("scroll-end", self.end)
        window.add_controller(self.controller)

    def begin(self, controller):
        if self.indicator is not None:
            self.indicator.cancel()
        self.indicator = None
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
            window = controller.get_widget()
            surface = window.get_surface()
            pointer = surface.get_display().get_default_seat().get_pointer()
            # Scroll events have no coordinates in GTK 4. Query the seat's
            # logical pointer, not the separate finger-scrolling device.
            inside, x, y, _state = surface.get_device_position(pointer)
            if not inside:
                return False
            offset_x, offset_y = window.get_surface_transform()
            widget = window.pick(x + offset_x, y + offset_y, Gtk.PickFlags.DEFAULT)
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
        horizontal = self.swipe.update(dx, dy)
        if horizontal:
            if self.indicator is None:
                self.indicator = self.get_indicator(self.target)
            if self.indicator is not None:
                self.indicator.update(self.swipe.x)
        return horizontal

    @staticmethod
    def get_indicator(target):
        # Nautilus already overlays the file view for its floating status bar.
        # Add a pass-through drawing layer without reparenting any of its UI.
        overlay = target.get_first_child()
        if not isinstance(overlay, Gtk.Overlay):
            return None
        if not hasattr(target, "_swipe_indicator"):
            indicator = SwipeIndicator()
            overlay.add_overlay(indicator)
            overlay.set_measure_overlay(indicator, False)
            overlay.set_clip_overlay(indicator, True)
            target._swipe_indicator = indicator
        return target._swipe_indicator

    def end(self, controller):
        action = self.swipe.finish()
        target = self.target
        indicator = self.indicator
        self.indicator = None
        self.begin(controller)
        if indicator is not None:
            indicator.finish(action is not None)
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
