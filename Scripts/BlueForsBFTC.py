"""QCoDeS driver for a BlueFors fridge via the Temperature Control REST API.

This talks to the BlueFors "Temperature Control" software HTTP API (default
port 5001) -- temperatures *and* heater control. It is distinct from
``qcodes_contrib_drivers``' ``BlueFors`` driver, which instead reads the on-disk
CSV log files and has no heater control.

Thermometer channels are exposed both by named fridge stage (e.g. ``bftc.mxc``)
and by raw channel number via :meth:`BlueForsBFTC.get_temperature`.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

import requests

from qcodes import validators as vals
from qcodes.instrument import ChannelList, Instrument, InstrumentChannel

__all__ = ["BlueForsBFTC", "BlueForsThermometerChannel", "BlueForsHeaterChannel"]

# Default BlueFors thermometer channel -> fridge stage name.
# Override via the ``thermometer_channels`` kwarg for your system.
DEFAULT_THERMOMETER_CHANNELS: dict[int, str] = {
    1: "50k",
    2: "4k",
    5: "still",
    6: "mxc",
}


class BlueForsThermometerChannel(InstrumentChannel):
    """One fridge thermometer (read-only): temperature, resistance, reactance."""

    def __init__(
        self,
        parent: "BlueForsBFTC",
        name: str,
        channel_nr: int,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, name, **kwargs)
        self.channel_nr = channel_nr

        self.temperature: Any = self.add_parameter(
            "temperature",
            unit="K",
            label=f"{name} temperature",
            get_cmd=lambda: parent._fetch_channel(channel_nr)["temperature"],
        )
        self.resistance: Any = self.add_parameter(
            "resistance",
            unit="Ohm",
            label=f"{name} resistance",
            get_cmd=lambda: parent._fetch_channel(channel_nr)["resistance"],
        )
        self.reactance: Any = self.add_parameter(
            "reactance",
            unit="Ohm",
            label=f"{name} reactance",
            get_cmd=lambda: parent._fetch_channel(channel_nr)["reactance"],
        )


class BlueForsHeaterChannel(InstrumentChannel):
    """A fridge heater. ``power`` is a real settable parameter (sweep/stabilise T).

    The REST API has no documented power read-back here, so ``power``/``active``
    report the last value this driver set (cached).
    """

    def __init__(
        self,
        parent: "BlueForsBFTC",
        name: str,
        heater_nr: int,
        max_power: float = 0.3,
        pid_mode: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, name, **kwargs)
        self._bftc = parent
        self.heater_nr = heater_nr
        self._max_power = max_power
        self._pid_mode = pid_mode
        self._power = 0.0
        self._active = False
        self._setpoint = 0.0

        self.max_power: Any = self.add_parameter(
            "max_power",
            unit="W",
            label=f"{name} max power",
            get_cmd=lambda: self._max_power,
            set_cmd=self._set_max_power,
            vals=vals.Numbers(0),
        )
        self.power: Any = self.add_parameter(
            "power",
            unit="W",
            label=f"{name} power",
            get_cmd=lambda: self._power,
            set_cmd=self._set_power,
            vals=vals.Numbers(0, max_power),
        )
        self.active: Any = self.add_parameter(
            "active",
            label=f"{name} active",
            get_cmd=lambda: self._active,
            set_cmd=self._set_active,
            vals=vals.Bool(),
        )
        self.setpoint: Any = self.add_parameter(
            "setpoint",
            unit="K",
            label=f"{name} PID setpoint",
            get_cmd=lambda: self._setpoint,
            set_cmd=self._set_setpoint,
            vals=vals.Numbers(0),
        )

    def _post(self, active: bool, power: float) -> None:
        self._bftc._heater_update(
            heater_nr=self.heater_nr,
            active=active,
            pid_mode=self._pid_mode,
            power=power,
            max_power=self._max_power,
        )

    def _set_max_power(self, value: float) -> None:
        self._max_power = value

    def _set_power(self, power: float) -> None:
        power = min(power, self._max_power)
        self._post(active=True, power=power)
        self._power = power
        self._active = True

    def _set_active(self, on: bool) -> None:
        if on:
            self._post(active=True, power=self._power)
        else:
            self._post(active=False, power=0.0)
            self._power = 0.0
        self._active = bool(on)

    def _set_setpoint(self, value: float) -> None:
        """Engage PID temperature control at ``value`` K.

        Posts exactly what the lab's ``set_pid_temp`` does -- ``{heater_nr,
        active, pid_mode:1, setpoint}`` with NO power/max_power, so the PID
        loop isn't fought by a stray power=0.
        """
        self._bftc._heater_update(
            heater_nr=self.heater_nr,
            active=True,
            pid_mode=1,
            setpoint=value,
        )
        self._setpoint = value
        self._active = True

    def on(self) -> None:
        self.active(True)

    def off(self) -> None:
        self.active(False)


class BlueForsBFTC(Instrument):
    """BlueFors fridge, controlled over the Temperature Control REST API.

    Args:
        name: QCoDeS instrument name.
        address: fridge controller IP address (e.g. ``"169.254.27.31"``).
        port: REST API port (default 5001).
        thermometer_channels: ``{channel_nr: stage_name}``. Defaults to
            ``{1:'50k', 2:'4k', 5:'still', 6:'mxc'}``.
        heater_channels: ``{heater_nr: name}``. Defaults to ``{4: 'heater'}``.
        max_power: default heater max power (W).
        tz_delta: hours of slack each side of "now" when querying the historical
            endpoint (matches the original notebook helper).
        retries / retry_wait / timeout: HTTP retry policy.
        cache_max_age: reuse a channel's last reading for this many seconds to
            avoid hammering the API when several parameters are read together.
    """

    def __init__(
        self,
        name: str,
        address: str,
        port: int = 5001,
        thermometer_channels: dict[int, str] | None = None,
        heater_channels: dict[int, str] | None = None,
        max_power: float = 0.3,
        tz_delta: float = 4.0,
        retries: int = 3,
        retry_wait: float = 2.0,
        timeout: float = 5.0,
        cache_max_age: float = 1.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(name, **kwargs)

        self._ip = address
        self._port = port
        self._tz_delta = tz_delta
        self._retries = retries
        self._retry_wait = retry_wait
        self._timeout = timeout
        self._cache_max_age = cache_max_age
        self._data_cache: dict[int, tuple[dict[str, float], float]] = {}

        if thermometer_channels is None:
            thermometer_channels = dict(DEFAULT_THERMOMETER_CHANNELS)
        if heater_channels is None:
            heater_channels = {4: "heater"}

        thermometers = ChannelList(
            self, "thermometers", BlueForsThermometerChannel, snapshotable=True
        )
        for ch_nr, stage in thermometer_channels.items():
            chan = BlueForsThermometerChannel(self, stage, ch_nr)
            self.add_submodule(stage, chan)  # named access: bftc.mxc
            thermometers.append(chan)
        self.add_submodule("thermometers", thermometers.to_channel_tuple())

        heaters = ChannelList(self, "heaters", BlueForsHeaterChannel, snapshotable=True)
        for h_nr, h_name in heater_channels.items():
            heater = BlueForsHeaterChannel(self, h_name, h_nr, max_power=max_power)
            self.add_submodule(h_name, heater)
            heaters.append(heater)
        self.add_submodule("heaters", heaters.to_channel_tuple())

        self.connect_message()

    # --- HTTP plumbing -----------------------------------------------------
    def _fetch_channel(self, channel_nr: int) -> dict[str, float]:
        """Return the latest {temperature, resistance, reactance, timestamp}."""
        cached = self._data_cache.get(channel_nr)
        if cached is not None and (time.monotonic() - cached[1]) < self._cache_max_age:
            return cached[0]

        url = f"http://{self._ip}:{self._port}/channel/historical-data"
        start = (datetime.now() - timedelta(hours=self._tz_delta)).replace(
            microsecond=0
        ).isoformat() + "Z"
        stop = (datetime.now() + timedelta(hours=self._tz_delta)).replace(
            microsecond=0
        ).isoformat() + "Z"
        payload = {
            "channel_nr": int(channel_nr),
            "start_time": start,
            "stop_time": stop,
            "fields": ["temperature", "resistance", "reactance"],
        }

        last_exc: Exception | None = None
        for attempt in range(self._retries):
            try:
                resp = requests.post(url, json=payload, timeout=self._timeout)
                meas = resp.json()["measurements"]
                data = {f: meas[f][-1] for f in ("temperature", "resistance", "reactance")}
                data["timestamp"] = meas["timestamp"][-1]
                self._data_cache[channel_nr] = (data, time.monotonic())
                return data
            except Exception as exc:  # noqa: BLE001 - network/parse errors all retry
                last_exc = exc
                if attempt < self._retries - 1:
                    time.sleep(self._retry_wait)

        if channel_nr in self._data_cache:
            self.log.warning(
                "Channel %s read failed (%s); returning last known value.",
                channel_nr,
                last_exc,
            )
            return self._data_cache[channel_nr][0]
        raise RuntimeError(
            f"BlueForsBFTC: failed to read channel {channel_nr} and no cached "
            f"value available: {last_exc}"
        )

    def _heater_update(
        self,
        heater_nr: int,
        active: bool,
        pid_mode: int,
        power: float | None = None,
        max_power: float | None = None,
        setpoint: float | None = None,
    ) -> None:
        url = f"http://{self._ip}:{self._port}/heater/update"
        payload: dict[str, Any] = {
            "heater_nr": heater_nr,
            "active": active,
            "pid_mode": pid_mode,
        }
        # PID temperature control vs manual power are distinct payloads -- send
        # only the fields the lab's helpers send for each (don't mix them).
        if setpoint is not None:
            payload["setpoint"] = setpoint
        else:
            payload["power"] = power
            payload["max_power"] = max_power
        requests.post(url, json=payload, timeout=max(self._timeout, 30))

    # --- generic access ----------------------------------------------------
    def get_temperature(self, channel_nr: int) -> float:
        """Temperature (K) of any channel by number, even if not pre-configured."""
        return self._fetch_channel(channel_nr)["temperature"]

    def get_idn(self) -> dict[str, str | None]:
        return {
            "vendor": "BlueFors",
            "model": "Temperature Control (REST API)",
            "serial": self._ip,
            "firmware": None,
        }

if __name__=='__main__':
    print('BFTC library')
    # Connect to BFTC
    APIkey = '7813ae93-31d7-4305-8e3b-8ded96422bc6'
    bftc = BlueForsBFTC("bftc", "169.254.11.150")
    print(f'Mixing chamber temperature: {bftc.mxc.temperature():.3f}')