from dataclasses import dataclass


@dataclass
class Feed:
    delta_s: float = 0.0  # smoothed delta from DeltaWidget
    has_delta: bool = False
