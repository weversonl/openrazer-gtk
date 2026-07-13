"""AppDeviceManager: polls the OpenRazer daemon and exposes GObject signals.

No hotplug D-Bus signal exists in python-openrazer, so device add/remove is
detected by re-instantiating DeviceManager() on a timer and diffing serials.

D-Bus calls to this daemon can take 5+ seconds intermittently (wireless
dongle latency) - every scan/write here runs on a background thread with
results marshaled back via GLib.idle_add. Never call dbus/openrazer methods
directly from a widget constructor.
"""

import logging
import threading

import dbus
from gi.repository import GLib, GObject
from openrazer.client import DeviceManager
from openrazer.client.device_manager import DaemonNotFound

from razer_gtk.backend import device_adapter as da
from razer_gtk.backend.errors import describe_write_error

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5


def _scan_devices() -> tuple[bool, str | None, dict[str, da.DeviceCapabilities]]:
    """Pure, blocking scan - runs on a background thread. Returns
    (daemon_available, daemon_version, capabilities_by_serial)."""
    try:
        dm = DeviceManager()
    except DaemonNotFound:
        return False, None, {}

    capabilities: dict[str, da.DeviceCapabilities] = {}
    for device in dm.devices:
        try:
            capabilities[device.serial] = da.from_device(device)
        except Exception:
            logger.exception("Failed to build capabilities for device %s", device.serial)
    return True, dm.daemon_version, capabilities


class AppDeviceManager(GObject.Object):
    """Owns the connection to the daemon, capability caches, and polling."""

    __gsignals__ = {
        "devices-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "device-state-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "backend-status-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "scanning-changed": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
    }

    def __init__(self) -> None:
        super().__init__()
        self._capabilities: dict[str, da.DeviceCapabilities] = {}
        self._volatile_state: dict[str, tuple[int, bool]] = {}
        self._daemon_available = False
        self._daemon_version: str | None = None
        self._selected_serial: str | None = None
        self._poll_source_id: int | None = None
        self._scan_in_flight = False

        self.rescan_async()

    def start_polling(self) -> None:
        if self._poll_source_id is None:
            self._poll_source_id = GLib.timeout_add_seconds(POLL_INTERVAL_SECONDS, self._on_poll_tick)

    def stop_polling(self) -> None:
        if self._poll_source_id is not None:
            GLib.source_remove(self._poll_source_id)
            self._poll_source_id = None

    @property
    def daemon_available(self) -> bool:
        return self._daemon_available

    @property
    def daemon_version(self) -> str | None:
        return self._daemon_version

    @property
    def scanning(self) -> bool:
        return self._scan_in_flight

    @property
    def devices(self) -> list[da.DeviceCapabilities]:
        return list(self._capabilities.values())

    def get_capabilities(self, serial: str) -> da.DeviceCapabilities | None:
        return self._capabilities.get(serial)

    def select_device(self, serial: str | None) -> None:
        self._selected_serial = serial

    def prefetch_snapshot_async(self, serial: str, on_ready) -> None:
        """Read a device's current values on a background thread, then call
        `on_ready(snapshot_dict)` on the main thread."""
        caps = self._capabilities.get(serial)
        if caps is None:
            GLib.idle_add(on_ready, {})
            return

        def worker() -> None:
            try:
                snapshot = da.fetch_live_snapshot(caps)
            except Exception:
                logger.exception("prefetch_snapshot_async failed for %s", serial)
                snapshot = {}
            GLib.idle_add(on_ready, snapshot)

        threading.Thread(target=worker, daemon=True).start()

    def rescan_async(self) -> None:
        """Kick off a full re-scan on a background thread."""
        if self._scan_in_flight:
            return
        self._scan_in_flight = True
        self.emit("scanning-changed", True)

        def worker() -> None:
            result = _scan_devices()
            GLib.idle_add(self._apply_scan_result, *result)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_scan_result(
        self, daemon_available: bool, daemon_version: str | None, capabilities: dict[str, da.DeviceCapabilities]
    ) -> bool:
        was_available = self._daemon_available
        old_serials = set(self._capabilities.keys())

        self._daemon_available = daemon_available
        self._daemon_version = daemon_version
        self._capabilities = capabilities
        self._scan_in_flight = False

        new_serials = set(capabilities.keys())

        self.emit("scanning-changed", False)
        if daemon_available != was_available:
            self.emit("backend-status-changed")
        if new_serials != old_serials:
            self.emit("devices-changed")
        return GLib.SOURCE_REMOVE

    def _poll_serials(self) -> set[str] | None:
        """Cheap hotplug check: just the device-serial list. None if unreachable."""
        try:
            bus = dbus.SessionBus()
            devices_obj = bus.get_object("org.razer", "/org/razer")
            devices_iface = dbus.Interface(devices_obj, "razer.devices")
            return {str(s) for s in devices_iface.getDevices()}
        except dbus.DBusException:
            return None

    def _on_poll_tick(self) -> bool:
        if self._scan_in_flight:
            return GLib.SOURCE_CONTINUE

        def worker() -> None:
            serials = self._poll_serials()
            GLib.idle_add(self._apply_poll_result, serials)

        threading.Thread(target=worker, daemon=True).start()
        return GLib.SOURCE_CONTINUE

    def _apply_poll_result(self, serials: set[str] | None) -> bool:
        if serials is None:
            if self._daemon_available:
                self.rescan_async()
        elif serials != set(self._capabilities.keys()) or not self._daemon_available:
            self.rescan_async()
        else:
            if self._selected_serial is not None:
                self._refresh_volatile_state_async(self._selected_serial)
        return GLib.SOURCE_REMOVE

    def _refresh_volatile_state_async(self, serial: str) -> None:
        caps = self._capabilities.get(serial)
        if caps is None or not caps.supports_battery:
            return

        def worker() -> None:
            try:
                level = caps.device.battery_level
                charging = caps.device.is_charging
                ok = True
            except dbus.DBusException:
                ok = False
                level = charging = None
            GLib.idle_add(self._apply_volatile_state, serial, ok, level, charging)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_volatile_state(self, serial: str, ok: bool, level, charging) -> bool:
        if not ok:
            logger.warning("Failed to refresh volatile state for %s", serial)
            return GLib.SOURCE_REMOVE
        self._volatile_state[serial] = (level, charging)
        self.emit("device-state-changed", serial)
        return GLib.SOURCE_REMOVE

    def get_volatile_state(self, serial: str) -> tuple[int, bool] | None:
        """Latest polled (battery_level, is_charging) for `serial`, if any."""
        return self._volatile_state.get(serial)

    def _try_write(self, fn) -> tuple[str | None, bool]:
        """Thread-safe: attempt fn(), translate any daemon error.
        Returns (error_message_or_None, daemon_went_away)."""
        try:
            fn()
            return None, False
        except DaemonNotFound as exc:
            logger.error("Daemon unavailable during write: %s", exc)
            return describe_write_error(exc), True
        except dbus.DBusException as exc:
            logger.error("D-Bus write failed: %s", exc)
            return describe_write_error(exc), False
        except (ValueError, NotImplementedError) as exc:
            logger.error("Invalid write: %s", exc)
            return describe_write_error(exc), False

    def perform_write(self, fn) -> str | None:
        """Synchronous write - blocks until the D-Bus call returns. Only for
        deliberate, infrequent single-shot actions (e.g. a Save button);
        anything triggered from normal navigation must use `perform_write_async`."""
        error, daemon_gone = self._try_write(fn)
        if daemon_gone:
            self._daemon_available = False
            self.emit("backend-status-changed")
        return error

    def perform_write_async(self, fn, on_done) -> None:
        """Run fn() on a background thread; call `on_done(error_or_None)` on the main thread."""

        def worker() -> None:
            error, daemon_gone = self._try_write(fn)
            GLib.idle_add(self._deliver_write_result, error, daemon_gone, on_done)

        threading.Thread(target=worker, daemon=True).start()

    def _deliver_write_result(self, error: str | None, daemon_gone: bool, on_done) -> bool:
        if daemon_gone:
            self._daemon_available = False
            self.emit("backend-status-changed")
        on_done(error)
        return GLib.SOURCE_REMOVE
