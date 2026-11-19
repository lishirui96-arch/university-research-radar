from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re

from playwright.sync_api import Page, sync_playwright


FIELDS = {
    "15": ("化学工程 · Chemical Engineering", 24),
    "16": ("化学 · Chemistry", 119),
    "17": ("计算机科学 · Computer Science", 265),
    "21": ("能源 · Energy", 44),
    "22": ("工程学 · Engineering", 467),
    "25": ("材料科学 · Materials Science", 144),
}
PERIODS = {90: "近90天", 360: "近360天"}


def _click_segment(page: Page, label: str) -> None:
    page.get_by_text(label, exact=True).first.click()
    page.wait_for_timeout(250)


def _wait_for_lines(page: Page, expected: int, period_days: int) -> None:
    page.wait_for_function(
        r"""
        options => {
          const charts = [...document.querySelectorAll('[data-testid="stVegaLiteChart"]')];
          const pattern = options.periodDays === 90 ? /^\d{2}-\d{2}$/ : /^\d{4}-\d{2}$/;
          return charts.length === 2
            && charts.every(chart => {
              const ticks = [...chart.querySelectorAll('svg text')]
                .map(element => (element.textContent || '').trim())
                .filter(text => pattern.test(text));
              return chart.querySelectorAll('.mark-line').length === options.expected
                && ticks.length === 13;
            });
        }
        """,
        arg={"expected": expected, "periodDays": period_days},
        timeout=120_000,
    )


def _chart_state(page: Page, expected_lines: int, period_days: int) -> dict:
    charts = page.locator('[data-testid="stVegaLiteChart"]')
    states = []
    tick_pattern = re.compile(r"^\d{2}-\d{2}$" if period_days == 90 else r"^\d{4}-\d{2}$")
    for index in range(2):
        chart = charts.nth(index)
        chart.scroll_into_view_if_needed()
        texts = [
            text.strip()
            for text in chart.locator("svg text").evaluate_all(
                "elements => elements.map(element => element.textContent)"
            )
            if text is not None
        ]
        ticks = [text for text in texts if tick_pattern.fullmatch(text)]
        legend = [
            text.strip()
            for text in chart.locator(".role-legend text").evaluate_all(
                "elements => elements.map(element => element.textContent)"
            )
            if text is not None and text.strip()
        ]
        states.append(
            {
                "line_count": chart.locator(".mark-line").count(),
                "point_count": chart.locator(".mark-symbol path").count(),
                "ticks": ticks,
                "legend": legend,
                "legend_is_chinese": bool(legend) and all(
                    any("\u4e00" <= char <= "\u9fff" for char in label)
                    for label in legend
                ),
            }
        )
    if any(state["line_count"] != expected_lines for state in states):
        raise AssertionError(f"Expected {expected_lines} lines per chart: {states}")
    if states[0]["ticks"] != states[1]["ticks"] or len(states[0]["ticks"]) != 13:
        raise AssertionError(f"Chart time buckets differ: {states}")
    if not all(state["legend_is_chinese"] for state in states):
        raise AssertionError(f"Non-Chinese legend found: {states}")
    return {"works_chart": states[0], "growth_chart": states[1]}


def _verify_tooltip(page: Page) -> str:
    point = page.locator('[data-testid="stVegaLiteChart"]').first.locator(
        ".mark-symbol path"
    ).first
    point.hover(force=True)
    tooltip = page.locator(".vg-tooltip")
    tooltip.wait_for(state="visible", timeout=10_000)
    text = tooltip.inner_text()
    for expected in ("统计周期", "新增 Works", "环比", "OpenAlex 英文名称", "中文名称状态"):
        if expected not in text:
            raise AssertionError(f"Tooltip is missing {expected}: {text}")
    return text


def audit_browser(url: str, output_dir: Path, chrome: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=str(chrome), headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1200})
        page.goto(url, wait_until="networkidle", timeout=120_000)
        page.get_by_text("全球科研热点监测", exact=True).wait_for(timeout=120_000)
        combo = page.locator('[data-testid="stSelectbox"] [role="combobox"]')
        for field_id, (field_label, topic_count) in FIELDS.items():
            combo.click()
            page.get_by_role("option", name=field_label, exact=True).click()
            page.wait_for_function(
                """expected => document.querySelector('[role="combobox"]')?.value === expected""",
                arg=field_label,
                timeout=120_000,
            )
            for period_days, period_label in PERIODS.items():
                _click_segment(page, period_label)
                for top_n in (5, 10):
                    _click_segment(page, f"TOP {top_n}")
                    _wait_for_lines(page, top_n, period_days)
                    state = _chart_state(page, top_n, period_days)
                    tooltip = _verify_tooltip(page)
                    results.append(
                        {
                            "field_id": field_id,
                            "field_label": field_label,
                            "field_topic_count": topic_count,
                            "period_days": period_days,
                            "selection_mode": f"TOP {top_n}",
                            "chart_state": state,
                            "tooltip_verified": True,
                            "tooltip_length": len(tooltip),
                        }
                    )
                page.screenshot(
                    path=output_dir / f"field-{field_id}-{period_days}d-top10.png",
                    full_page=True,
                )
            _click_segment(page, "自定义")
            _wait_for_lines(page, 5, 360)
            results.append(
                {
                    "field_id": field_id,
                    "field_label": field_label,
                    "field_topic_count": topic_count,
                    "period_days": 360,
                    "selection_mode": "custom",
                    "chart_state": _chart_state(page, 5, 360),
                    "tooltip_verified": bool(_verify_tooltip(page)),
                }
            )
            _click_segment(page, "TOP 5")
            _click_segment(page, "增长率")
            _wait_for_lines(page, 5, 360)
            results.append(
                {
                    "field_id": field_id,
                    "field_label": field_label,
                    "field_topic_count": topic_count,
                    "period_days": 360,
                    "selection_mode": "TOP 5 / growth ranking",
                    "chart_state": _chart_state(page, 5, 360),
                    "tooltip_verified": bool(_verify_tooltip(page)),
                }
            )
            _click_segment(page, "增长量")
        browser.close()
    return {
        "url": url,
        "generated_at": datetime.now().astimezone().isoformat(),
        "checks": len(results),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--chrome",
        type=Path,
        default=Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    )
    args = parser.parse_args()
    audit = audit_browser(args.url, args.output_dir, args.chrome)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"checks": audit["checks"], "url": audit["url"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
