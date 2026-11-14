"""Draw a Marey chart: time on the x axis, distance along the line on the y axis."""

import math
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass

from matplotlib.axes import Axes

from caltrain_schedule.gtfs import Station, Trip

# The Set1 colors from the 2017 charts: local blue, limited green, express
# (formerly baby bullet) red. South County, which is new, is purple.
ROUTE_COLORS = {
    "Local Weekday": "#377eb8",
    "Local Weekend": "#377eb8",
    "Limited": "#4daf4a",
    "Express": "#e41a1c",
    "South County": "#984ea3",
}
UNKNOWN_ROUTE_COLOR = "#999999"

FADED_ALPHA = 0.2
GRID_COLOR = "0.6"
# The frame of matplotlib's former seaborn-white style.
FRAME_COLOR = "#262626"
FRAME_WIDTH = 1.25
PAD_SECONDS = 600
# Miles of space past the top and bottom stations.
EDGE_PAD = 2.0
BEYOND_PAD = 1.0


@dataclass(frozen=True)
class ChartOptions:
    """What part of the schedule a chart shows."""

    direction: str = "both"
    # Hours after the start of the service day. Values over 24 are after
    # midnight. None fits the range to the trips.
    start_hour: float | None = None
    end_hour: float | None = None
    # The stations at the top and bottom of the chart.
    top_station: str = "san_francisco"
    bottom_station: str = "sj_diridon"
    labeled_stations: Collection[str] = ()


def route_color(route: str) -> str:
    """Return the line color for a route name."""
    return ROUTE_COLORS.get(route, UNKNOWN_ROUTE_COLOR)


def hour_label(hour: int) -> str:
    """Label an hour tick the way the 2017 charts did: 4 through 24, then 1, 2."""
    return str(hour if hour <= 24 else hour - 24)


def time_range(trips: Iterable[Trip]) -> tuple[float, float]:
    """Return the hours that cover the trips.

    The range is padded by 10 minutes and rounded outward to 10 minutes,
    which reproduces the 2017 limits, such as 4:10 to 25:50 on weekdays.
    """
    seconds = [stop.seconds for trip in trips for stop in trip.stop_times]
    if not seconds:
        raise ValueError("no trips to plot")
    step = PAD_SECONDS
    start = (min(seconds) - PAD_SECONDS) // step * step
    end = -(-(max(seconds) + PAD_SECONDS) // step) * step
    return start / 3600, end / 3600


def edge_limit(edge: float, positions: Iterable[float], outward: int) -> float:
    """Return the y limit beyond the edge station, in miles.

    The limit is ``EDGE_PAD`` miles past the edge station. When the next
    station past the edge is within that pad, as Tamien is past San Jose
    Diridon, the limit moves to ``BEYOND_PAD`` miles past that station, so
    its stop markers are not cut off. ``outward`` is 1 for the far edge
    and -1 for the near edge.
    """
    beyond = [outward * (pos - edge) for pos in positions if outward * (pos - edge) > 0]
    pad = EDGE_PAD
    if beyond and min(beyond) < EDGE_PAD:
        pad = max(EDGE_PAD, min(beyond) + BEYOND_PAD)
    return edge + outward * pad


def plot_marey(
    ax: Axes,
    trips: Iterable[Trip],
    stations: Mapping[str, Station],
    positions: Mapping[str, float],
    options: ChartOptions,
) -> Axes:
    """Draw one line per trip on ``ax``.

    ``positions`` gives each station's distance from San Francisco. The top
    station is drawn at the top. Trips in the other direction from
    ``options.direction`` are drawn faint and without stop markers.
    """
    if options.direction not in {"north", "south", "both"}:
        raise ValueError(f"unknown direction: {options.direction}")

    trips = list(trips)
    data_start, data_end = time_range(trips)
    start = data_start if options.start_hour is None else options.start_hour
    end = data_end if options.end_hour is None else options.end_hour

    for trip in trips:
        color = route_color(trip.route)
        highlighted = options.direction in {"both", trip.direction}
        alpha = 1.0 if highlighted else FADED_ALPHA
        zorder = 3 if highlighted else 2
        hours = [stop.seconds / 3600 for stop in trip.stop_times]
        miles = [positions[stop.station_id] for stop in trip.stop_times]
        ax.plot(hours, miles, color=color, alpha=alpha, zorder=zorder, label=f"Train {trip.train}")
        if highlighted:
            ax.scatter(
                hours,
                miles,
                s=10,
                facecolors="w",
                edgecolors=color,
                linewidths=1,
                zorder=4,
            )

    # Hour grid, with even hours shaded. Shading covers the partial hours at
    # the edges too; the axes limits clip it.
    hour_ticks = range(math.ceil(start), math.floor(end) + 1)
    ax.set_xticks(list(hour_ticks), [hour_label(hour) for hour in hour_ticks])
    for hour in hour_ticks:
        ax.axvline(hour, color=GRID_COLOR, linewidth=0.4, zorder=1)
    for hour in range(math.floor(start), math.ceil(end)):
        if hour % 2 == 0:
            ax.axvspan(hour, hour + 1, color="black", alpha=0.03, zorder=0, linewidth=0)
    ax.set_xlim(start, end)

    # Station grid. Distance increases downward, so San Francisco is on top.
    labeled = [sid for sid in options.labeled_stations if sid in positions]
    ax.set_yticks(
        [positions[sid] for sid in labeled],
        [stations[sid].name if sid in stations else sid for sid in labeled],
    )
    for sid in labeled:
        ax.axhline(positions[sid], color=GRID_COLOR, linewidth=0.4, zorder=1)
    near, far = sorted((positions[options.top_station], positions[options.bottom_station]))
    ax.set_ylim(
        edge_limit(far, positions.values(), 1),
        edge_limit(near, positions.values(), -1),
    )

    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_color(FRAME_COLOR)
        spine.set_linewidth(FRAME_WIDTH)
    return ax
