"""
plot_foes_doy_ut.py

Download foEs (sporadic-E critical frequency) from ionosonde stations in
Western Australia (GIRO/DIDBase) or Japan (NICT), and plot it as a function of

    x-axis : Day Of Year (DOY)
    y-axis : Universal Time (UT, hour)

DATA SOURCES
------------
1) Global Ionosphere Radio Observatory (GIRO), Lowell GIRO Data Center (LGDC)
       https://lgdc.uml.edu/fastchar/getbest
   Rules of the Road (license / acknowledgement requirements):
       https://ulcar.uml.edu/DIDBase/RulesOfTheRoadForDIDBase.htm
   Data released under CC-BY-NC-SA 4.0. Acknowledge the station data
   provider if this is used in a publication.

   Western-Australian stations in DIDBase (URSI code / longitude):
       Learmonth   LM42B   114.10E   21.8S   -- digital record since 2004
       Perth       PE43K   116.13E   32.0S   -- digital record since 2015

2) NICT (National Institute of Information and Communications Technology),
   World Data Center for Ionosphere, Japan -- manually-scaled hourly values:
       http://wdc.nict.go.jp/Ionosphere/archive/observation-history/
           factor-manual-<code>-<year>H.sjis.txt
   Times in the raw files are JST (JST = UT + 9h); this script converts
   them to UT before binning, to match the GIRO-station convention above.

   Japanese stations (code / longitude / latitude):
       Wakkanai/Sarobetsu  WK546   141.75E   45.16N
       Kokubunji (Tokyo)   TO536   139.49E   35.71N
       Yamagawa            YG431   130.62E   31.20N
       Okinawa/Ogimi       OK426   128.15E   26.68N

REQUIREMENTS
------------
    pip install requests pandas numpy matplotlib

USAGE
-----
    python plot_foes_doy_ut.py --station LM42B --year-start 2015 --year-end 2024
    python plot_foes_doy_ut.py --station PE43K --year-start 2016 --year-end 2024 --doy-bin 5
    python plot_foes_doy_ut.py --station TO536 --year-start 2015 --year-end 2024
    python plot_foes_doy_ut.py --station WK546 --year-start 2015 --year-end 2024 --per-year
"""

import argparse
import sys
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial", "Helvetica", "DejaVu Sans"]
import requests

STATIONS = {
    # Western Australia -- served live by GIRO/DIDBase FastChar API
    # (AWST = Australian Western Standard Time, UTC+8, no daylight saving)
    "LM42B": {"name": "Learmonth", "lon": 114.10, "lat": -21.8, "source": "GIRO",
              "utc_offset": 8, "tz_label": "AWST"},
    "PE43K": {"name": "Perth", "lon": 116.13, "lat": -32.0, "source": "GIRO",
              "utc_offset": 8, "tz_label": "AWST"},
    # Japan -- manually-scaled hourly values from NICT WDC for Ionosphere
    # (JST = Japan Standard Time, UTC+9, no daylight saving)
    "WK546": {"name": "Wakkanai/Sarobetsu", "lon": 141.75, "lat": 45.16, "source": "NICT",
              "utc_offset": 9, "tz_label": "JST"},
    "TO536": {"name": "Kokubunji", "lon": 139.49, "lat": 35.71, "source": "NICT",
              "utc_offset": 9, "tz_label": "JST"},
    "YG431": {"name": "Yamagawa", "lon": 130.62, "lat": 31.20, "source": "NICT",
              "utc_offset": 9, "tz_label": "JST"},
    "OK426": {"name": "Okinawa/Ogimi", "lon": 128.15, "lat": 26.68, "source": "NICT",
              "utc_offset": 9, "tz_label": "JST"},
}

FASTCHAR_URL = "https://lgdc.uml.edu/fastchar/getbest"
NICT_URL_TMPL = ("http://wdc.nict.go.jp/Ionosphere/archive/observation-history/"
                  "factor-manual-{code}-{year}H.sjis.txt")


def fetch_year_giro(ursi_code: str, year: int, char_name: str = "foEs",
                     max_retries: int = 5) -> str:
    """Download one calendar year of scaled characteristic data as raw text.

    A full year fits in a single request. The server rate-limits bursts of
    requests (HTTP 429), so this retries with backoff and callers should
    still pause between successive years (see download_range).
    """
    params = {
        "ursiCode": ursi_code,
        "charName": char_name,
        "DMUF": "3000",
        "fromDate": f"{year}/01/01 00:00:00",
        "toDate": f"{year}/12/31 23:59:59",
    }
    delay = 5
    for attempt in range(max_retries):
        resp = requests.get(FASTCHAR_URL, params=params, timeout=120)
        if resp.status_code == 200:
            return resp.text
        if resp.status_code == 429:
            print(f"    rate-limited, waiting {delay}s before retry "
                  f"({attempt + 1}/{max_retries})...")
            time.sleep(delay)
            delay *= 2
            continue
        resp.raise_for_status()
    raise RuntimeError(f"Failed to download {year} for {ursi_code} "
                        f"after {max_retries} retries")


def parse_fastchar_text(text: str, char_name: str = "foEs") -> pd.DataFrame:
    """Parse FastChar.GetBest text output into a DataFrame(time, value, cs).

    Header line format:  "# Time                    CS  foEs QD"
    Data line format:    "2020-01-01T18:30:00.000Z  65  2.55 //"
    A value of '//' (or any non-numeric token) means no Es was scaled at
    that time and is stored as NaN.
    """
    col_idx = None
    times, values, cs_scores = [], [], []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            body = line.lstrip("#").strip()
            toks = body.split()
            if len(toks) >= 2 and toks[0].lower() == "time":
                if char_name in toks:
                    col_idx = toks.index(char_name)
            continue
        if col_idx is None:
            continue

        fields = line.split()
        if len(fields) <= col_idx:
            continue

        try:
            t = pd.Timestamp(fields[0])
        except ValueError:
            continue

        raw_val = fields[col_idx]
        try:
            val = float(raw_val)
        except ValueError:
            val = np.nan  # e.g. '//' -> no Es detected

        try:
            cs = float(fields[1])
        except ValueError:
            cs = np.nan

        times.append(t)
        values.append(val)
        cs_scores.append(cs)

    return pd.DataFrame({"time": times, char_name: values, "CS": cs_scores})


def fetch_year_nict(code: str, year: int) -> str | None:
    """Download one calendar year of NICT manually-scaled hourly data.

    Returns the decoded (Shift-JIS) text, or None if that station/year
    combination has no file (not all years exist for all stations).
    """
    url = NICT_URL_TMPL.format(code=code, year=year)
    resp = requests.get(url, timeout=60)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.content.decode("shift_jis", errors="replace")


_NUM_RE = None  # compiled lazily to keep the top-level import list small


def _leading_number(token: str) -> float:
    """Extract a leading integer from a NICT value+qualifier token.

    Fields look like ' 33JA' (value 33, qualifier letters 'JA'), '16EB',
    or a bare qualifier like 'G' / blanks when nothing was scaled.
    """
    global _NUM_RE
    if _NUM_RE is None:
        import re
        _NUM_RE = re.compile(r"\s*(\d+)")
    m = _NUM_RE.match(token)
    return float(m.group(1)) if m else np.nan


def parse_nict_text(text: str, char_name: str = "foEs") -> pd.DataFrame:
    """Parse a NICT factor-manual-<code>-<year>H.sjis.txt file.

    Header line (starts with '#'):
        "#                    fmin ,foE  ,h'E  ,foEs ,h'Es ,TYPES,..."
    Data line:
        "TO536,20200101000000: 16  ,     ,     , 33JA,122  ,F1   ,..."
    Comma-splitting the data line gives tokens[0]="TO536",
    tokens[1]="20200101000000: 16  " (timestamp + header[0]'s value glued
    together), tokens[2]=header[1]'s value, tokens[3]=header[2]'s value,
    etc. -- i.e. tokens[i+1] holds header[i]'s value for i >= 1, while
    header[0] has to be split out of tokens[1] separately.
    Frequency-type values (foEs included) are encoded as MHz x 10.
    Times in the file are JST; they are converted to UT here.
    """
    col_names = None
    col_idx = None
    times, values = [], []

    for raw_line in text.splitlines():
        line = raw_line.strip("\r\n")
        if not line.strip():
            continue
        if line.startswith("#"):
            col_names = [c.strip() for c in line.lstrip("#").split(",")]
            col_idx = col_names.index(char_name) if char_name in col_names else None
            continue
        if col_idx is None:
            continue

        tokens = line.split(",")
        if len(tokens) < 2:
            continue
        ts_str, _, val0_str = tokens[1].partition(":")
        ts_str = ts_str.strip()
        if len(ts_str) < 12:
            continue
        try:
            t_jst = pd.Timestamp(
                year=int(ts_str[0:4]), month=int(ts_str[4:6]), day=int(ts_str[6:8]),
                hour=int(ts_str[8:10]), minute=int(ts_str[10:12]))
        except ValueError:
            continue

        if col_idx == 0:
            raw_val = val0_str
        else:
            field_idx = col_idx + 1
            if field_idx >= len(tokens):
                continue
            raw_val = tokens[field_idx]

        num = _leading_number(raw_val)
        val = num / 10.0 if np.isfinite(num) else np.nan

        times.append(t_jst - pd.Timedelta(hours=9))  # JST -> UT
        values.append(val)

    return pd.DataFrame({"time": times, char_name: values,
                          "CS": np.full(len(times), 999.0)})


def download_range(station_code: str, year_start: int, year_end: int,
                    char_name: str = "foEs", cache_csv: Path | None = None,
                    inter_year_delay: float | None = None) -> pd.DataFrame:
    """Download (or load from cache) foEs for [year_start, year_end]."""
    if cache_csv is not None and cache_csv.exists():
        print(f"Loading cached data from {cache_csv}")
        df = pd.read_csv(cache_csv, parse_dates=["time"])
        return df

    source = STATIONS[station_code]["source"]
    delay = inter_year_delay if inter_year_delay is not None else (3.0 if source == "GIRO" else 0.5)

    frames = []
    for year in range(year_start, year_end + 1):
        print(f"  downloading {station_code} {char_name} {year} ...")
        if source == "GIRO":
            text = fetch_year_giro(station_code, year, char_name=char_name)
            df_year = parse_fastchar_text(text, char_name=char_name)
        else:
            text = fetch_year_nict(station_code, year)
            if text is None:
                print(f"    -> no file for {year}, skipping")
                time.sleep(delay)
                continue
            df_year = parse_nict_text(text, char_name=char_name)
        print(f"    -> {len(df_year)} records")
        frames.append(df_year)
        time.sleep(delay)  # be polite to the server

    if not frames:
        return pd.DataFrame({"time": [], char_name: [], "CS": []})

    df = pd.concat(frames, ignore_index=True)
    df = df.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)

    if cache_csv is not None:
        cache_csv.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache_csv, index=False)
        print(f"Cached raw data to {cache_csv}")

    return df


def bin_doy_ut(df: pd.DataFrame, char_name: str = "foEs",
                doy_bin: int = 1, ut_bin: float = 1.0,
                min_cs: float = 0.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bin observations onto a DOY x UT grid and average foEs in each cell.

    Rows where foEs is NaN (no Es scaled) are excluded from the mean --
    i.e. this plots the *strength* of Es when present, not occurrence rate.
    Rows with CS < min_cs (autoscaling confidence score) are also dropped;
    CS == 999 (manual scaling) and CS == -1 (unknown) are always kept.
    """
    d = df.dropna(subset=[char_name]).copy()
    d = d[(d["CS"] >= min_cs) | (d["CS"] == 999) | (d["CS"] == -1)]

    d["doy"] = d["time"].dt.dayofyear
    d["ut"] = d["time"].dt.hour + d["time"].dt.minute / 60.0

    doy_edges = np.arange(0.5, 366.5 + doy_bin, doy_bin)
    ut_edges = np.arange(0, 24 + ut_bin, ut_bin)

    d["doy_bin"] = pd.cut(d["doy"], doy_edges, labels=False)
    d["ut_bin"] = pd.cut(d["ut"], ut_edges, labels=False, include_lowest=True)

    grid = np.full((len(ut_edges) - 1, len(doy_edges) - 1), np.nan)
    grouped = d.groupby(["ut_bin", "doy_bin"])[char_name].mean()
    for (iut, idoy), val in grouped.items():
        grid[int(iut), int(idoy)] = val

    doy_centers = 0.5 * (doy_edges[:-1] + doy_edges[1:])
    ut_centers = 0.5 * (ut_edges[:-1] + ut_edges[1:])
    return doy_centers, ut_centers, grid


def plot_doy_ut(doy_edges_or_centers, ut_edges_or_centers, grid,
                 station_label: str, year_start: int, year_end: int,
                 char_name: str = "foEs", out_png: Path | None = None,
                 utc_offset: float | None = None, tz_label: str | None = None):
    fig, ax = plt.subplots(figsize=(10, 6))

    mesh = ax.pcolormesh(doy_edges_or_centers, ut_edges_or_centers, grid,
                          shading="nearest", cmap="rainbow", vmin=0, vmax=10)
    cbar = fig.colorbar(mesh, ax=ax, pad=0.08)
    cbar.set_label(f"{char_name} (MHz)")

    ax.set_xlabel("Day of Year (DOY)")
    ax.set_ylabel("UT (hour)")
    ax.set_ylim(0, 24)
    ax.set_yticks(np.arange(0, 25, 3))
    ax.set_title(f"{char_name} vs DOY / UT -- {station_label} "
                 f"({year_start}-{year_end})")

    # Secondary right axis: local standard time (e.g. AWST/JST), wrapped to
    # 0-24 h with the same 3-hour tick spacing as the UT axis. Local time is
    # UT + utc_offset, so a given local hour sits at UT = (local - offset) mod 24.
    if utc_offset is not None:
        local_hours = np.arange(0, 24, 3)
        tick_ut = np.sort((local_hours - utc_offset) % 24)
        tick_labels = [str(int(round((u + utc_offset) % 24))) for u in tick_ut]
        ax_right = ax.secondary_yaxis("right")
        ax_right.set_yticks(tick_ut)
        ax_right.set_yticklabels(tick_labels)
        ax_right.set_ylabel(f"{tz_label} (hour)" if tz_label else "Local time (hour)")

    # Secondary top axis: month names as an auxiliary guide to the DOY axis
    # (non-leap-year day-of-year boundaries; close enough for a visual guide).
    month_starts = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335, 366]
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    month_mids = [0.5 * (a + b) for a, b in zip(month_starts[:-1], month_starts[1:])]

    # Black/white "railroad-track" dashed lines at month boundaries, so they
    # stay visible against every color in the rainbow colormap. Skip the
    # DOY=1 and DOY=366 edges (start of Jan / end of Dec).
    for x in month_starts[1:-1]:
        ax.axvline(x, color="black", linestyle=(0, (4, 4)), linewidth=1.0, zorder=5)
        ax.axvline(x, color="white", linestyle=(4, (4, 4)), linewidth=1.0, zorder=5)

    ax_top = ax.secondary_xaxis("top")
    ax_top.set_xticks(month_starts)
    ax_top.set_xticklabels([])
    ax_top.tick_params(which="major", length=4)
    ax_top.set_xticks(month_mids, minor=True)
    ax_top.set_xticklabels(month_names, minor=True)
    ax_top.tick_params(which="minor", length=0)

    fig.tight_layout()
    if out_png is not None:
        fig.savefig(out_png, dpi=200)
        print(f"Figure saved to {out_png}")
    plt.show()
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--station", default="LM42B", choices=list(STATIONS),
                     help="Station code: LM42B/PE43K (WA, GIRO) or "
                          "WK546/TO536/YG431/OK426 (Japan, NICT). "
                          "Default: LM42B (Learmonth)")
    ap.add_argument("--year-start", type=int, default=2015)
    ap.add_argument("--year-end", type=int, default=2024)
    ap.add_argument("--doy-bin", type=int, default=1,
                     help="Bin width along DOY axis in days (default: 1)")
    ap.add_argument("--ut-bin", type=float, default=1.0,
                     help="Bin width along UT axis in hours (default: 1.0)")
    ap.add_argument("--min-cs", type=float, default=0.0,
                     help="Minimum autoscaling confidence score to keep "
                          "(0-100; default: 0, i.e. keep everything)")
    ap.add_argument("--outdir", default=".", type=Path)
    ap.add_argument("--no-cache", action="store_true",
                     help="Ignore/overwrite any cached CSV and re-download")
    ap.add_argument("--per-year", action="store_true",
                     help="In addition to the combined plot, save one "
                          "DOY-vs-UT plot per individual year")
    args = ap.parse_args()

    station = STATIONS[args.station]
    station_label = f"{station['name']} ({args.station})"

    args.outdir.mkdir(parents=True, exist_ok=True)
    cache_csv = args.outdir / f"{args.station}_foEs_{args.year_start}-{args.year_end}.csv"
    if args.no_cache and cache_csv.exists():
        cache_csv.unlink()

    print(f"Station: {station_label}, lon={station['lon']}E, lat={station['lat']}")
    df = download_range(args.station, args.year_start, args.year_end,
                         char_name="foEs", cache_csv=cache_csv)

    if df.empty:
        print("No data downloaded -- aborting.", file=sys.stderr)
        sys.exit(1)

    if args.per_year:
        for year in range(args.year_start, args.year_end + 1):
            df_year = df[df["time"].dt.year == year]
            if df_year.empty:
                print(f"  {year}: no data, skipping")
                continue
            doy_c, ut_c, grid = bin_doy_ut(df_year, char_name="foEs",
                                            doy_bin=args.doy_bin, ut_bin=args.ut_bin,
                                            min_cs=args.min_cs)
            out_png = args.outdir / f"{args.station}_foEs_DOYvsUT_{year}.png"
            plot_doy_ut(doy_c, ut_c, grid, station_label, year, year,
                        char_name="foEs", out_png=out_png,
                        utc_offset=station["utc_offset"], tz_label=station["tz_label"])
    else:
        doy_c, ut_c, grid = bin_doy_ut(df, char_name="foEs",
                                        doy_bin=args.doy_bin, ut_bin=args.ut_bin,
                                        min_cs=args.min_cs)

        out_png = args.outdir / f"{args.station}_foEs_DOYvsUT_{args.year_start}-{args.year_end}.png"
        plot_doy_ut(doy_c, ut_c, grid, station_label,
                    args.year_start, args.year_end, char_name="foEs",
                    out_png=out_png,
                    utc_offset=station["utc_offset"], tz_label=station["tz_label"])


if __name__ == "__main__":
    main()
