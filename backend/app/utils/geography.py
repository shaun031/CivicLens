import math

from app.models.discovery import Bounds, GeographicBounds, Nearby

EARTH_METERS = 6371008.8
CELL_DEGREES = 0.05


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a, b = math.radians(lat1), math.radians(lat2)
    h = (
        math.sin((b - a) / 2) ** 2
        + math.cos(a) * math.cos(b) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_METERS * math.asin(math.sqrt(min(1.0, max(0.0, h))))


def geo_cell(latitude: float, longitude: float) -> str:
    # +180 and -180 denote the same meridian. Clamp poles to the last valid row.
    row = min(3599, int(math.floor((latitude + 90) / CELL_DEGREES)))
    col = int(math.floor(((longitude + 180) % 360) / CELL_DEGREES))
    return f"g05:{row:04d}:{col:04d}"


def longitude_ranges(bounds: Bounds) -> list[tuple[float, float]]:
    if bounds.minLongitude > bounds.maxLongitude:
        return [(bounds.minLongitude, 180), (-180, bounds.maxLongitude)]
    return [(bounds.minLongitude, bounds.maxLongitude)]


def cells_for_bounds(bounds: Bounds) -> list[str]:
    first = max(0, int(math.floor((bounds.minLatitude + 90) / CELL_DEGREES)))
    last = min(3599, int(math.floor((bounds.maxLatitude + 90) / CELL_DEGREES)))
    cells = set()
    for low, high in longitude_ranges(bounds):
        start = max(0, int(math.floor((low + 180) / CELL_DEGREES)))
        end = min(7199, int(math.floor((high + 180) / CELL_DEGREES)))
        for row in range(first, last + 1):
            for col in range(start, end + 1):
                cells.add(f"g05:{row:04d}:{col:04d}")
        if high == 180:
            cells.update(f"g05:{row:04d}:0000" for row in range(first, last + 1))
    return sorted(cells)


def nearby_bounds(query: Nearby) -> GeographicBounds:
    delta = math.degrees(query.radiusMeters / EARTH_METERS)
    south, north = max(-90, query.latitude - delta), min(90, query.latitude + delta)
    if south <= -90 or north >= 90:
        return GeographicBounds(
            minLatitude=south, maxLatitude=north, minLongitude=-180, maxLongitude=180
        )
    longitude_delta = math.degrees(
        math.asin(min(1, math.sin(math.radians(delta)) / math.cos(math.radians(query.latitude))))
    )
    return GeographicBounds(
        minLatitude=south,
        maxLatitude=north,
        minLongitude=(query.longitude - longitude_delta + 180) % 360 - 180,
        maxLongitude=(query.longitude + longitude_delta + 180) % 360 - 180,
    )


def region_cell(latitude: float, longitude: float) -> str:
    """Five-degree parent cells reuse existing sparse GSIs; never enumerate fine cells at 200km."""
    return f"r5:{min(35, int((latitude + 90) // 5)):02d}:{int(((longitude + 180) % 360) // 5):02d}"


def regions_for_bounds(bounds: GeographicBounds) -> list[str]:
    cells = set()
    for low, high in longitude_ranges(bounds):
        for row in range(
            max(0, int((bounds.minLatitude + 90) // 5)),
            min(35, int((bounds.maxLatitude + 90) // 5)) + 1,
        ):
            for col in range(max(0, int((low + 180) // 5)), min(71, int((high + 180) // 5)) + 1):
                cells.add(f"r5:{row:02d}:{col:02d}")
            if high == 180:
                cells.add(f"r5:{row:02d}:00")
    return sorted(cells)


def inside_bounds(latitude: float, longitude: float, bounds: Bounds) -> bool:
    return bounds.minLatitude <= latitude <= bounds.maxLatitude and any(
        low <= longitude <= high for low, high in longitude_ranges(bounds)
    )
