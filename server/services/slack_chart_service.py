"""Chart generation service for Slack visualizations."""

from __future__ import annotations

import json
from typing import Any, Literal
from urllib.parse import quote

ChartType = Literal["bar", "line", "pie", "doughnut", "radar", "polarArea", "horizontalBar", "scatter"]


class ChartService:
    """Service for generating chart URLs using QuickChart.io."""

    BASE_URL = "https://quickchart.io/chart"

    @staticmethod
    def generate_chart_url(
        chart_type: ChartType,
        labels: list[str],
        datasets: list[dict[str, Any]],
        title: str | None = None,
        width: int = 600,
        height: int = 400,
        background_color: str = "white",
    ) -> str:
        """
        Generate a QuickChart URL for displaying charts in Slack.

        Args:
            chart_type: Type of chart (bar, line, pie, etc.)
            labels: X-axis labels
            datasets: List of dataset objects with label, data, and optional styling
            title: Optional chart title
            width: Chart width in pixels (default 600)
            height: Chart height in pixels (default 400)
            background_color: Background color (default white)

        Returns:
            QuickChart URL string

        Example:
            url = ChartService.generate_chart_url(
                chart_type="bar",
                labels=["Q1", "Q2", "Q3", "Q4"],
                datasets=[{
                    "label": "Revenue",
                    "data": [100, 150, 200, 180]
                }],
                title="Quarterly Revenue"
            )
        """
        chart_config = ChartService._build_chart_config(
            chart_type=chart_type,
            labels=labels,
            datasets=datasets,
            title=title,
            background_color=background_color,
        )

        encoded_config = quote(json.dumps(chart_config))
        return f"{ChartService.BASE_URL}?c={encoded_config}&w={width}&h={height}&bkg={background_color}&version=4"

    @staticmethod
    def _build_chart_config(
        chart_type: ChartType,
        labels: list[str],
        datasets: list[dict[str, Any]],
        title: str | None,
        background_color: str,
    ) -> dict[str, Any]:
        """Build Chart.js configuration object with beautiful Byaan styling."""
        is_horizontal = chart_type == "horizontalBar"
        actual_chart_type = "bar" if chart_type == "horizontalBar" else chart_type

        options: dict[str, Any] = {
            "plugins": {
                "legend": {
                    "display": True,
                    "position": "top",
                    "labels": {
                        "usePointStyle": True,
                        "pointStyle": "circle",
                    },
                },
            },
        }

        if is_horizontal:
            options["indexAxis"] = "y"

        if title:
            options["plugins"]["title"] = {
                "display": True,
                "text": title,
            }

        if chart_type in ["bar", "horizontalBar", "line"]:
            options["scales"] = {
                "y": {"beginAtZero": True},
                "x": {},
            }

        formatted_datasets = []
        for idx, dataset in enumerate(datasets):
            formatted_ds = {
                "label": dataset.get("label", f"Dataset {idx + 1}"),
                "data": dataset.get("data", []),
            }

            if "backgroundColor" in dataset:
                formatted_ds["backgroundColor"] = dataset["backgroundColor"]
            elif chart_type in ["bar", "horizontalBar"]:
                formatted_ds["backgroundColor"] = ChartService._get_color(idx)
                formatted_ds["borderRadius"] = 8
                formatted_ds["borderSkipped"] = False
            elif chart_type in ["line"]:
                formatted_ds["borderColor"] = ChartService._get_color(idx)
                formatted_ds["fill"] = False
                formatted_ds["tension"] = 0.4
                formatted_ds["borderWidth"] = 3
            elif chart_type in ["pie", "doughnut"]:
                formatted_ds["backgroundColor"] = [ChartService._get_color(i) for i in range(len(labels))]
                formatted_ds["borderWidth"] = 2
                formatted_ds["borderColor"] = "#ffffff"

            if "borderColor" in dataset:
                formatted_ds["borderColor"] = dataset["borderColor"]

            formatted_datasets.append(formatted_ds)

        config: dict[str, Any] = {
            "type": actual_chart_type,
            "data": {"labels": labels, "datasets": formatted_datasets},
            "options": options,
        }

        return config

    @staticmethod
    def _get_color(index: int) -> str:
        """Get color from Byaan theme palette."""
        colors = [
            "#FF7700",
            "#FF66CC",
            "#FBBF24",
            "#D946EF",
            "#ec4899",
            "#f59e0b",
            "#f43f5e",
            "#ef4444",
        ]
        return colors[index % len(colors)]
