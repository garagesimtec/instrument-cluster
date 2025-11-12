import math
import time

from .models import Flags, TelemetryFrame, Wheel, Wheels

SHIFT_INTERVAL = 5.0  # seconds between gear changes
SHIFT_PRE = 0.2  # seconds before change to show in_gear = False


class DemoReader:
    def __init__(self):
        self._t0 = time.perf_counter()

    def start(self) -> None:
        pass

    def latest(self) -> TelemetryFrame:
        t = time.perf_counter() - self._t0
        speed = max(0.0, 35.0 + 15.0 * math.sin(2 * math.pi * (t / 6.0)))  # 38.62
        rpm = int(6500 + 2000 * math.sin(2 * math.pi * (t / 3.0)))

        # cycles every `SHIFT_INTERVAL` seconds: -1, 0, 1, 2, 3, 4, 5, 6
        gear = -1 + int((t // SHIFT_INTERVAL) % 8)

        wheel = Wheel(
            suspension_height=0.0,
            radius=0.0,
            rps=0.0,
            ground_speed=0.0,
            temperature=10.7,
        )

        wheels = Wheels(
            front_left=wheel,
            front_right=wheel,
            rear_left=wheel,
            rear_right=wheel,
        )

        k = int(t // SHIFT_INTERVAL)
        t_into = t - k * SHIFT_INTERVAL
        t_remaining = SHIFT_INTERVAL - t_into
        in_gear = not (t_remaining <= SHIFT_PRE)

        flags = Flags(in_gear=in_gear)

        return TelemetryFrame(
            received_time=time.time_ns(),
            car_speed=speed,
            engine_rpm=rpm,
            current_gear=gear,
            throttle=max(0.0, math.sin(t) * 0.5 + 0.5),
            brake=max(0.0, math.sin(t + 1.8) * -0.4),
            steering=math.sin(t / 2.0) * 0.3,
            lap_count=1,
            best_lap_time=1000,  # 0 + int((1000 * t)),
            last_lap_time=1000,
            flags=flags,
            wheels=wheels,
        )

    def stop(self) -> None:
        pass
