"""Draw a Marey chart: time on the x axis, distance along the line on the y axis."""

import math
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass

from matplotlib.axes import Axes
from matplotlib.font_manager import FontProperties
from matplotlib.transforms import blended_transform_factory

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
# Stations outside ``labeled_stations`` get a lighter label and grid line.
OTHER_STATION_COLOR = "0.6"
OTHER_GRID_COLOR = "0.85"
STATION_COLOR = "black"
STATION_SIZE = "medium"
OTHER_STATION_SIZE = "small"
# Label spacing, as a multiple of the labeled stations' font size.
LABEL_LINE_HEIGHT = 1.15
# How much more a labeled station's name resists moving than a grey one's.
MAJOR_LABEL_WEIGHT = 20.0
# How far a labeled station's name may move, as a fraction of a line.
MAX_MAJOR_SHIFT = 0.35
# Gap between the station names and the axes, as a fraction of its width.
LEADER_LENGTH = 0.012
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


def spread_labels(
    targets: Sequence[float],
    min_gap: float,
    weights: Sequence[float] | None = None,
) -> list[float]:
    """Move sorted label positions apart until neighbors are ``min_gap`` apart.

    Labels that would overlap form a group of evenly spaced labels. Each
    group is placed to minimize the weighted squared distance of its labels
    from their targets, so a heavy label moves less than a light one.
    Groups merge until none overlap.
    """
    if weights is None:
        weights = [1.0] * len(targets)

    def first_label(group: list[int]) -> float:
        # The weighted mean of each target, less its offset in the group.
        total = sum(weights[i] for i in group)
        return sum(weights[i] * (targets[i] - k * min_gap) for k, i in enumerate(group)) / total

    groups: list[list[int]] = []
    for index in range(len(targets)):
        group = [index]
        while groups:
            previous = groups[-1]
            previous_last = first_label(previous) + (len(previous) - 1) * min_gap
            if first_label(group) - previous_last >= min_gap:
                break
            group = groups.pop() + group
        groups.append(group)

    spread: list[float] = []
    for group in groups:
        start = first_label(group)
        spread.extend(start + k * min_gap for k in range(len(group)))
    return spread


def fit_labels(
    targets: Sequence[float],
    major: Sequence[bool],
    min_gap: float,
    max_major_shift: float,
) -> dict[int, float]:
    """Choose which labels to show and where, keyed by index into ``targets``.

    Every major label is shown. Minor labels are added in order, and each
    one is kept only if the spread labels leave every major label within
    ``max_major_shift`` of its target. Where the line is too crowded, some
    minor labels are left out.
    """
    weights = [MAJOR_LABEL_WEIGHT if is_major else 1.0 for is_major in major]

    def spread(indices: list[int]) -> list[float]:
        return spread_labels([targets[i] for i in indices], min_gap, [weights[i] for i in indices])

    kept = [i for i, is_major in enumerate(major) if is_major]
    for candidate in (i for i, is_major in enumerate(major) if not is_major):
        trial = sorted([*kept, candidate])
        positions = spread(trial)
        if all(
            abs(pos - targets[i]) <= max_major_shift
            for i, pos in zip(trial, positions, strict=True)
            if major[i]
        ):
            kept = trial
    return dict(zip(kept, spread(kept), strict=True))


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
    # Every station in view is named on the left: the labeled stations in
    # black, the rest smaller and in lighter grey. Where names would
    # overlap they are spread apart, mostly by moving the grey names, and a
    # short leader line joins each name to its station.
    near, far = sorted((positions[options.top_station], positions[options.bottom_station]))
    lower = edge_limit(far, positions.values(), 1)
    upper = edge_limit(near, positions.values(), -1)
    ax.set_ylim(lower, upper)
    ax.set_yticks([])

    in_view = sorted(
        (sid for sid, pos in positions.items() if upper <= pos <= lower),
        key=lambda sid: positions[sid],
    )
    major = set(options.labeled_stations)
    for sid in in_view:
        color = GRID_COLOR if sid in major else OTHER_GRID_COLOR
        ax.axhline(positions[sid], color=color, linewidth=0.4, zorder=1)

    fontsize = FontProperties(size=STATION_SIZE).get_size_in_points()
    _, axes_height = ax.get_window_extent().size
    points_per_mile = axes_height * 72 / ax.figure.dpi / (lower - upper)
    min_gap = fontsize * LABEL_LINE_HEIGHT / points_per_mile
    label_positions = fit_labels(
        [positions[sid] for sid in in_view],
        [sid in major for sid in in_view],
        min_gap=min_gap,
        max_major_shift=MAX_MAJOR_SHIFT * min_gap,
    )
    left_edge = blended_transform_factory(ax.transAxes, ax.transData)
    for index, y in label_positions.items():
        sid = in_view[index]
        is_major = sid in major
        ax.annotate(
            stations[sid].name if sid in stations else sid,
            xy=(0, positions[sid]),
            xycoords=left_edge,
            xytext=(-LEADER_LENGTH, y),
            textcoords=left_edge,
            ha="right",
            va="center_baseline",
            color=STATION_COLOR if is_major else OTHER_STATION_COLOR,
            fontsize=STATION_SIZE if is_major else OTHER_STATION_SIZE,
            arrowprops={
                "arrowstyle": "-",
                "color": GRID_COLOR if is_major else OTHER_GRID_COLOR,
                "linewidth": 0.4,
                "shrinkA": 1,
                "shrinkB": 0,
            },
            annotation_clip=False,
        )

    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_color(FRAME_COLOR)
        spine.set_linewidth(FRAME_WIDTH)
    return ax
