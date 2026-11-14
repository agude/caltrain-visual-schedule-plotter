"""Read Caltrain feeds from before stops had parent stations, such as 2017's.

The 2017 feeds name each platform after its station, such as ``Mt View
Caltrain``, but have no parent stations and no ``shape_dist_traveled``. This
module maps those names to the current feed's station IDs, and keeps the
mileposts the 2017 charts used, to place stations that have since closed.
"""

from collections.abc import Mapping

# Maps a 2017 stop name to the current station ID and a display name.
LEGACY_STATIONS: dict[str, tuple[str, str]] = {
    "San Francisco Caltrain": ("san_francisco", "San Francisco"),
    "22nd St Caltrain": ("22nd_street", "22nd Street"),
    "Bayshore Caltrain": ("bayshore", "Bayshore"),
    "So. San Francisco Caltrain Station": ("south_sf", "South San Francisco"),
    "San Bruno Caltrain": ("san_bruno", "San Bruno"),
    "Millbrae Caltrain": ("place_MLBR", "Millbrae"),
    "Broadway Caltrain": ("broadway", "Broadway"),
    "Burlingame Caltrain": ("burlingame", "Burlingame"),
    "San Mateo Caltrain": ("san_mateo", "San Mateo"),
    "Hayward Park Caltrain": ("hayward_park", "Hayward Park"),
    "Hillsdale Caltrain": ("hillsdale", "Hillsdale"),
    "Belmont Caltrain": ("belmont", "Belmont"),
    "San Carlos Caltrain": ("san_carlos", "San Carlos"),
    "Redwood City Caltrain": ("redwood_city", "Redwood City"),
    "Atherton Caltrain": ("atherton", "Atherton"),
    "Menlo Park Caltrain": ("menlo_park", "Menlo Park"),
    "Palo Alto Caltrain": ("palo_alto", "Palo Alto"),
    "Stanford": ("stanford", "Stanford"),
    "California Ave Caltrain": ("california_ave", "California Avenue"),
    "San Antonio Caltrain": ("san_antonio", "San Antonio"),
    "Mt View Caltrain": ("mountain_view", "Mountain View"),
    "Sunnyvale Caltrain": ("sunnyvale", "Sunnyvale"),
    "Lawrence Caltrain": ("lawrence", "Lawrence"),
    "Santa Clara Caltrain": ("santa_clara", "Santa Clara"),
    "College Park Caltrain": ("college_park", "College Park"),
    "San Jose Diridon Caltrain": ("sj_diridon", "San Jose Diridon"),
    "San Jose Caltrain Station": ("sj_diridon", "San Jose Diridon"),
    "Tamien Caltrain": ("tamien", "Tamien"),
    "Tamien Caltrain Station": ("tamien", "Tamien"),
    "Capitol Caltrain": ("capitol", "Capitol"),
    "Blossom Hill Caltrain": ("blossom_hill", "Blossom Hill"),
    "Morgan Hill Caltrain": ("morgan_hill", "Morgan Hill"),
    "San Martin Caltrain": ("san_martin", "San Martin"),
    "Gilroy Caltrain": ("gilroy", "Gilroy"),
}

# The mileposts the 2017 charts used, from Wikipedia's list of Caltrain
# stations, keyed by station ID.
MILEPOSTS_2017: dict[str, float] = {
    "san_francisco": 0.2,
    "22nd_street": 1.9,
    "bayshore": 5.2,
    "south_sf": 9.3,
    "san_bruno": 11.6,
    "place_MLBR": 13.7,
    "broadway": 15.2,
    "burlingame": 16.3,
    "san_mateo": 17.9,
    "hayward_park": 19.1,
    "hillsdale": 20.3,
    "belmont": 21.9,
    "san_carlos": 23.2,
    "redwood_city": 25.4,
    "atherton": 27.8,
    "menlo_park": 28.9,
    "palo_alto": 30.1,
    "stanford": 30.8,
    "california_ave": 31.8,
    "san_antonio": 34.1,
    "mountain_view": 36.1,
    "sunnyvale": 38.8,
    "lawrence": 40.8,
    "santa_clara": 44.3,
    "college_park": 45.7,
    "sj_diridon": 46.9,
    "tamien": 49.1,
    "capitol": 52.4,
    "blossom_hill": 55.7,
    "morgan_hill": 67.5,
    "san_martin": 71.2,
    "gilroy": 77.4,
}


def fill_positions(
    positions: Mapping[str, float],
    mileposts: Mapping[str, float] = MILEPOSTS_2017,
) -> dict[str, float]:
    """Add stations that ``positions`` lacks but ``mileposts`` has.

    A missing station is placed between its nearest placed neighbors on
    each side, at the same fraction of the gap that the mileposts give.
    A station with a placed neighbor on one side only is offset from it by
    the milepost difference.
    """
    filled = dict(positions)
    known = sorted((mileposts[sid], sid) for sid in positions if sid in mileposts)
    for sid, milepost in mileposts.items():
        if sid in filled or not known:
            continue
        before = [(mp, other) for mp, other in known if mp <= milepost]
        after = [(mp, other) for mp, other in known if mp > milepost]
        if before and after:
            (mp_a, a), (mp_b, b) = before[-1], after[0]
            fraction = (milepost - mp_a) / (mp_b - mp_a)
            filled[sid] = positions[a] + fraction * (positions[b] - positions[a])
        elif before:
            mp_a, a = before[-1]
            filled[sid] = positions[a] + milepost - mp_a
        else:
            mp_b, b = after[0]
            filled[sid] = positions[b] - (mp_b - milepost)
    return filled
