"""Escaped, local study overview; domain metrics stay separate."""

import html
import json
from pathlib import Path


def write_index(report: dict, path: Path):
    def esc(value):
        return html.escape(str(value))

    progress = report["progress"]
    parts = [
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>Evaluation study</title>',
        "<style>body{font:16px system-ui;max-width:1100px;margin:32px auto;padding:16px;"
        "background:#f6f8fa;color:#192b3c}table{border-collapse:collapse;width:100%}"
        "th,td{padding:10px;border-bottom:1px solid #ccc;text-align:left}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>",
        "<h1>" + esc(report["plan"]["id"]) + "</h1>",
        "<p>" + esc(report["plan"]["purpose"]) + "</p>",
        "<p>Completed batches: "
        + esc(progress["complete_batches"])
        + "/"
        + esc(progress["total_batches"])
        + " · Submitted judgments: "
        + esc(progress["submitted_cells"])
        + "/"
        + esc(progress["possible_cells"])
        + "</p>",
        "<p>References require independent human consensus or registered adjudication. "
        "No human labels means no measured human agreement or evaluator accuracy. "
        "Initial critiques are collected before rubric reveal in the ordinary UI; "
        "this is not a secure blinding or authenticated identity system.</p>",
        "<h2>Annotation progress</h2><table><tr><th>Batch</th><th>Reviewer</th><th>Domain</th>"
        "<th>Judgments</th><th>Initial critiques</th><th>Complete</th></tr>",
    ]
    for batch in progress["batches"]:
        parts.append(
            "<tr>"
            + "".join(
                "<td>" + esc(value) + "</td>"
                for value in (
                    batch["id"],
                    batch["reviewer"],
                    batch["domain"],
                    f"{batch['submitted_cells']}/{batch['possible_cells']}",
                    f"{batch['initial_critiques']}/{batch['possible_critiques']}",
                    batch["complete"],
                )
            )
            + "</tr>"
        )
    parts.append("</table><h2>Domain-specific comparisons</h2><ul>")
    for i, (domain, data) in enumerate(sorted(report["domains"].items()), 1):
        parts.append(
            f'<li><a href="domain-{i:04d}.html">'
            + esc(domain)
            + "</a>: "
            + esc(data["reference_count"])
            + " binary references; "
            + esc(len(data["unresolved"]))
            + " unresolved cells.</li>"
        )
    parts.append(
        "</ul><h2>Initial independent critiques</h2><pre>"
        + esc(json.dumps(report["initial_critiques"], indent=2))
        + "</pre>"
    )
    parts.append(
        "<h2>Frozen protocol</h2><pre>"
        + esc(json.dumps(report["plan"], indent=2))
        + "</pre><p>Study hash: "
        + esc(report["study_hash"])
        + "</p></html>"
    )
    parts.insert(
        -1,
        "<h2>Judge runtime and trace provenance</h2><pre>"
        + esc(json.dumps(report["judge_runs"], indent=2))
        + "</pre>",
    )
    with path.open("x", encoding="utf-8") as stream:
        stream.write("".join(parts))
