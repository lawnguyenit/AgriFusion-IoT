from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure


FIGURE_FACE = "#fffaf2"
AXIS_FACE = "#fffdf8"
GRID_COLOR = "#d8e4d2"
SPINE_COLOR = "#d7decf"
TITLE_COLOR = "#243a2e"
TEXT_COLOR = "#49604c"


@dataclass(frozen=True)
class ReportMetricSpec:
    group: str
    key: str
    label: str
    unit: str
    color: str
    axis_id: str = "left"


@dataclass(frozen=True)
class ReportChartSpec:
    chart_id: str
    title: str
    subtitle: str
    metrics: tuple[ReportMetricSpec, ...]
    left_axis_label: str
    right_axis_label: str | None = None


CHART_SPECS: tuple[ReportChartSpec, ...] = (
    ReportChartSpec(
        chart_id="air",
        title="Khong khi canh tac",
        subtitle="Nhiet do va do am khong khi tu payload result/history/air.",
        metrics=(
            ReportMetricSpec("air", "temperature_c", "Nhiet do khong khi", "degC", "#d6a33b", "left"),
            ReportMetricSpec("air", "humidity_pct", "Do am khong khi", "%", "#2f8f83", "right"),
        ),
        left_axis_label="Nhiet do (degC)",
        right_axis_label="Do am (%)",
    ),
    ReportChartSpec(
        chart_id="soil",
        title="Vi khi hau dat",
        subtitle="Nhiet do va do am dat tu payload result/history/soil.",
        metrics=(
            ReportMetricSpec("soil", "temperature_c", "Nhiet do dat", "degC", "#cf7243", "left"),
            ReportMetricSpec("soil", "humidity_pct", "Do am dat", "%", "#4d95bf", "right"),
        ),
        left_axis_label="Nhiet do (degC)",
        right_axis_label="Do am (%)",
    ),
    ReportChartSpec(
        chart_id="soil_chemistry",
        title="Hoa hoc dat",
        subtitle="pH va EC dat duoc tach rieng de tranh nen chung tren mot thang chuan hoa.",
        metrics=(
            ReportMetricSpec("soil", "ph", "pH dat", "pH", "#7e9946", "left"),
            ReportMetricSpec("soil", "ec_us_cm", "EC dat", "uS/cm", "#b35f70", "right"),
        ),
        left_axis_label="pH",
        right_axis_label="EC (uS/cm)",
    ),
    ReportChartSpec(
        chart_id="npk",
        title="Dinh duong NPK",
        subtitle="Ba thanh phan N, P, K dung chung don vi ppm nen de chung mot truc.",
        metrics=(
            ReportMetricSpec("npk", "n_ppm", "Nito (N)", "ppm", "#719d4b", "left"),
            ReportMetricSpec("npk", "p_ppm", "Photpho (P)", "ppm", "#e0aa39", "left"),
            ReportMetricSpec("npk", "k_ppm", "Kali (K)", "ppm", "#d97b48", "left"),
        ),
        left_axis_label="NPK (ppm)",
    ),
)


def render_report_chart_bundle(
    *,
    payload: dict[str, Any],
    output_root: Path,
    timezone_name: str,
    updated_at_local: str,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    frames = _build_group_frames(payload, timezone_name=timezone_name)
    chart_entries: list[dict[str, Any]] = []

    for spec in CHART_SPECS:
        chart_entry = _render_single_chart(
            spec=spec,
            frames=frames,
            output_root=output_root,
            updated_at_local=updated_at_local,
        )
        if chart_entry is not None:
            chart_entries.append(chart_entry)

    summary_entry = _render_summary_panel(
        specs=CHART_SPECS,
        frames=frames,
        output_root=output_root,
        updated_at_local=updated_at_local,
    )
    if summary_entry is not None:
        chart_entries.append(summary_entry)

    available_ranges = [
        entry["timeRange"]
        for entry in chart_entries
        if isinstance(entry.get("timeRange"), dict) and entry["timeRange"].get("startTs") is not None
    ]
    return {
        "status": "ready" if chart_entries else "no_chart_data",
        "outputRoot": str(output_root),
        "updatedAtLocal": updated_at_local,
        "chartCount": len(chart_entries),
        "historyGroups": {
            group: int(len(frame.index))
            for group, frame in frames.items()
        },
        "timeRange": _merge_ranges(available_ranges),
        "charts": chart_entries,
    }


def _build_group_frames(payload: dict[str, Any], *, timezone_name: str) -> dict[str, pd.DataFrame]:
    history_payload = payload.get("history", {})
    frames: dict[str, pd.DataFrame] = {}
    for group_name, group_records in history_payload.items():
        if not isinstance(group_records, dict) or not group_records:
            frames[group_name] = pd.DataFrame()
            continue
        rows: list[dict[str, Any]] = []
        for ts_text, record in sorted(group_records.items(), key=lambda item: int(item[0])):
            if not isinstance(record, dict):
                continue
            ts = _coerce_int(record.get("ts", ts_text))
            if ts is None:
                continue
            row = {"ts": ts, "dt": pd.Timestamp(ts, unit="s", tz="UTC").tz_convert(timezone_name)}
            row.update(record)
            rows.append(row)
        frame = pd.DataFrame(rows)
        frames[group_name] = frame.sort_values("ts").reset_index(drop=True) if not frame.empty else pd.DataFrame()
    return frames


def _render_single_chart(
    *,
    spec: ReportChartSpec,
    frames: dict[str, pd.DataFrame],
    output_root: Path,
    updated_at_local: str,
) -> dict[str, Any] | None:
    series_payload = _build_series_payload(spec=spec, frames=frames)
    if not series_payload:
        return None

    figure, axis_left = plt.subplots(figsize=(14.8, 6.8), constrained_layout=True)
    axis_right = axis_left.twinx() if spec.right_axis_label else None
    _style_figure(figure)
    _style_axis(axis_left, y_label=spec.left_axis_label, show_left=True, show_right=axis_right is None)
    if axis_right is not None:
        _style_axis(axis_right, y_label=spec.right_axis_label or "", show_left=False, show_right=True)

    legend_handles = []
    for item in series_payload:
        axis = axis_left if item["metric"].axis_id == "left" else axis_right
        if axis is None:
            continue
        handle = _plot_metric(axis, item["frame"], item["metric"])
        if handle is not None:
            legend_handles.append(handle)

    _finalize_axes(
        figure=figure,
        axis_left=axis_left,
        axis_right=axis_right,
        title=spec.title,
        subtitle=spec.subtitle,
        updated_at_local=updated_at_local,
        legend_handles=legend_handles,
    )

    base_name = spec.chart_id
    svg_path = output_root / f"{base_name}.svg"
    png_path = output_root / f"{base_name}.png"
    figure.savefig(svg_path, format="svg", bbox_inches="tight")
    figure.savefig(png_path, format="png", dpi=320, bbox_inches="tight", facecolor=figure.get_facecolor())
    plt.close(figure)

    metric_ids = [f"{metric.group}.{metric.key}" for metric in spec.metrics]
    time_range = _extract_range(series_payload)
    return {
        "chartId": spec.chart_id,
        "title": spec.title,
        "metricIds": metric_ids,
        "timeRange": time_range,
        "svgPath": str(svg_path),
        "pngPath": str(png_path),
    }


def _render_summary_panel(
    *,
    specs: tuple[ReportChartSpec, ...],
    frames: dict[str, pd.DataFrame],
    output_root: Path,
    updated_at_local: str,
) -> dict[str, Any] | None:
    available = [(spec, _build_series_payload(spec=spec, frames=frames)) for spec in specs]
    available = [(spec, payload) for spec, payload in available if payload]
    if not available:
        return None

    figure, axes = plt.subplots(2, 2, figsize=(16.6, 10.8), constrained_layout=True)
    _style_figure(figure)
    axis_pairs = axes.flatten()
    subplot_specs = [axis.get_subplotspec() for axis in axis_pairs]

    for panel_axis in axis_pairs:
        panel_axis.remove()

    rendered_ranges: list[dict[str, int | None]] = []
    for (spec, payload), subplot_spec in zip(available, subplot_specs, strict=False):
        axis_left = figure.add_subplot(subplot_spec)
        axis_right = axis_left.twinx() if spec.right_axis_label else None
        _style_axis(axis_left, y_label=spec.left_axis_label, show_left=True, show_right=axis_right is None)
        if axis_right is not None:
            _style_axis(axis_right, y_label=spec.right_axis_label or "", show_left=False, show_right=True)

        handles = []
        for item in payload:
            axis = axis_left if item["metric"].axis_id == "left" else axis_right
            if axis is None:
                continue
            handle = _plot_metric(axis, item["frame"], item["metric"])
            if handle is not None:
                handles.append(handle)

        range_label = _format_time_range_label(_extract_range(payload))
        axis_left.set_title(
            spec.title,
            loc="left",
            fontsize=15,
            fontweight="bold",
            color=TITLE_COLOR,
            pad=24,
        )
        axis_left.text(
            0.0,
            1.04,
            range_label,
            transform=axis_left.transAxes,
            ha="left",
            va="bottom",
            fontsize=10.5,
            color=TEXT_COLOR,
        )
        if handles:
            axis_left.legend(
                handles=handles,
                loc="upper center",
                bbox_to_anchor=(0.5, 1.02),
                ncol=max(1, min(3, len(handles))),
                frameon=False,
                fontsize=9.5,
            )
        rendered_ranges.append(_extract_range(payload))

    svg_path = output_root / "summary_panel.svg"
    png_path = output_root / "summary_panel.png"
    figure.savefig(svg_path, format="svg", bbox_inches="tight")
    figure.savefig(png_path, format="png", dpi=320, bbox_inches="tight", facecolor=figure.get_facecolor())
    plt.close(figure)

    return {
        "chartId": "summary_panel",
        "title": "Tong hop chart bao cao",
        "metricIds": [
            f"{metric.group}.{metric.key}"
            for spec in specs
            for metric in spec.metrics
        ],
        "timeRange": _merge_ranges(rendered_ranges),
        "svgPath": str(svg_path),
        "pngPath": str(png_path),
    }


def _build_series_payload(
    *,
    spec: ReportChartSpec,
    frames: dict[str, pd.DataFrame],
) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for metric in spec.metrics:
        frame = frames.get(metric.group)
        if frame is None or frame.empty or metric.key not in frame.columns:
            continue
        series_frame = frame.loc[:, ["ts", "dt", metric.key]].copy()
        series_frame[metric.key] = pd.to_numeric(series_frame[metric.key], errors="coerce")
        series_frame = series_frame.dropna(subset=[metric.key])
        if series_frame.empty:
            continue
        payload.append({"metric": metric, "frame": series_frame})
    return payload


def _plot_metric(axis: Axes, frame: pd.DataFrame, metric: ReportMetricSpec):
    handle = axis.plot(
        frame["dt"],
        frame[metric.key],
        color=metric.color,
        linewidth=2.8,
        solid_capstyle="round",
        alpha=0.97,
        label=metric.label,
    )[0]
    last_row = frame.iloc[-1]
    axis.scatter(
        [last_row["dt"]],
        [last_row[metric.key]],
        s=38,
        color=metric.color,
        edgecolors=AXIS_FACE,
        linewidths=1.1,
        zorder=4,
    )
    return handle


def _style_figure(figure: Figure) -> None:
    figure.patch.set_facecolor(FIGURE_FACE)


def _style_axis(axis: Axes, *, y_label: str, show_left: bool, show_right: bool) -> None:
    axis.set_facecolor(AXIS_FACE)
    axis.grid(True, axis="y", color=GRID_COLOR, linewidth=0.8, alpha=0.72)
    axis.grid(False, axis="x")
    axis.tick_params(axis="x", colors=TEXT_COLOR, labelsize=10.5, rotation=0)
    axis.tick_params(axis="y", colors=TEXT_COLOR, labelsize=10.5)
    axis.set_ylabel(y_label, color=TEXT_COLOR, fontsize=11.5, fontweight="bold")
    axis.spines["top"].set_visible(False)
    axis.spines["left"].set_visible(show_left)
    axis.spines["right"].set_visible(show_right)
    axis.spines["bottom"].set_color(SPINE_COLOR)
    if show_left:
        axis.spines["left"].set_color(SPINE_COLOR)
    if show_right:
        axis.spines["right"].set_color(SPINE_COLOR)


def _finalize_axes(
    *,
    figure: Figure,
    axis_left: Axes,
    axis_right: Axes | None,
    title: str,
    subtitle: str,
    updated_at_local: str,
    legend_handles: list[Any],
) -> None:
    axis_left.set_title(
        title,
        loc="left",
        fontsize=18,
        fontweight="bold",
        color=TITLE_COLOR,
        pad=26,
    )
    axis_left.text(
        0.0,
        1.04,
        subtitle,
        transform=axis_left.transAxes,
        ha="left",
        va="bottom",
        fontsize=11,
        color=TEXT_COLOR,
    )
    axis_left.text(
        1.0,
        1.04,
        f"Cap nhat local: {updated_at_local}",
        transform=axis_left.transAxes,
        ha="right",
        va="bottom",
        fontsize=10,
        color=TEXT_COLOR,
    )
    _apply_time_formatter(axis_left)
    if axis_right is not None:
        _apply_time_formatter(axis_right)
    if legend_handles:
        axis_left.legend(
            handles=legend_handles,
            loc="upper center",
            bbox_to_anchor=(0.5, 1.02),
            ncol=max(1, min(3, len(legend_handles))),
            frameon=False,
            fontsize=10.5,
        )
    figure.align_ylabels()


def _apply_time_formatter(axis: Axes) -> None:
    x_min, x_max = axis.get_xlim()
    if x_min == x_max:
        return
    start_dt = mdates.num2date(x_min)
    end_dt = mdates.num2date(x_max)
    span_seconds = max(0.0, (end_dt - start_dt).total_seconds())
    if span_seconds <= 3 * 24 * 3600:
        formatter = mdates.DateFormatter("%d/%m %H:%M")
    elif span_seconds <= 90 * 24 * 3600:
        formatter = mdates.DateFormatter("%d/%m")
    else:
        formatter = mdates.DateFormatter("%m/%Y")
    axis.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=7))
    axis.xaxis.set_major_formatter(formatter)
    for label in axis.get_xticklabels():
        label.set_rotation(16)
        label.set_ha("right")


def _extract_range(series_payload: list[dict[str, Any]]) -> dict[str, int | None]:
    timestamps = [
        int(frame_item["frame"]["ts"].iloc[0])
        for frame_item in series_payload
    ] + [
        int(frame_item["frame"]["ts"].iloc[-1])
        for frame_item in series_payload
    ]
    if not timestamps:
        return {"startTs": None, "endTs": None}
    return {"startTs": min(timestamps), "endTs": max(timestamps)}


def _merge_ranges(ranges: list[dict[str, int | None]]) -> dict[str, int | None]:
    starts = [item.get("startTs") for item in ranges if item.get("startTs") is not None]
    ends = [item.get("endTs") for item in ranges if item.get("endTs") is not None]
    return {
        "startTs": min(starts) if starts else None,
        "endTs": max(ends) if ends else None,
    }


def _format_time_range_label(time_range: dict[str, int | None]) -> str:
    start_ts = time_range.get("startTs")
    end_ts = time_range.get("endTs")
    if start_ts is None or end_ts is None:
        return "Khong co khung thoi gian"
    start_text = datetime.fromtimestamp(start_ts).strftime("%d/%m/%Y")
    end_text = datetime.fromtimestamp(end_ts).strftime("%d/%m/%Y")
    return f"{start_text} -> {end_text}"


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
