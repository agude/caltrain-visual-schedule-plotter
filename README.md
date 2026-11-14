# caltrain-schedule

Draws Marey charts of the Caltrain schedule from Caltrain's GTFS feed. Each
train is a line: time runs left to right, and distance from San Francisco runs
top to bottom. This project updates the 2017 charts in
[Caltrain Visual Schedule](https://alexgude.com/blog/caltrain-visual-schedule/)
and [Updated Caltrain Visual Schedule](https://alexgude.com/blog/caltrain-visual-schedule-updates/).

## Usage

```sh
just fetch       # Download and unpack the current feed into data/caltrain-YYYYMMDD/.
just charts      # Draw the chart set from the newest feed.
just charts-all  # Draw the chart set from every feed in data/.
```

Each feed's charts go to `output/<feed name>/`, such as
`output/caltrain-20261113/weekday.svg`. The chart set is the weekday
schedule (both directions, northbound, southbound, to Gilroy, morning, and
evening), Saturday, and Sunday, as PNG and SVG. Every feed uses the same
time ranges, so charts of different schedules line up.

`data/` holds three feeds, unpacked as downloaded:

| Feed | Schedule | Used in |
| --- | --- | --- |
| `caltrain-20170308/` | April 2017 | [Caltrain Visual Schedule](https://alexgude.com/blog/caltrain-visual-schedule/) |
| `caltrain-20170715/` | July 2017 | [Updated Caltrain Visual Schedule](https://alexgude.com/blog/caltrain-visual-schedule-updates/) |
| `caltrain-20261113/` | January 2026 | This update |

Draw a single chart with the `plot` command:

```sh
uv run caltrain-schedule plot data/caltrain-20261113 output/chart.svg \
    --day weekday --direction north --start 05:30 --end 10:30
```

| Option | Effect |
| --- | --- |
| `--day` | Regular schedule for `weekday`, `weekend`, or a day name. Ignores holidays. |
| `--date` | Schedule on a `YYYY-MM-DD` date, with holiday changes applied. |
| `--direction` | `both`, `north`, or `south`. The other direction is drawn faint. |
| `--start`, `--end` | Time range as `HH:MM`. Hours of 24 or more are after midnight. |
| `--top`, `--bottom` | GTFS parent station IDs at the chart edges, such as `gilroy`. |
| `--label` | Station ID to name in black. Repeat it for more. Other stations are named in grey. |
| `--no-other-names` | Name only the `--label` stations. The other stations keep their grey grid lines. |
| `--distances` | Feed to take station distances from. The 2017 feeds have none. |
| `--name` | What the chart shows, for the title. The title adds the month the schedule started. |
| `--title` | Replaces the whole title. |

Colors follow the 2017 charts: local blue, limited green, express red. South
County Connector trains, which are new, are purple.

## Changes from the 2017 notebooks

- Station distances come from the feed's `shape_dist_traveled`, not from
  hand-entered Wikipedia mileposts. This removes the old error of up to
  100 m south of Lawrence.
- Service types come from `routes.txt` (Local Weekday, Local Weekend,
  Limited, Express, South County), not from the leading digit of the train
  number.
- Services are chosen from `calendar.txt` and `calendar_dates.txt`, not from
  hard-coded `service_id` strings, so a new feed needs no code change.
- The 2017 feeds load too. Their stops map to current station IDs by
  name, and closed stations, such as Atherton, are placed with the 2017
  mileposts.
- Matplotlib renamed the 2017 `seaborn-white` style to
  `seaborn-v0_8-white`. The look, including the Liberation Sans font and the
  2017 font sizes, is now set explicitly, and seaborn and pandas are no
  longer dependencies.

## Development

Requires [uv](https://docs.astral.sh/uv/) 0.13 or newer and [just](https://just.systems/).

The `.python-version` file selects Python 3.15. uv 0.13 or newer can
download its final release. The lower uv minimum in `pyproject.toml` lets
Dependabot update the lock on Python 3.11; CI tests that minimum.

```sh
just sync           # Install the locked development environment.
just hooks-install  # Install the pre-commit hook, which runs `just lint`.
just check          # Run lint, type-check, and test.
```

Run `just` to list every recipe.

## Releasing

```sh
just release patch  # Or minor or major. Runs `just check`, then commits and tags.
git push origin HEAD vX.Y.Z
```

## License

[CC0 1.0 Universal](LICENSE.md)
