import math
from dataclasses import dataclass

from app.utils.geography import EARTH_METERS, haversine


@dataclass(frozen=True)
class Envelope:
    south: float
    north: float
    west: float
    east: float


def envelope(latitude: float, longitude: float, radius: float) -> Envelope:
    proximity(latitude, longitude, latitude, longitude, radius)
    angle = radius / EARTH_METERS
    latitude_angle = math.radians(latitude)
    south = max(-90, latitude - math.degrees(angle))
    north = min(90, latitude + math.degrees(angle))
    if south <= -90 or north >= 90:
        return Envelope(south, north, -180, 180)
    delta = math.degrees(math.asin(min(1, math.sin(angle) / math.cos(latitude_angle))))
    return Envelope(
        south, north, (longitude - delta + 180) % 360 - 180, (longitude + delta + 180) % 360 - 180
    )


def proximity(
    lat1: float, lon1: float, lat2: float, lon2: float, radius: float
) -> tuple[float, float]:
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("Positive finite radius required")
    for latitude, longitude in ((lat1, lon1), (lat2, lon2)):
        if not math.isfinite(latitude) or not -90 <= latitude <= 90:
            raise ValueError("Invalid latitude")
        if not math.isfinite(longitude) or not -180 <= longitude <= 180:
            raise ValueError("Invalid longitude")
    distance = haversine(lat1, lon1, lat2, lon2)
    return distance, max(0.0, min(1.0, 1 - distance / radius))
