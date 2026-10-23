# Nautilus swipe navigation

A per-user Nautilus Python extension. Swipe two fingers right over the file
area to go back, or left to go forward. Navigation happens when you lift your
fingers after at least 100 logical pixels. Vertical scrolling, the sidebar,
mouse wheels, Ctrl+scroll zoom, and desktop workspace gestures keep their
normal behavior. A circular arrow slides in from the corresponding edge as
you swipe and lights up at the navigation threshold. On release it pulses
and fades, or retreats if the swipe was cancelled. It follows the desktop
accent color and respects the GTK reduced-animation setting.

Requires Nautilus with nautilus-python, PyGObject, and GTK 4.20 or newer.
Tested against the installed Nautilus 51.1 and GTK 4.24 on Hyprland/Wayland.
This uses Nautilus's internal widget names and actions, which may change in
future releases.

## Install

```sh
mkdir -p ~/.local/share/nautilus-python/extensions
ln -s "$PWD/nautilus_swipe_back.py" ~/.local/share/nautilus-python/extensions/nautilus_swipe_back.py
```

Close and reopen Nautilus after quitting its background process with
`nautilus --quit`. Finish any file transfers first. Existing windows must
restart to load Python extensions.

## Remove

Delete `~/.local/share/nautilus-python/extensions/nautilus_swipe_back.py` and
restart Nautilus.

## Verify

```sh
/usr/bin/python -m unittest discover -s tests -v
```
