# Maintainer notes

Implementation decisions and conventions that aren't obvious from the code
alone. See `README.md` for usage; this file is about *why*, for picking
the project back up later.

## Per-station plot settings

- **UT bin width:** `LM42B` and `PE43K` (Western Australia, GIRO) use
  `--ut-bin 0.25` (15 min) since their source data has that native
  cadence. The 4 Japan stations (`WK546`, `TO536`, `YG431`, `OK426`) use
  the default 1.0 h bin, because NICT's archive is natively hourly --
  finer bins there would just add empty cells, not resolution.
- **Colormap/scale:** hardcoded in `plot_doy_ut()` as `cmap="rainbow"`,
  `vmin=0`, `vmax=10` MHz -- not a CLI flag, deliberately fixed so plots
  are comparable across stations/years.
- **Month-boundary guide lines:** black/white dashed vertical lines at
  internal month starts (Feb-Dec) only; the DOY=1/366 edges are
  intentionally skipped.
- **Right-side local-time axis:** shows AWST (UTC+8) for the WA stations
  and JST (UTC+9) for the Japan stations, via `utc_offset`/`tz_label` in
  the `STATIONS` dict in `plot_foes_doy_ut.py` -- add new stations there
  rather than hardcoding a timezone in the plotting function.
- **Colorbar spacing:** `fig.colorbar(mesh, ax=ax, pad=0.08)` -- tuned by
  eye against the local-time axis labels (0.14 was too far right, the
  matplotlib default was too close).

## Regenerating everything

Output lives in one directory per station (`LM42B/`, `PE43K/`, `WK546/`,
`TO536/`, `YG431/`, `OK426/`), each holding a cached CSV, the combined
2015-2024 plot, and 10 per-year plots. To rebuild all 66 PNGs after a
styling change:

```bash
for s in LM42B PE43K; do
  python plot_foes_doy_ut.py --station $s --year-start 2015 --year-end 2024 --ut-bin 0.25 --outdir $s
  python plot_foes_doy_ut.py --station $s --year-start 2015 --year-end 2024 --ut-bin 0.25 --per-year --outdir $s
done
for s in WK546 TO536 YG431 OK426; do
  python plot_foes_doy_ut.py --station $s --year-start 2015 --year-end 2024 --outdir $s
  python plot_foes_doy_ut.py --station $s --year-start 2015 --year-end 2024 --per-year --outdir $s
done
```

The per-station CSV caches make this fast (no re-download) unless
`--no-cache` is passed.

## Known data quirk

Kokubunji (`TO536`) has a handful of anomalously high foEs values in
mid-May 2020 (e.g. 24.8 MHz on 2020-05-14). Confirmed present in NICT's
raw source file, not a parsing bug -- left unfiltered by design.

## History

The original implementation was an IDL script (`giro_es_statistics.pro`
+ `giro.go`), covering only the GIRO/WA stations and computing a
month x local-time occurrence-rate matrix. Both files were removed from
this repo (and GitHub) once `plot_foes_doy_ut.py` covered the same ground
in Python with more stations and a DOY x UT value plot instead.
