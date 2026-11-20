from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path

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
CHART_SELECTOR = '[data-testid="stPlotlyChart"] .js-plotly-plot'


def _click_segment(page: Page, label: str) -> None:
    page.get_by_text(label, exact=True).first.click()
    page.wait_for_timeout(250)


def _wait_for_lines(page: Page, expected: int, period_days: int) -> None:
    page.wait_for_function(
        """
        options => {
          const charts = [...document.querySelectorAll(options.selector)];
          return charts.length === 2
            && charts.every(chart => chart.data?.length === options.expected
              && chart._fullLayout?.xaxis?.fixedrange === false
              && chart._fullLayout.xaxis.minallowed
              && chart._fullLayout.xaxis.maxallowed);
        }
        """,
        arg={
            "selector": CHART_SELECTOR,
            "expected": expected,
            "periodDays": period_days,
        },
        timeout=120_000,
    )


def _chart_state(page: Page, expected_lines: int, period_days: int) -> dict:
    charts = page.locator(CHART_SELECTOR)
    states = []
    for index in range(2):
        chart = charts.nth(index)
        chart.scroll_into_view_if_needed()
        state = chart.evaluate(
            """element => ({
              line_count: element.data.length,
              point_count: element.data.reduce(
                (count, trace) => count + (trace.x?.length || 0), 0
              ),
              ticks: [...element.querySelectorAll('.xtick text')]
                .map(node => (node.textContent || '').trim()).filter(Boolean),
              legend: [...element.querySelectorAll('.legendtext')]
                .map(node => (node.textContent || '').trim()).filter(Boolean),
              minallowed: String(element._fullLayout.xaxis.minallowed),
              maxallowed: String(element._fullLayout.xaxis.maxallowed),
              fixedrange: element._fullLayout.xaxis.fixedrange,
            })"""
        )
        state["legend_is_chinese"] = bool(state["legend"]) and all(
            any("\u4e00" <= char <= "\u9fff" for char in label)
            for label in state["legend"]
        )
        states.append(state)
    if any(state["line_count"] != expected_lines for state in states):
        raise AssertionError(f"Expected {expected_lines} lines per chart: {states}")
    if states[0]["ticks"] != states[1]["ticks"]:
        raise AssertionError(f"Chart date axes differ: {states}")
    if states[0]["minallowed"] != states[1]["minallowed"]:
        raise AssertionError(f"Chart minimum boundaries differ: {states}")
    if states[0]["maxallowed"] != states[1]["maxallowed"]:
        raise AssertionError(f"Chart maximum boundaries differ: {states}")
    if any(state["fixedrange"] is not False for state in states):
        raise AssertionError(f"Chart interaction is unexpectedly fixed: {states}")
    if not all(state["legend_is_chinese"] for state in states):
        raise AssertionError(f"Non-Chinese legend found: {states}")
    return {"works_chart": states[0], "growth_chart": states[1]}


def _verify_tooltip(page: Page) -> str:
    chart = page.locator(CHART_SELECTOR).first
    point = chart.locator(".scatterlayer .point").first
    point.hover(force=True)
    tooltip = chart.locator(".hovertext").first
    tooltip.wait_for(state="visible", timeout=10_000)
    text = tooltip.text_content() or ""
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
