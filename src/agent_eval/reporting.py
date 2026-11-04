"""Static, escaped comparison report for reviewers and study leads."""

import html
import json
from pathlib import Path


def write_html(report: dict, path: Path):
    def esc(value):
        return html.escape(str(value))

    def pretty(value):
        return "<pre>" + esc(json.dumps(value, indent=2, ensure_ascii=False)) + "</pre>"

    sections = [
        (
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            "<title>Evaluator comparison</title><style>"
            "body{font:16px system-ui;max-width:1200px;margin:30px auto;padding:16px;"
            "color:#192b3c;background:#f6f8fa}section,details{background:white;padding:16px;"
            "margin:14px 0;border:1px solid #ddd;border-radius:8px}"
            "table{border-collapse:collapse;width:100%}th,td{padding:10px;text-align:left;"
            "border-bottom:1px solid #ccc}pre{white-space:pre-wrap;overflow-wrap:anywhere}"
            "</style><h1>Evaluator comparison</h1>"
        )
    ]
    sections.append(
        "<p>Split: "
        + esc(report["split"])
        + " · Binary reference cells: "
        + esc(report["reference_count"])
        + " · Unresolved: "
        + esc(len(report["unresolved"]))
        + "</p>"
    )
    sections.append(
        "<p>References require independent human consensus or explicit adjudication. "
        "A cell is a case–criterion judgment; cells are not independent scenario groups. "
        "Undefined metrics are shown as unavailable. Agreement does not establish rubric validity.</p>"
    )
    if report.get("synthetic_demo"):
        sections.append(
            "<p><strong>SYNTHETIC DEMO: labels are scripted examples, not human annotations.</strong></p>"
        )
    sections.append(
        "<table><tr><th>Judge</th><th>Failure precision</th><th>Detection rate</th>"
        "<th>Coverage</th><th>Missing / abstained</th></tr>"
    )
    for name, metrics in report["evaluators"].items():
        row = metrics["all"]

        def pct(key, row=row):
            return f"{row[key]:.1%}" if row[key] is not None else "unavailable"

        sections.append(
            "<tr><td>"
            + esc(name)
            + "</td><td>"
            + pct("failure_precision")
            + "</td><td>"
            + pct("failure_detection_rate")
            + "</td><td>"
            + pct("coverage")
            + "</td><td>"
            + esc(f"{row['missing']} / {row['abstained']}")
            + "</td></tr>"
        )
    sections.append("</table><h2>Per-criterion metrics</h2>" + pretty(report["evaluators"]))
    sections.append(
        "<h2>Review queue</h2><p>Unresolved references, incorrect judge verdicts, "
        "and missing/abstaining predictions are listed below.</p>"
    )
    for cell in report.get("review_queue", []):
        sections.append(
            "<details><summary>"
            + esc(cell["case_id"])
            + " · "
            + esc(cell["criterion_id"])
            + " · "
            + esc(", ".join(cell["reasons"]))
            + "</summary>"
            + pretty(cell)
            + "</details>"
        )
    sections.append(
        "<h2>Critiques outside the rubric</h2><p>Read these to find questions "
        "the current rubric may not ask. These notes require human analysis.</p>"
        + pretty(report.get("freeform_critiques", []))
    )
    sections.append("<h2>Annotation completion</h2>" + pretty(report.get("human_completion", [])))
    sections.append(
        "<h2>Human agreement</h2>"
        + pretty({k: report[k] for k in ("human_pair_agreement", "human_pair_comparisons")})
    )
    sections.append("<h2>Provenance</h2>" + pretty(report.get("provenance", {})))
    sections.append("</html>")
    with path.open("x", encoding="utf-8") as handle:
        handle.write("".join(sections))
