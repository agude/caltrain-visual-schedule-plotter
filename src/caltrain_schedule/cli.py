"""Command-line interface for caltrain-schedule."""

import argparse
import datetime as dt
import io
import tempfile
import urllib.request
import zipfile
from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")

import matplotlib.pyplot as plt

from caltrain_schedule import __version__
from caltrain_schedule.gtfs import (
    WEEKDAYS,
    Feed,
    Station,
    Trip,
    load_feed,
    services_on_date,
    services_on_weekday,
    station_positions,
)
from caltrain_schedule.legacy import fill_positions
from caltrain_schedule.plot import (
    FONTS,
    KEY_NAMES,
    TITLE_PAD_WITH_KEY,
    TITLE_SIZE,
    ChartOptions,
    plot_comparison,
    plot_marey,
)

# Caltrain's developer page links to this feed, which Trillium Transit hosts.
FEED_URL = "https://data.trilliumtransit.com/gtfs/caltrain-ca-us/caltrain-ca-us.zip"

ORIGIN_STATION = "san_francisco"


WIDTH = 15
HEIGHT = 7
# Comparison charts show one trip each way, so they need less width.
COMPARISON_WIDTH = 10
DPI = 300


def parse_hour(value: str) -> float:
    """Convert ``HH:MM`` to hours. Hours of 24 or more are after midnight."""
    try:
        hours, minutes = (int(part) for part in value.split(":"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected HH:MM, got {value!r}") from None
    if not 0 <= minutes < 60:
        raise argparse.ArgumentTypeError(f"minutes out of range in {value!r}")
    return hours + minutes / 60


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for caltrain-schedule."""
    parser = argparse.ArgumentParser(
        prog="caltrain-schedule",
        description="Draw Marey charts of the Caltrain schedule from its GTFS feed.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    fetch = commands.add_parser("fetch", help="Download the current GTFS feed and unpack it.")
    fetch.add_argument(
        "output", type=Path, help="Directory to unpack the feed into; must not exist."
    )
    fetch.add_argument("--url", default=FEED_URL, help="Feed URL. Default: %(default)s")

    chart = commands.add_parser("plot", help="Draw a Marey chart from a GTFS feed.")
    chart.add_argument("feed", type=Path, help="GTFS zip file or unzipped directory.")
    chart.add_argument("output", type=Path, help="Image to write; the suffix sets the format.")
    when = chart.add_mutually_exclusive_group()
    when.add_argument(
        "--day",
        choices=(*WEEKDAYS, "weekday", "weekend"),
        default="weekday",
        help="Regular schedule for a day, ignoring holidays. Default: %(default)s",
    )
    when.add_argument(
        "--date",
        type=dt.date.fromisoformat,
        help="Schedule on a YYYY-MM-DD date, including holiday changes.",
    )
    chart.add_argument("--direction", choices=("both", "north", "south"), default="both")
    chart.add_argument("--start", type=parse_hour, help="First time shown, as HH:MM.")
    chart.add_argument(
        "--end", type=parse_hour, help="Last time shown, as HH:MM. Use 25:30 for 1:30 AM."
    )
    chart.add_argument("--top", default="san_francisco", help="Station ID at the top.")
    chart.add_argument("--bottom", default="sj_diridon", help="Station ID at the bottom.")
    chart.add_argument(
        "--height",
        type=float,
        default=HEIGHT,
        help="Chart height in inches. Taller charts spread close station names less."
        " Default: %(default)s",
    )
    chart.add_argument(
        "--key",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Name the routes in their line colors under the title. Default: on.",
    )
    chart.add_argument(
        "--distances",
        type=Path,
        help="Feed to take station distances from, for a feed without them, such as 2017's."
        " Default: the plotted feed.",
    )
    chart.add_argument(
        "--name",
        help="What the chart shows, for the default title. Default: the day, such as Weekday.",
    )
    chart.add_argument("--title", help="Chart title. Default: the name and the schedule's start.")

    compare = commands.add_parser(
        "compare", help="Draw two trains against minutes from one station, to compare speed."
    )
    compare.add_argument("output", type=Path, help="Image to write; the suffix sets the format.")
    compare.add_argument(
        "--trip",
        nargs=2,
        action="append",
        metavar=("FEED", "TRAIN"),
        required=True,
        help="A feed and a train number in it. Give it twice, oldest first.",
    )
    compare.add_argument(
        "--origin",
        default="sj_diridon",
        help="Station ID that time is measured from. Default: %(default)s",
    )
    compare.add_argument(
        "--distances",
        type=Path,
        required=True,
        help="Feed to take station distances from, such as the newest one.",
    )
    compare.add_argument(
        "--height", type=float, default=HEIGHT, help="Chart height in inches. Default: %(default)s"
    )
    compare.add_argument("--title", help="Chart title. Default: the trains' route names.")
    return parser


def fetch_feed(url: str, output: Path) -> None:
    """Download the feed zip at ``url`` and unpack its tables into ``output``.

    ``output`` must not exist. The tables are unpacked into a temporary
    directory beside it and renamed into place, so a failed download leaves
    nothing behind. A GTFS zip holds only plain table files, so any entry
    with a directory part is refused rather than written outside ``output``.
    """
    if output.exists():
        raise SystemExit(f"caltrain-schedule: {output} already exists")
    with urllib.request.urlopen(url) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
    for name in archive.namelist():
        if Path(name).name != name or name in {"", ".", ".."}:
            raise SystemExit(f"caltrain-schedule: refusing feed entry {name!r}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as staging:
        for name in archive.namelist():
            (Path(staging) / name).write_bytes(archive.read(name))
        Path(staging).rename(output)


def describe_day(args: argparse.Namespace) -> str:
    """Name the chosen day, for messages and the default title."""
    if args.date is not None:
        return str(args.date.isoformat())
    return str(args.day).capitalize()


def default_title(args: argparse.Namespace, feed: Feed, services: set[str]) -> str:
    """Title a chart with what it shows and when its schedule started.

    A chart for a date shows that date. Otherwise the title names the month
    the schedule took effect, such as ``Weekday, April 2017``, so charts of
    different schedules can be told apart.
    """
    name = args.name or describe_day(args)
    if args.date is not None:
        return f"Caltrain Schedule: {name}"
    start = min(feed.services[sid].start for sid in services if sid in feed.services)
    return f"Caltrain Schedule: {name}, {start:%B %Y}"


def load_positions(feed: Feed) -> dict[str, float]:
    """Return each station's distance from San Francisco, in miles, from ``feed``.

    Closed stations that ``feed`` lacks, such as Atherton, are placed with
    the 2017 mileposts.
    """
    try:
        return fill_positions(station_positions(feed, ORIGIN_STATION))
    except ValueError as error:
        raise SystemExit(f"caltrain-schedule: {error}") from None


def draw_chart(args: argparse.Namespace) -> None:
    """Draw the chart that the ``plot`` arguments describe."""
    feed = load_feed(args.feed)
    if args.date is not None:
        services = services_on_date(feed, args.date)
    elif args.day == "weekday":
        # Caltrain runs one schedule Monday through Friday.
        services = services_on_weekday(feed, "wednesday")
    elif args.day == "weekend":
        services = services_on_weekday(feed, "saturday") | services_on_weekday(feed, "sunday")
    else:
        services = services_on_weekday(feed, args.day)
    trips = [trip for trip in feed.trips if trip.service_id in services]
    if not trips:
        raise SystemExit(f"caltrain-schedule: no trips run on {describe_day(args)}")

    positions = load_positions(feed if args.distances is None else load_feed(args.distances))
    for station in (args.top, args.bottom):
        if station not in positions:
            raise SystemExit(f"caltrain-schedule: unknown station ID: {station}")
    options = ChartOptions(
        direction=args.direction,
        start_hour=args.start,
        end_hour=args.end,
        top_station=args.top,
        bottom_station=args.bottom,
        key=args.key,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with mpl.rc_context({"font.family": "sans-serif", "font.sans-serif": FONTS}):
        fig, ax = plt.subplots(figsize=(WIDTH, args.height))
        plot_marey(ax, trips, feed.stations, positions, options)
        ax.set_title(
            args.title or default_title(args, feed, services),
            fontsize=TITLE_SIZE,
            pad=TITLE_PAD_WITH_KEY if args.key else None,
        )
        fig.savefig(args.output, dpi=DPI, bbox_inches="tight")
        plt.close(fig)


def find_train(feed: Feed, train: str) -> Trip:
    """Return the one trip in ``feed`` that runs as ``train``."""
    trips = [trip for trip in feed.trips if trip.train == train]
    if len(trips) != 1:
        found = "no trips" if not trips else f"{len(trips)} trips"
        raise SystemExit(f"caltrain-schedule: {found} run as train {train}")
    return trips[0]


def comparison_label(feed: Feed, trip: Trip, origin: str) -> str:
    """Label a compared trip with its schedule's start, its number, and its time."""
    start = feed.services[trip.service_id].start
    seconds = [stop.seconds for stop in trip.stop_times if stop.station_id == origin]
    minutes = (trip.stop_times[-1].seconds - seconds[0]) // 60 if seconds else None
    duration = f", {minutes} min" if minutes is not None else ""
    return f"{start:%B %Y}: train {trip.train}{duration}"


def draw_comparison(args: argparse.Namespace) -> None:
    """Draw the chart that the ``compare`` arguments describe."""
    trips: list[tuple[str, Trip]] = []
    stations: dict[str, Station] = {}
    for path, train in args.trip:
        feed = load_feed(Path(path))
        trip = find_train(feed, train)
        trips.append((comparison_label(feed, trip, args.origin), trip))
        stations.update(feed.stations)
    positions = load_positions(load_feed(args.distances))
    names = dict.fromkeys(KEY_NAMES.get(trip.route, trip.route) for _, trip in trips)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with mpl.rc_context({"font.family": "sans-serif", "font.sans-serif": FONTS}):
        fig, ax = plt.subplots(figsize=(COMPARISON_WIDTH, args.height))
        try:
            plot_comparison(ax, trips, stations, positions, args.origin)
        except ValueError as error:
            plt.close(fig)
            raise SystemExit(f"caltrain-schedule: {error}") from None
        ax.set_title(args.title or " / ".join(names), fontsize=TITLE_SIZE)
        fig.savefig(args.output, dpi=DPI, bbox_inches="tight")
        plt.close(fig)


def main(argv: Sequence[str] | None = None) -> int:
    """Run caltrain-schedule and return its exit status."""
    args = build_parser().parse_args(argv)
    if args.command == "fetch":
        fetch_feed(args.url, args.output)
    elif args.command == "compare":
        draw_comparison(args)
    else:
        draw_chart(args)
    return 0
