"""Read the parts of a Caltrain GTFS feed that a Marey chart needs."""

import csv
import datetime as dt
import io
import math
import statistics
import zipfile
from collections import Counter, defaultdict, deque
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from caltrain_schedule.legacy import LEGACY_STATIONS

METERS_PER_MILE = 1609.344
RAIL_ROUTE_TYPE = "2"
ONE_YEAR = dt.timedelta(days=365)

# GTFS direction_id values, as Caltrain's directions.txt defines them.
DIRECTION_NAMES = {"0": "north", "1": "south"}

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@dataclass(frozen=True)
class Station:
    """A parent station, which groups the platforms of one stop."""

    station_id: str
    name: str


@dataclass(frozen=True)
class StopTime:
    """A train's arrival at a station, in seconds after the service day starts."""

    station_id: str
    seconds: int
    shape_distance: float


@dataclass(frozen=True)
class Trip:
    """One scheduled train run."""

    trip_id: str
    train: str
    route: str
    service_id: str
    direction: str
    stop_times: tuple[StopTime, ...]


@dataclass(frozen=True)
class Service:
    """A GTFS service: the days on which a set of trips runs."""

    service_id: str
    weekdays: frozenset[str]
    start: dt.date
    end: dt.date


@dataclass(frozen=True)
class Feed:
    """The stations, trips, and service calendar of a GTFS feed."""

    stations: dict[str, Station]
    trips: tuple[Trip, ...]
    services: dict[str, Service]
    # Maps a date to the service IDs added (True) or removed (False) on it.
    exceptions: dict[dt.date, dict[str, bool]]


def parse_time(value: str) -> int:
    """Convert a GTFS ``HH:MM:SS`` time to seconds.

    GTFS times count from noon minus 12 hours on the service day, so trains
    after midnight have hours of 24 or more. They stay larger than the
    evening times, which keeps each trip's times increasing.
    """
    hours, minutes, seconds = (int(part) for part in value.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def parse_date(value: str) -> dt.date:
    """Convert a GTFS ``YYYYMMDD`` date to a date."""
    return dt.datetime.strptime(value, "%Y%m%d").date()


def station_name(stop_name: str) -> str:
    """Shorten a stop name, such as ``Palo Alto Station``, to ``Palo Alto``."""
    for suffix in (" Caltrain Station", " Station"):
        stop_name = stop_name.removesuffix(suffix)
    return stop_name


class _Tables:
    """Read GTFS tables from a directory or a zip file."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def rows(self, name: str) -> Iterator[dict[str, str]]:
        if self._path.is_dir():
            with (self._path / name).open(encoding="utf-8-sig", newline="") as handle:
                yield from csv.DictReader(handle)
            return
        with (
            zipfile.ZipFile(self._path) as archive,
            archive.open(name) as raw,
            io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as handle,
        ):
            yield from csv.DictReader(handle)


def load_feed(path: Path) -> Feed:
    """Load a GTFS feed from a directory or a zip file."""
    tables = _Tables(path)

    stations: dict[str, Station] = {}
    parent_of: dict[str, str] = {}
    for row in tables.rows("stops.txt"):
        stop_id, name = row["stop_id"], row["stop_name"]
        if row.get("location_type") == "1":
            stations[stop_id] = Station(stop_id, station_name(name))
        elif row.get("parent_station"):
            parent_of[stop_id] = row["parent_station"]
        elif name in LEGACY_STATIONS:
            # A feed without parent stations, such as 2017's.
            station_id, display_name = LEGACY_STATIONS[name]
            parent_of[stop_id] = station_id
            stations[station_id] = Station(station_id, display_name)
        else:
            parent_of[stop_id] = stop_id

    # Keep trains only: GTFS route_type 2 is rail. The 2017 feeds include a
    # Tamien shuttle bus.
    routes = {
        row["route_id"]: row["route_short_name"]
        for row in tables.rows("routes.txt")
        if row.get("route_type", RAIL_ROUTE_TYPE) == RAIL_ROUTE_TYPE
    }

    stop_rows: dict[str, list[tuple[int, StopTime]]] = defaultdict(list)
    for row in tables.rows("stop_times.txt"):
        stop_time = StopTime(
            station_id=parent_of.get(row["stop_id"], row["stop_id"]),
            seconds=parse_time(row["arrival_time"]),
            shape_distance=float(row.get("shape_dist_traveled") or "nan"),
        )
        stop_rows[row["trip_id"]].append((int(row["stop_sequence"]), stop_time))

    trips = tuple(
        Trip(
            trip_id=row["trip_id"],
            train=row["trip_short_name"] or row["trip_id"],
            route=routes[row["route_id"]],
            service_id=row["service_id"],
            direction=DIRECTION_NAMES[row["direction_id"]],
            stop_times=tuple(stop for _, stop in sorted(stop_rows[row["trip_id"]])),
        )
        for row in tables.rows("trips.txt")
        if row["route_id"] in routes
    )

    services = {
        row["service_id"]: Service(
            service_id=row["service_id"],
            weekdays=frozenset(day for day in WEEKDAYS if row[day] == "1"),
            start=parse_date(row["start_date"]),
            end=parse_date(row["end_date"]),
        )
        for row in tables.rows("calendar.txt")
    }

    exceptions: dict[dt.date, dict[str, bool]] = defaultdict(dict)
    for row in tables.rows("calendar_dates.txt"):
        exceptions[parse_date(row["date"])][row["service_id"]] = row["exception_type"] == "1"

    return Feed(stations, trips, services, dict(exceptions))


def services_on_weekday(feed: Feed, weekday: str) -> set[str]:
    """Return the regular service IDs for a day of the week, ignoring holidays.

    The regular service is the most common set of services on that day of
    the week during the feed's first year. The calendar flags alone are
    not enough: the July 2017 feed marks its Saturday service as running
    every day, and removes it from weekdays with calendar_dates.txt.
    """
    if weekday not in WEEKDAYS:
        raise ValueError(f"unknown day of the week: {weekday}")
    if not feed.services:
        return set()
    first = min(service.start for service in feed.services.values())
    last = min(max(service.end for service in feed.services.values()), first + ONE_YEAR)
    first += dt.timedelta(days=(WEEKDAYS.index(weekday) - first.weekday()) % 7)
    counts: Counter[frozenset[str]] = Counter()
    date = first
    while date <= last:
        counts[frozenset(services_on_date(feed, date))] += 1
        date += dt.timedelta(weeks=1)
    most_common = counts.most_common(1)
    return set(most_common[0][0]) if most_common else set()


def services_on_date(feed: Feed, date: dt.date) -> set[str]:
    """Return the service IDs that run on a date, including holiday changes."""
    weekday = WEEKDAYS[date.weekday()]
    active = {
        sid
        for sid, service in feed.services.items()
        if weekday in service.weekdays and service.start <= date <= service.end
    }
    for sid, added in feed.exceptions.get(date, {}).items():
        if added:
            active.add(sid)
        else:
            active.discard(sid)
    return active


def station_positions(feed: Feed, origin: str) -> dict[str, float]:
    """Return each station's signed track distance south of ``origin``, in miles.

    Every trip gives the shape distance between its consecutive stops,
    signed by direction: positive going south, negative going north. The
    median over trips is the offset between two stations, and a
    breadth-first walk from ``origin`` adds the offsets up. Northbound and
    southbound tracks differ slightly in length, which the median smooths
    out.
    """
    if all(math.isnan(stop.shape_distance) for trip in feed.trips for stop in trip.stop_times):
        raise ValueError("the feed has no shape_dist_traveled; take distances from another feed")
    offsets: dict[tuple[str, str], list[float]] = defaultdict(list)
    for trip in feed.trips:
        sign = 1.0 if trip.direction == "south" else -1.0
        for first, second in zip(trip.stop_times, trip.stop_times[1:], strict=False):
            offset = sign * (second.shape_distance - first.shape_distance)
            offsets[(first.station_id, second.station_id)].append(offset)
            offsets[(second.station_id, first.station_id)].append(-offset)

    neighbors: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for (start, end), values in offsets.items():
        neighbors[start].append((end, statistics.median(values) / METERS_PER_MILE))

    if origin not in neighbors:
        raise ValueError(f"no trip stops at the origin station: {origin}")

    # Each station is placed once, from the first placed neighbor that
    # reaches it. Express trains skip stations, but their offsets are
    # measured along the same track, so the paths agree. In Caltrain's
    # November 2026 feed they differ by at most 200 m, south of San Jose.
    positions = {origin: 0.0}
    queue = deque([origin])
    while queue:
        station = queue.popleft()
        for neighbor, miles in sorted(neighbors[station]):
            if neighbor not in positions:
                positions[neighbor] = positions[station] + miles
                queue.append(neighbor)
    return positions
