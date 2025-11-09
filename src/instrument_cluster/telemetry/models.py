from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class Flags(BaseModel):
    paused: bool = False
    loading_or_processing: bool = False
    car_on_track: bool = False
    in_gear: bool = False  # 0 when shifting or out of gear, standing
    has_turbo: bool = False
    rev_limiter_alert_active: bool = False
    hand_brake_active: bool = False
    lights_active: bool = False
    lights_high_beams_active: bool = False
    lights_low_beams_active: bool = False
    asm_active: bool = False
    tcs_active: bool = False


class Vector(BaseModel):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class Wheels(BaseModel):
    front_left: Wheel
    front_right: Wheel
    rear_left: Wheel
    rear_right: Wheel


class Wheel(BaseModel):
    suspension_height: float = Field(ge=0, le=1)
    radius: float  # in meters
    rps: float  # rotations per second (not radians like default)
    ground_speed: float  # meters per second
    temperature: float


class Bounds(BaseModel):
    min: float = 0.0
    max: float = 1000.0


class TelemetryFrame(BaseModel):
    received_time: float = 0.0
    car_id: int = -1
    car_speed: float = 0.0
    engine_rpm: float = 0.0
    current_gear: int = 0  # 0 is reverse, -1 is neutral
    throttle: float = 0.0
    brake: float = 0.0
    steering: float = 0.0
    lap_count: int | None = None
    laps_in_race: int | None = None
    best_lap_time: int | None = None
    last_lap_time: int | None = None
    flags: Flags = None
    rpm_alert: Bounds = None
    wheels: Wheels = None
    position: Vector = None
    gear_ratios: List[float] = None
