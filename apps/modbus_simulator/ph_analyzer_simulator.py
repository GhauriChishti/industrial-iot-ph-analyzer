"""Async Modbus TCP simulator for an industrial pH analyzer.

This module exposes a Modbus TCP server with holding-register values that
represent a pH analyzer's measurements and state.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import signal
from dataclasses import dataclass

from pymodbus.datastore import ModbusDeviceContext, ModbusSequentialDataBlock, ModbusServerContext
from pymodbus.server import StartAsyncTcpServer

LOGGER = logging.getLogger("ph_analyzer_simulator")

HOST = "0.0.0.0"
PORT = 5020
UPDATE_INTERVAL_SECONDS = 1.0

REG_PH = 0
REG_TEMPERATURE = 1
REG_STATUS = 2
REG_ALARM = 3
REG_HEALTH = 4


@dataclass
class AnalyzerState:
    """In-memory state for the simulated analyzer."""

    ph: float = 7.2
    temperature_c: float = 25.0
    status: int = 1
    alarm: int = 0
    health_percent: int = 100


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _calculate_alarm(ph: float, temperature_c: float) -> int:
    if temperature_c < 5 or temperature_c > 45:
        return 3
    if ph < 6.5:
        return 1
    if ph > 8.5:
        return 2
    return 0


def _advance_state(state: AnalyzerState) -> AnalyzerState:
    """Advance analyzer values by one simulation tick."""
    # Primary neutral operation band.
    ph = state.ph + random.uniform(-0.08, 0.08)

    # Occasional acidic or alkaline drift events.
    event_roll = random.random()
    if event_roll < 0.03:
        ph += random.uniform(-1.4, -0.7)  # acidic drift
    elif event_roll < 0.06:
        ph += random.uniform(0.8, 1.6)  # alkaline drift

    # Keep values physically plausible while allowing alarm excursions.
    ph = _clamp(ph, 4.5, 10.5)

    # Temperature around 25C with modest noise and rare spikes.
    temperature_c = state.temperature_c + random.uniform(-0.25, 0.25)
    if random.random() < 0.01:
        temperature_c += random.choice([-1, 1]) * random.uniform(8.0, 24.0)
    temperature_c = _clamp(temperature_c, -5.0, 60.0)

    # Sensor health declines slightly during out-of-band conditions.
    if ph < 6.5 or ph > 8.5 or temperature_c < 5 or temperature_c > 45:
        health_percent = state.health_percent - random.randint(1, 2)
    else:
        health_percent = state.health_percent + random.randint(0, 1)
    health_percent = int(_clamp(health_percent, 60, 100))

    alarm = _calculate_alarm(ph, temperature_c)

    return AnalyzerState(
        ph=ph,
        temperature_c=temperature_c,
        status=1,
        alarm=alarm,
        health_percent=health_percent,
    )


def _write_registers(context: ModbusServerContext, state: AnalyzerState) -> None:
    """Write current state to holding registers."""
    registers = [0] * 5
    registers[REG_PH] = int(round(state.ph * 100))
    registers[REG_TEMPERATURE] = int(round(state.temperature_c * 10))
    registers[REG_STATUS] = state.status
    registers[REG_ALARM] = state.alarm
    registers[REG_HEALTH] = state.health_percent

    # Write to slave/unit 0x00 holding registers (1-5).
    context[0x00].setValues(3, 1, registers)


def _read_registers(context: ModbusServerContext) -> list[int]:
    return context[0x00].getValues(3, 1, count=5)


async def _simulation_loop(context: ModbusServerContext, stop_event: asyncio.Event) -> None:
    state = AnalyzerState()

    while not stop_event.is_set():
        state = _advance_state(state)
        _write_registers(context, state)

        regs = _read_registers(context)
        LOGGER.info(
            "pH=%.2f temp=%.1f°C status=%d alarm=%d health=%d%% regs=%s",
            state.ph,
            state.temperature_c,
            state.status,
            state.alarm,
            state.health_percent,
            regs,
        )
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=UPDATE_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            continue


async def run_server() -> None:
    """Run Modbus server and simulation task until interrupted."""
    store = ModbusDeviceContext(hr=ModbusSequentialDataBlock(1, [0] * 100))
    context = ModbusServerContext(devices={0x00: store}, single=False)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _request_shutdown() -> None:
        LOGGER.info("Shutdown signal received, stopping simulator...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except NotImplementedError:
            # Fallback platforms without add_signal_handler support.
            signal.signal(sig, lambda *_: _request_shutdown())

    sim_task = asyncio.create_task(_simulation_loop(context, stop_event), name="ph-simulation-loop")

    try:
        LOGGER.info("Starting Modbus TCP server on %s:%s", HOST, PORT)
        await StartAsyncTcpServer(context=context, address=(HOST, PORT))
    finally:
        stop_event.set()
        sim_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sim_task


def main() -> None:
    """Program entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        LOGGER.info("Simulator stopped by user.")


if __name__ == "__main__":
    main()
