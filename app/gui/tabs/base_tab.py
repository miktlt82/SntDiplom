"""Abstract base tab class."""

from __future__ import annotations
from abc import ABC, abstractmethod
import customtkinter as ctk

from app.event_bus import event_bus


class BaseTab(ABC):
    """Base class for all tabs."""

    def __init__(self, app):
        self.app = app
        self.frame: ctk.CTkFrame | None = None
        self._subscriptions: list[tuple[str, callable]] = []

    def build(self, parent_frame: ctk.CTkFrame):
        self.frame = parent_frame
        self._build_ui()
        self._subscribe_events()
        self.refresh_data()

    @abstractmethod
    def _build_ui(self):
        pass

    @abstractmethod
    def refresh_data(self):
        pass

    def _subscribe_events(self):
        """Override to subscribe to events."""
        self._subscribe("database_changed", lambda **kw: self.refresh_data())
        self._subscribe("theme_changed", lambda **kw: self._on_theme_changed())

    def _subscribe(self, event: str, callback):
        event_bus.subscribe(event, callback)
        self._subscriptions.append((event, callback))

    def _on_theme_changed(self):
        """Override for theme-specific updates."""
        pass

    def destroy(self):
        """Unsubscribe all event handlers to prevent leaks."""
        for ev, cb in self._subscriptions:
            event_bus.unsubscribe(ev, cb)
        self._subscriptions.clear()

    def set_status(self, message: str):
        event_bus.publish("status_message", message=message)
