"""
Helpers for layouts that adapt to the window size.

Tk fires <Configure> dozens of times per second while you drag a window
edge; re-laying-out on every one of those is what makes resizing feel
janky. on_resize() waits until the size has settled for a moment and then
calls back once, with sizes in logical pixels (Windows display scaling
already divided out) so breakpoints mean the same thing on every screen.
"""

import tkinter

import customtkinter as ctk


def scaling(widget):
    try:
        return ctk.ScalingTracker.get_widget_scaling(widget)
    except Exception:
        return 1.0


def on_resize(widget, callback, delay_ms=60):
    state = {"job": None, "size": None}

    def fire():
        state["job"] = None
        s = scaling(widget)
        callback(widget.winfo_width() / s, widget.winfo_height() / s)

    def handler(event):
        if event.widget is not widget:   # on a window, child widgets' events bubble up too
            return
        size = (event.width, event.height)
        if size == state["size"]:
            return
        state["size"] = size
        if state["job"] is not None:
            widget.after_cancel(state["job"])
        state["job"] = widget.after(delay_ms, fire)

    # Bind on the underlying Tk frame (CTk's own bind() targets an inner
    # canvas) and with add="+" so CTk's internal resize handler survives.
    tkinter.Misc.bind(widget, "<Configure>", handler, "+")
