from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = REPO_ROOT / ".agent-permit"
OUTPUT_PATH = REPO_ROOT / "dashboard" / "src" / "data" / "generated" / "dashboardSnapshot.json"
CONTRACT_VERSION = "permitgraph.dashboard.snapshot.v1"
PROOF_PACKS_DIR = ARTIFACT_ROOT / "proof-packs"
SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "password",
    "private_key",
    "secret",
    "token",
)
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)((?:api[_-]?key|authorization|password|private[_-]?key|secret|token)\b[^:=\n]{0,40}[:=]\s*)([^\s,]+)"
)


def main() -> None:
    args = parse_args()
    validation_path = required_latest_file(
        ARTIFACT_ROOT / "live-repo-validations",
        "live-repo-validation-results.json",
        "Run `uv run --extra deep-agent agent-permit live-validate-real <manifest>` or restore a validation results artifact.",
    )
    demo_path = latest_file(
        ARTIFACT_ROOT / "open-source-demos",
        "open-source-demo-results.json",
    )
    eval_trends_path = latest_file(
        ARTIFACT_ROOT / "eval-trends",
        "eval-trends.json",
    )
    latest_scan_metrics_path = latest_file(ARTIFACT_ROOT / "runs", "run-metrics.json")

    validation = read_json(validation_path)
    demo = read_json(demo_path) if demo_path else {}
    eval_trends = read_json(eval_trends_path) if eval_trends_path else {}
    latest_scan_metrics = read_json(latest_scan_metrics_path) if latest_scan_metrics_path else {}
    repo_prep = {entry["repo_id"]: entry for entry in demo.get("repo_prep", [])}
    rows = build_rows(validation, repo_prep, validation_path)
    summary = build_summary(validation, rows, eval_trends, latest_scan_metrics)
    artifact_previews = build_artifact_previews(validation_path, rows)
    selected_run_id = validation.get("validation_run_id", "unknown-run")

    snapshot = {
        "contractVersion": CONTRACT_VERSION,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "selectedRunId": selected_run_id,
        "source": {
            "validationRunId": validation.get("validation_run_id"),
            "validationPath": relative_path(validation_path),
            "demoRunId": demo.get("demo_run_id"),
            "demoPath": relative_path(demo_path) if demo_path else None,
            "evalRunId": eval_trends.get("trend_run_id"),
            "evalPath": relative_path(eval_trends_path) if eval_trends_path else None,
            "latestScanRunId": latest_scan_metrics.get("run_id"),
            "latestScanPath": relative_path(latest_scan_metrics_path)
            if latest_scan_metrics_path
            else None,
        },
        "runMeta": {
            "title": "Agent Risk Review",
            "repo": "open-source validation suite",
            "branch": "recent commits",
            "runId": validation.get("validation_run_id", "unknown-run"),
            "completedAt": validation.get("completed_at"),
        },
        "repos": build_repos(rows),
        "runs": build_runs(validation, rows, summary, validation_path),
        "summary": summary,
        "savedViews": [
            {"id": "all", "label": "All Repos", "count": len(rows)},
            {"id": "blocked", "label": "Blocked", "count": summary["blockedRepos"]},
            {
                "id": "needs-review",
                "label": "Needs Review",
                "count": summary["needsReviewRepos"],
            },
            {"id": "approved", "label": "Approved", "count": summary["approvedRepos"]},
        ],
        "findings": rows,
        "artifactPreviews": artifact_previews,
        "runDetails": build_run_details(selected_run_id, rows, artifact_previews),
        "decisionLog": build_decision_log(summary),
        "traceSteps": build_trace_steps(summary),
        "policyControls": build_policy_controls(summary),
        "proofPack": build_proof_pack(validation_path, artifact_previews, rows),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {relative_path(OUTPUT_PATH)}")

    if args.proof_pack:
        proof_pack_result = write_proof_pack(
            snapshot,
            validation_path=validation_path,
            latest_scan_metrics_path=latest_scan_metrics_path,
            output_dir=args.proof_pack_dir,
        )
        print(f"Proof pack: {relative_path(proof_pack_result['directory'])}")
        print(f"Proof pack zip: {relative_path(proof_pack_result['zipPath'])}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export PermitGraph dashboard data from local .agent-permit artifacts."
    )
    parser.add_argument(
        "--proof-pack",
        action="store_true",
        help="also write a sanitized proof pack directory and zip for customer demos",
    )
    parser.add_argument(
        "--proof-pack-dir",
        type=Path,
        default=None,
        help="proof pack output directory; defaults to .agent-permit/proof-packs/<validation_run_id>",
    )
    return parser.parse_args()


def latest_file(root: Path, filename: str) -> Path | None:
    if not root.exists():
        return None
    matches = sorted(root.glob(f"*/{filename}"), key=lambda path: path.stat().st_mtime)
    return matches[-1] if matches else None


def required_latest_file(root: Path, filename: str, guidance: str) -> Path:
    path = latest_file(root, filename)
    if path is None:
        raise SystemExit(
            f"error: no {filename} found under {relative_path(root)}. {guidance}"
        )
    return path


def read_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_rows(
    validation: dict[str, Any],
    repo_prep: dict[str, dict[str, Any]],
    validation_path: Path | None,
) -> list[dict[str, Any]]:
    rows = []
    for index, result in enumerate(validation.get("results", []), start=1):
        repo_id = result.get("repo_id", "unknown-repo")
        prep = repo_prep.get(repo_id, {})
        status = normalize_status(result.get("actual_permit_status"))
        rules = result.get("actual_rule_ids", [])
        findings_count = result.get("findings_count", 0)
        graph_paths = result.get("graph_paths_count", 0)
        controls = result.get("controls_count", 0)
        citation_passed = bool(result.get("citation_check_passed"))
        expectation_passed = bool(result.get("expectation_check_passed"))
        source = result.get("source", prep.get("source", repo_id))
        primary_rule = rules[0] if rules else "clean-run"
        severity = severity_for(status, rules, findings_count)
        capability = capability_for(rules, status)
        artifacts = artifacts_for(result, validation_path)
        artifact_status_value = artifact_status_for_result(result, artifacts)

        rows.append(
            {
                "id": f"APO-LIVE-{index:04d}",
                "repo": repo_id,
                "source": source,
                "branch": "recent commit",
                "runId": result.get("run_id", validation.get("validation_run_id")),
                "status": status,
                "severity": severity,
                "rule": primary_rule,
                "title": title_for(repo_id, status, findings_count, rules),
                "path": relative_path(validation_path) if validation_path else "live-validation-results.json",
                "line": 0,
                "capability": capability,
                "confidence": confidence_for(citation_passed, expectation_passed),
                "owner": owner_for(status, capability),
                "age": age_label(prep.get("commit_date")),
                "summary": summary_for(result, repo_id, status),
                "evidence": evidence_for(rules, findings_count, graph_paths, controls),
                "scanner": "live-validation + bounded deep agent",
                "remediation": remediation_for(status, rules),
                "artifacts": artifacts,
                "artifactStatus": artifact_status_value,
                "missingArtifacts": missing_per_repo_artifacts(artifact_status_value),
                "traceIds": trace_ids_for(result),
                "commit": {
                    "hash": prep.get("commit"),
                    "date": prep.get("commit_date"),
                    "message": prep.get("commit_message"),
                },
                "metrics": {
                    "cacheHitRatio": result.get("cache_hit_ratio"),
                    "cachedTokens": result.get("cached_tokens", 0),
                    "citationCheckPassed": citation_passed,
                    "controls": controls,
                    "durationSeconds": result.get("duration_seconds"),
                    "expectationCheckPassed": expectation_passed,
                    "findings": findings_count,
                    "graphPaths": graph_paths,
                    "modelCalls": result.get("model_calls", 0),
                    "totalTokens": result.get("total_tokens", 0),
                },
            }
        )
    return rows


def build_summary(
    validation: dict[str, Any],
    rows: list[dict[str, Any]],
    eval_trends: dict[str, Any],
    latest_scan_metrics: dict[str, Any],
) -> dict[str, Any]:
    statuses = Counter(row["status"] for row in rows)
    validation_summary = validation.get("summary", {})
    citation_passes = sum(1 for row in rows if row["metrics"]["citationCheckPassed"])
    return {
        "repos": len(rows),
        "passedRepos": validation_summary.get("passed", 0),
        "blockedRepos": statuses.get("blocked", 0),
        "needsReviewRepos": statuses.get("needs-review", 0),
        "approvedRepos": statuses.get("approved", 0),
        "findings": sum(row["metrics"]["findings"] for row in rows),
        "graphPaths": sum(row["metrics"]["graphPaths"] for row in rows),
        "controls": sum(row["metrics"]["controls"] for row in rows),
        "citationCoverage": citation_passes / len(rows) if rows else 0,
        "cacheHitRatio": validation_summary.get("cache_hit_ratio"),
        "cachedTokens": validation_summary.get("cached_tokens", 0),
        "inputTokens": validation_summary.get("input_tokens", 0),
        "totalTokens": validation_summary.get("total_tokens", 0),
        "modelCalls": sum(row["metrics"]["modelCalls"] for row in rows),
        "evalPassRate": eval_trends.get("summary", {}).get("latest_pass_rate"),
        "latestScanStatus": latest_scan_metrics.get("permit_status"),
        "latestScanFindings": latest_scan_metrics.get("findings"),
        "latestScanFilesIndexed": latest_scan_metrics.get("files_indexed"),
    }


def build_repos(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    repos = []
    for row in rows:
        repos.append(
            {
                "id": row["repo"],
                "label": row["repo"],
                "source": row["source"],
                "status": row["status"],
                "latestRunId": row["runId"],
                "runIds": [row["runId"]],
                "commit": row["commit"],
                "counts": {
                    "controls": row["metrics"]["controls"],
                    "findings": row["metrics"]["findings"],
                    "graphPaths": row["metrics"]["graphPaths"],
                },
            }
        )
    return repos


def build_runs(
    validation: dict[str, Any],
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    validation_path: Path | None,
) -> list[dict[str, Any]]:
    aggregate_run_id = validation.get("validation_run_id", "unknown-run")
    runs = [
        {
            "id": aggregate_run_id,
            "label": "Open-source validation suite",
            "repoId": "all",
            "scope": "validation",
            "status": aggregate_status(summary),
            "completedAt": validation.get("completed_at"),
            "artifacts": aggregate_artifacts(validation_path),
            "metrics": {
                "cacheHitRatio": summary["cacheHitRatio"],
                "cachedTokens": summary["cachedTokens"],
                "citationCoverage": summary["citationCoverage"],
                "controls": summary["controls"],
                "findings": summary["findings"],
                "graphPaths": summary["graphPaths"],
                "modelCalls": summary["modelCalls"],
                "totalTokens": summary["totalTokens"],
            },
        }
    ]
    for row in rows:
        runs.append(
            {
                "id": row["runId"],
                "label": row["repo"],
                "repoId": row["repo"],
                "scope": "repo",
                "status": row["status"],
                "completedAt": row["commit"]["date"],
                "artifacts": row["artifacts"],
                "artifactStatus": row["artifactStatus"],
                "metrics": row["metrics"],
            }
        )
    return runs


def build_run_details(
    selected_run_id: str,
    rows: list[dict[str, Any]],
    artifact_previews: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    details = {
        selected_run_id: {
            "runId": selected_run_id,
            "repoId": "all",
            "rowIds": [row["id"] for row in rows],
            "artifactPreviewPaths": sorted(artifact_previews.keys()),
            "artifactAvailability": "aggregate",
            "missingArtifacts": ["per-repo raw-findings.json", "per-repo graph-paths.json"],
        }
    }
    for row in rows:
        details[row["runId"]] = {
            "runId": row["runId"],
            "repoId": row["repo"],
            "rowIds": [row["id"]],
            "artifactPreviewPaths": [
                artifact
                for artifact in row["artifacts"]
                if artifact in artifact_previews
            ],
            "artifactAvailability": row["artifactStatus"],
            "missingArtifacts": row["missingArtifacts"],
        }
    return details


def build_decision_log(summary: dict[str, Any]) -> list[dict[str, str]]:
    status = aggregate_status(summary)
    return [
        {
            "id": "decision-scanner",
            "label": "Scanner evidence loaded",
            "state": "passed",
            "detail": f"{summary['findings']} findings across {summary['repos']} repositories.",
        },
        {
            "id": "decision-graph",
            "label": "Capability graph traced",
            "state": "blocked" if summary["blockedRepos"] else "passed",
            "detail": f"{summary['graphPaths']} paths and {summary['controls']} controls evaluated.",
        },
        {
            "id": "decision-permit",
            "label": "Permit status assigned",
            "state": status,
            "detail": (
                f"{summary['blockedRepos']} blocked, {summary['needsReviewRepos']} needs review, "
                f"{summary['approvedRepos']} approved."
            ),
        },
        {
            "id": "decision-deep-agent",
            "label": "Deep Agent citations checked",
            "state": "passed" if summary["citationCoverage"] >= 1 else "review",
            "detail": f"Citation coverage is {summary['citationCoverage']:.0%}.",
        },
        {
            "id": "decision-cost",
            "label": "Cost controls measured",
            "state": "passed" if (summary.get("cacheHitRatio") or 0) > 0.5 else "review",
            "detail": f"{summary['cachedTokens']} cached tokens from {summary['totalTokens']} total tokens.",
        },
    ]


def build_proof_pack(
    validation_path: Path | None,
    artifact_previews: dict[str, dict[str, Any]],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    aggregate_paths = sorted(artifact_previews.keys())
    missing_artifacts = sorted(
        {
            artifact
            for row in rows
            for artifact in row.get("missingArtifacts", [])
        }
    )
    status = "ready" if aggregate_paths and not missing_artifacts else "partial"
    if not aggregate_paths:
        status = "missing"
    reason = (
        "All referenced run artifacts are available in the local snapshot."
        if status == "ready"
        else "Aggregate validation artifacts are repo-local; some per-repo evidence artifacts are missing."
    )
    return {
        "status": status,
        "reason": reason,
        "sourceRunPath": relative_path(validation_path) if validation_path else None,
        "includedArtifacts": aggregate_paths,
        "missingArtifacts": missing_artifacts,
    }


def aggregate_status(summary: dict[str, Any]) -> str:
    if summary["blockedRepos"]:
        return "blocked"
    if summary["needsReviewRepos"]:
        return "needs-review"
    return "approved"


def aggregate_artifacts(validation_path: Path | None) -> list[str]:
    if validation_path is None:
        return []
    artifacts = [relative_path(validation_path)]
    report_path = validation_path.with_name("live-repo-validation-report.md")
    if report_path.exists():
        artifacts.append(relative_path(report_path))
    return artifacts


def artifact_status_for_result(
    result: dict[str, Any],
    artifacts: list[str],
) -> str:
    artifact_dir = str(result.get("artifact_dir") or "")
    if artifact_dir.startswith("/private/tmp/"):
        return "partial"
    if artifact_dir and Path(artifact_dir).is_dir():
        return "available"
    if artifact_dir:
        return "missing"
    if any(_artifact_path_from_ref(artifact) for artifact in artifacts):
        return "available"
    return "missing"


def missing_per_repo_artifacts(artifact_status_value: str) -> list[str]:
    if artifact_status_value == "available":
        return []
    return [
        "raw-findings.json",
        "graph-paths.json",
        "permit.yaml",
        "agent-investigation.md",
    ]


def build_trace_steps(summary: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": "trace-artifacts",
            "label": "Load validation artifacts",
            "state": "passed",
            "duration": "static",
            "tool": "artifact.read",
            "output": f"{summary['repos']} repo validation rows loaded from durable .agent-permit output.",
        },
        {
            "id": "trace-citations",
            "label": "Check citation coverage",
            "state": "passed" if summary["citationCoverage"] >= 1 else "review",
            "duration": "aggregate",
            "tool": "citation_critic.verify",
            "output": f"{summary['citationCoverage']:.0%} of live repo validations passed citation checks.",
        },
        {
            "id": "trace-paths",
            "label": "Trace capability paths",
            "state": "blocked" if summary["blockedRepos"] else "passed",
            "duration": "aggregate",
            "tool": "graph.paths",
            "output": f"{summary['graphPaths']} graph paths and {summary['controls']} controls found across live repos.",
        },
        {
            "id": "trace-cost",
            "label": "Measure model cost controls",
            "state": "passed" if (summary.get("cacheHitRatio") or 0) > 0.5 else "review",
            "duration": "aggregate",
            "tool": "openrouter.usage",
            "output": f"{summary['cachedTokens']} cached tokens across {summary['modelCalls']} model calls.",
        },
    ]


def build_policy_controls(summary: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "id": "CTRL-CITATION",
            "label": "Deep Agent claims cite scanner evidence",
            "state": "passed" if summary["citationCoverage"] >= 1 else "review",
            "note": f"Citation coverage is {summary['citationCoverage']:.0%} across the validation set.",
        },
        {
            "id": "CTRL-CI",
            "label": "Privileged CI paths block permit approval",
            "state": "blocked" if summary["blockedRepos"] else "passed",
            "note": f"{summary['blockedRepos']} repositories have blocked permit decisions.",
        },
        {
            "id": "CTRL-CACHE",
            "label": "Prompt caching lowers repeated-run cost",
            "state": "passed" if (summary.get("cacheHitRatio") or 0) > 0.5 else "review",
            "note": f"Cache hit ratio is {percent(summary.get('cacheHitRatio'))}.",
        },
        {
            "id": "CTRL-EVAL",
            "label": "Fixture eval suite protects scanner regressions",
            "state": "passed" if summary.get("evalPassRate") == 1 else "review",
            "note": f"Latest eval pass rate is {percent(summary.get('evalPassRate'))}.",
        },
    ]


def build_artifact_previews(
    validation_path: Path | None,
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    previews: dict[str, dict[str, Any]] = {}
    candidate_paths = []
    if validation_path is not None:
        candidate_paths.extend(
            [validation_path, validation_path.with_name("live-repo-validation-report.md")]
        )
    for row in rows:
        for artifact in row.get("artifacts", []):
            path = _artifact_path_from_ref(artifact)
            if path is not None:
                candidate_paths.append(path)
    for path in candidate_paths:
        if not path.exists():
            continue
        artifact_path = relative_path(path)
        suffix = path.suffix.lower()
        content = path.read_text(encoding="utf-8")
        if suffix == ".json":
            content = json.dumps(json.loads(content), indent=2, sort_keys=True)
            kind = "json"
        elif suffix == ".md":
            kind = "markdown"
        else:
            kind = "text"
        previews[artifact_path] = {
            "kind": kind,
            "label": path.name,
            "path": artifact_path,
            "sizeBytes": path.stat().st_size,
            "content": content[:12000],
            "truncated": len(content) > 12000,
        }
    return previews


def write_proof_pack(
    snapshot: dict[str, Any],
    *,
    validation_path: Path,
    latest_scan_metrics_path: Path | None,
    output_dir: Path | None,
) -> dict[str, Path]:
    run_id = snapshot.get("selectedRunId") or "unknown-run"
    proof_pack_dir = output_dir or (PROOF_PACKS_DIR / safe_segment(str(run_id)))
    proof_pack_dir.mkdir(parents=True, exist_ok=True)

    included: list[dict[str, Any]] = []
    missing: list[str] = []
    seen_sources: set[Path] = set()

    def add_file(source: Path | None, destination: Path, *, required: bool = True) -> None:
        if source is None or not source.is_file():
            if required:
                missing.append(str(destination))
            return
        resolved = source.resolve()
        if resolved in seen_sources:
            return
        seen_sources.add(resolved)
        target = proof_pack_dir / destination
        write_sanitized_file(source, target)
        included.append(
            {
                "path": str(destination),
                "source": relative_path(source),
                "sha256": sha256_file(target),
                "sizeBytes": target.stat().st_size,
            }
        )

    add_file(validation_path, Path("validation/live-repo-validation-results.json"))
    add_file(
        validation_path.with_name("live-repo-validation-report.md"),
        Path("validation/live-repo-validation-report.md"),
    )
    add_file(OUTPUT_PATH, Path("dashboard/dashboardSnapshot.json"))

    scan_dir = latest_scan_metrics_path.parent if latest_scan_metrics_path else None
    scan_required = (
        "permit.yaml",
        "raw-findings.json",
        "graph-paths.json",
        "run-metrics.json",
    )
    scan_optional = (
        "summary.md",
        "risk-report.md",
        "agent-investigation.md",
        "controls.json",
        "scan-run.json",
        "results.sarif",
    )
    for name in scan_required:
        add_file(scan_dir / name if scan_dir else None, Path(f"scan/{name}"))
    for name in scan_optional:
        add_file(scan_dir / name if scan_dir else None, Path(f"scan/{name}"), required=False)

    for row in snapshot.get("findings", []):
        repo_segment = safe_segment(row.get("repo", "repo"))
        for artifact in row.get("artifacts", []):
            source = _artifact_path_from_ref(artifact)
            if source is not None and source.is_file():
                add_file(source, Path("repos") / repo_segment / source.name, required=False)
        for artifact in row.get("missingArtifacts", []):
            missing.append(f"repos/{repo_segment}/{artifact}")

    missing = sorted(set(missing))
    report_path = proof_pack_dir / "proof-pack-report.md"
    manifest_path = proof_pack_dir / "proof-pack-manifest.json"
    report_path.write_text(
        build_proof_pack_report(snapshot, included, missing),
        encoding="utf-8",
    )
    included.append(
        {
            "path": report_path.name,
            "source": "generated proof pack report",
            "sha256": sha256_file(report_path),
            "sizeBytes": report_path.stat().st_size,
        }
    )
    manifest = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "runId": run_id,
        "status": "ready" if not missing else "partial",
        "sanitization": {
            "mode": "allowlist-plus-redaction",
            "redactedKeyParts": list(SENSITIVE_KEY_PARTS),
        },
        "source": snapshot.get("source", {}),
        "included": included,
        "missing": missing,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    zip_path = proof_pack_dir.with_suffix(".zip")
    write_zip(proof_pack_dir, zip_path)
    return {"directory": proof_pack_dir, "zipPath": zip_path}


def build_proof_pack_report(
    snapshot: dict[str, Any],
    included: list[dict[str, Any]],
    missing: list[str],
) -> str:
    summary = snapshot.get("summary", {})
    proof_pack = snapshot.get("proofPack", {})
    lines = [
        "# PermitGraph Proof Pack",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Run: `{snapshot.get('selectedRunId', 'unknown-run')}`",
        f"Status: `{('ready' if not missing else 'partial')}`",
        "",
        "## What This Proves",
        "",
        "- Scanner and Deep Agent evidence were generated from local `.agent-permit` artifacts.",
        f"- {summary.get('repos', 0)} repositories, {summary.get('findings', 0)} findings, and {summary.get('graphPaths', 0)} graph paths were reviewed.",
        f"- Citation coverage: {percent(summary.get('citationCoverage'))}.",
        f"- Cached tokens: {summary.get('cachedTokens', 0)}.",
        "",
        "## Included Evidence",
        "",
        "- `proof-pack-manifest.json`",
    ]
    lines.extend(f"- `{entry['path']}`" for entry in sorted(included, key=lambda item: item["path"]))
    if missing:
        lines.extend(["", "## Partial Evidence", ""])
        lines.append(
            "The pack is still usable for demo and customer discovery, but these per-repo proof files were not available locally:"
        )
        lines.extend(f"- `{path}`" for path in missing)
    lines.extend(
        [
            "",
            "## Sanitization",
            "",
            "- Only allowlisted artifact names are copied.",
            "- JSON values under sensitive key names are redacted.",
            "- Text assignments that look like tokens, secrets, passwords, API keys, authorization values, or private keys are redacted.",
            "- Source URLs and secret variable names may remain when they are evidence, but raw secret values are not intentionally exported.",
            "",
            "## Source Snapshot",
            "",
            proof_pack.get("reason", "Dashboard snapshot proof pack generated from local artifacts."),
            "",
        ]
    )
    return "\n".join(lines)


def write_sanitized_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    text = source.read_text(encoding="utf-8", errors="replace")
    if source.suffix.lower() in {".json", ".sarif"}:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            target.write_text(redact_text(text), encoding="utf-8")
            return
        target.write_text(
            json.dumps(redact_json(payload), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return
    target.write_text(redact_text(text), encoding="utf-8")


def redact_json(value: Any, key: str | None = None) -> Any:
    if key is not None and is_sensitive_key(key):
        return "[redacted]"
    if isinstance(value, dict):
        return {item_key: redact_json(item_value, item_key) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact_json(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_text(text: str) -> str:
    return SENSITIVE_ASSIGNMENT_RE.sub(r"\1[redacted]", text)


def is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_zip(source_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir))


def safe_segment(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return normalized.strip("-") or "unknown"


def normalize_status(status: str | None) -> str:
    if status == "needs_review":
        return "needs-review"
    if status in {"approved", "blocked"}:
        return status
    return "needs-review"


def severity_for(status: str, rules: list[str], findings_count: int) -> str:
    if status == "blocked":
        return "critical" if "ci-pr-target-write-token" in rules else "high"
    if findings_count == 0:
        return "low"
    if "ci-write-permission" in rules or "ci-secret-reference" in rules:
        return "high"
    return "medium"


def capability_for(rules: list[str], status: str) -> str:
    joined = " ".join(rules)
    if "ci-" in joined:
        return "ci trust boundary"
    if "mcp-" in joined:
        return "mcp tool boundary"
    if "prompt-" in joined:
        return "instruction boundary"
    if status == "approved":
        return "clean permit"
    return "policy review"


def title_for(repo_id: str, status: str, findings_count: int, rules: list[str]) -> str:
    if findings_count == 0:
        return f"{repo_id} passed without deterministic findings"
    primary_rules = ", ".join(rules[:2])
    return f"{repo_id} {status.replace('-', ' ')}: {primary_rules}"


def confidence_for(citation_passed: bool, expectation_passed: bool) -> int:
    if citation_passed and expectation_passed:
        return 96
    if citation_passed or expectation_passed:
        return 84
    return 70


def owner_for(status: str, capability: str) -> str:
    if status == "blocked":
        return "AppSec"
    if capability == "ci trust boundary":
        return "DevEx"
    if status == "approved":
        return "Platform"
    return "AI Platform"


def age_label(commit_date: str | None) -> str:
    if not commit_date:
        return "unknown"
    try:
        parsed = datetime.fromisoformat(commit_date.replace("Z", "+00:00"))
    except ValueError:
        return commit_date[:10]
    return f"{parsed:%b} {parsed.day}"


def summary_for(result: dict[str, Any], repo_id: str, status: str) -> str:
    return (
        f"{repo_id} finished with permit status {status.replace('-', ' ')}. "
        f"{result.get('findings_count', 0)} findings, {result.get('graph_paths_count', 0)} graph paths, "
        f"and {result.get('controls_count', 0)} controls were checked."
    )


def evidence_for(
    rules: list[str],
    findings_count: int,
    graph_paths: int,
    controls: int,
) -> str:
    if rules:
        return f"Rules present: {', '.join(rules)}. Findings={findings_count}, paths={graph_paths}, controls={controls}."
    return f"No expected risk rules present. Findings={findings_count}, paths={graph_paths}, controls={controls}."


def remediation_for(status: str, rules: list[str]) -> str:
    joined = " ".join(rules)
    if "ci-pr-target-write-token" in joined:
        return "Split trusted CI from untrusted pull request handling and downgrade token permissions before agent execution."
    if "ci-write-permission" in joined or "ci-secret-reference" in joined:
        return "Review workflow secrets and use least-privilege permissions before allowing agent automation."
    if status == "approved":
        return "Keep scanner and Deep Agent citation checks in CI to preserve this approval state."
    return "Review the cited scanner rules and require owner approval before granting the permit."


def artifacts_for(result: dict[str, Any], validation_path: Path | None) -> list[str]:
    artifacts = [
        relative_path(validation_path) if validation_path else "live-repo-validation-results.json",
    ]
    if validation_path is not None:
        report_path = validation_path.with_name("live-repo-validation-report.md")
        if report_path.exists():
            artifacts.append(relative_path(report_path))
    artifact_dir = _optional_artifact_dir(result.get("artifact_dir"))
    if artifact_dir is not None:
        for name in (
            "raw-findings.json",
            "graph-paths.json",
            "permit.yaml",
            "agent-investigation.md",
            "run-metrics.json",
            "live-validation.json",
            "openrouter-usage.json",
            "results.sarif",
        ):
            path = artifact_dir / name
            if path.is_file():
                artifacts.append(relative_path(path))
    for key in ("report_path", "usage_path", "validation_path"):
        path = _optional_artifact_file(result.get(key))
        if path is not None:
            artifact_ref = relative_path(path)
            if artifact_ref not in artifacts:
                artifacts.append(artifact_ref)
    if result.get("source"):
        artifacts.append(result["source"])
    return artifacts


def trace_ids_for(result: dict[str, Any]) -> list[str]:
    trace_ids = ["trace-artifacts", "trace-citations"]
    if result.get("graph_paths_count", 0):
        trace_ids.append("trace-paths")
    if result.get("model_calls", 0):
        trace_ids.append("trace-cost")
    return trace_ids


def percent(value: float | None) -> str:
    if value is None:
        return "not available"
    return f"{value:.0%}"


def relative_path(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _artifact_path_from_ref(reference: str) -> Path | None:
    if reference.startswith(("http://", "https://")):
        return None
    path = Path(reference)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path if path.is_file() else None


def _optional_artifact_dir(value: Any) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    return path if path.is_dir() else None


def _optional_artifact_file(value: Any) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    return path if path.is_file() else None


if __name__ == "__main__":
    main()
