from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "benchmark"
FIELDS = ["timestamp_utc", "sample", "phase", "service", "container", "cpu_pct",
          "mem_used_mib", "mem_limit_mib", "mem_pct"]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def docker_cmd(*args: str, timeout: int = 20) -> str:
    proc = subprocess.run(["docker", *args], text=True, capture_output=True,
                          check=False, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout


def parse_pct(text: str) -> float:
    return float(str(text).replace("%", "").strip())


def to_mib(text: str) -> float:
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([KMGTPE]?i?B|B)\s*", text, re.I)
    if not match:
        raise ValueError(f"Unrecognized Docker memory unit: {text!r}")
    n, unit = float(match.group(1)), match.group(2).upper()
    # The CLI formats quantities in either IEC (KiB/MiB/GiB) or SI (kB/MB/GB).
    iec = "I" in unit
    prefix = unit[0] if len(unit) > 1 and unit[0] in "KMGTPE" else ""
    power = {"": 0, "K": 1, "M": 2, "G": 3, "T": 4, "P": 5, "E": 6}[prefix]
    value_bytes = n * ((1024 if iec else 1000) ** power)
    return value_bytes / (1024 ** 2)


def parse_memory(text: str) -> tuple[float, float]:
    parts = text.split("/")
    if len(parts) != 2:
        raise ValueError(f"Unrecognized Docker memory usage: {text!r}")
    return to_mib(parts[0]), to_mib(parts[1])


def get_service_containers() -> dict[str, str]:
    ids = [s.strip() for s in docker_cmd("compose", "ps", "-q").splitlines() if s.strip()]
    if not ids:
        raise RuntimeError("No running Compose containers. Run: sudo docker compose up -d")
    containers = {}
    for cid in ids:
        labels = json.loads(docker_cmd("inspect", "--format", "{{json .Config.Labels}}", cid))
        service = labels.get("com.docker.compose.service")
        if service in ("neo4j", "qdrant"):
            containers[service] = cid
    if not {"neo4j", "qdrant"}.issubset(containers):
        raise RuntimeError(f"Expected neo4j and qdrant in current Compose project, found: {sorted(containers)}")
    return {svc: containers[svc] for svc in ("neo4j", "qdrant")}


def one_sample(containers: dict[str, str], sample_no: int, phase: str) -> list[dict]:
    raw = docker_cmd("stats", "--no-stream", "--format", "{{json .}}", *containers.values(), timeout=25)
    labels_by_id = {value: key for key, value in containers.items()}
    id_starts = [(cid[:12], name) for cid, name in labels_by_id.items()]
    readings = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        rowid = str(item.get("ID", ""))
        name = str(item.get("Name") or item.get("Container") or "")
        service = next((svc for prefix, svc in id_starts if rowid.startswith(prefix) or name.endswith("-" + svc + "-1")), None)
        if service is None:
            service = next((svc for svc in containers if svc in name), None)
        if service is None:
            raise RuntimeError(f"Cannot identify service for stats record: {item}")
        memory, limit = parse_memory(item["MemUsage"])
        readings.append({
            "timestamp_utc": now_utc(), "sample": sample_no, "phase": phase,
            "service": service, "container": name, "cpu_pct": round(parse_pct(item["CPUPerc"]), 4),
            "mem_used_mib": round(memory, 3), "mem_limit_mib": round(limit, 3),
            "mem_pct": round(parse_pct(item["MemPerc"]), 4),
        })
    if {r["service"] for r in readings} != {"neo4j", "qdrant"}:
        raise RuntimeError(f"Incomplete docker stats sample: {readings}")
    return readings


def create_summary(data: list[dict], csv_path: Path, baseline_samples: int, start: str) -> dict:
    summary: dict = {
        "started_utc": start, "ended_utc": now_utc(), "csv": csv_path.name,
        "collection_method": "docker stats --no-stream",
        "baseline_samples_requested": baseline_samples,
        "samples_by_phase": {phase: len({r["sample"] for r in data if r["phase"] == phase})
                             for phase in ("baseline", "load")},
        "services": {},
        "limitations": [
            "The load phase includes any waiting between the baseline and the Windows benchmark command, and before Ctrl+C.",
            "CPU% is as reported by docker stats (can exceed 100% on multicore systems).",
            "Container memory excludes the Windows Python client and may include Docker memory accounting specifics.",
            "CPU/RAM was sampled externally; peaks between samples may be missed.",
        ],
    }
    for service in ("neo4j", "qdrant"):
        info = {}
        for phase in ("baseline", "load"):
            subset = [r for r in data if r["service"] == service and r["phase"] == phase]
            if subset:
                info[phase] = {
                    "n": len(subset),
                    "mean_cpu_pct": round(sum(r["cpu_pct"] for r in subset) / len(subset), 3),
                    "peak_cpu_pct": round(max(r["cpu_pct"] for r in subset), 3),
                    "mean_mem_mib": round(sum(r["mem_used_mib"] for r in subset) / len(subset), 3),
                    "peak_mem_mib": round(max(r["mem_used_mib"] for r in subset), 3),
                }
        if "baseline" in info and "load" in info:
            info["delta_mean_cpu_pct"] = round(info["load"]["mean_cpu_pct"] - info["baseline"]["mean_cpu_pct"], 3)
            info["delta_mean_mem_mib"] = round(info["load"]["mean_mem_mib"] - info["baseline"]["mean_mem_mib"], 3)
        summary["services"][service] = info
    return summary


def self_test() -> None:
    assert to_mib("1024KiB") == 1
    assert to_mib("1GiB") == 1024
    assert to_mib("1MB") == 1000 ** 2 / 1024 ** 2
    assert parse_memory("257.5MiB / 7.773GiB")[0] == 257.5
    assert parse_pct("0.57%") == 0.57
    fake = [
        {"sample": 1, "phase": "baseline", "service": "neo4j", "cpu_pct": 1., "mem_used_mib": 100.},
        {"sample": 2, "phase": "load", "service": "neo4j", "cpu_pct": 10., "mem_used_mib": 105.},
    ]
    summary = create_summary(fake, Path("example.csv"), 1, "test")
    assert summary["services"]["neo4j"]["delta_mean_mem_mib"] == 5.
    print("SELF-TEST OK: unit conversion, percent parsing, memory parsing, summary calculations")


def main() -> int:
    p = argparse.ArgumentParser(description="Monitor container CPU/RAM while Windows runs the benchmark")
    p.add_argument("--baseline-samples", type=int, default=4,
                   help="How many Docker stats samples to collect before announcing start (default: 4)")
    p.add_argument("--interval", type=float, default=0.5,
                   help="Additional sleep between stats calls; each call can also take ~1-2s")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.baseline_samples < 2 or args.interval < 0.1:
        p.error("--baseline-samples >= 2 and --interval >= 0.1 required")
    containers = get_service_containers()
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_path = OUTPUT_DIR / f"docker_resources_{stamp}.csv"
    json_path = OUTPUT_DIR / f"docker_resources_{stamp}_summary.json"
    print("Monitoring:", ", ".join(containers), flush=True)
    print("CSV:", csv_path, flush=True)
    print("BASELINE: wait for baseline to complete; do not start benchmark yet.", flush=True)
    records: list[dict] = []
    started = now_utc()
    errors = 0
    sample_no = 0
    with csv_path.open("w", newline="", encoding="utf-8") as fout:
        writer = csv.DictWriter(fout, fieldnames=FIELDS)
        writer.writeheader()
        try:
            while True:
                phase = "baseline" if sample_no < args.baseline_samples else "load"
                sample_no += 1
                try:
                    sample = one_sample(containers, sample_no, phase)
                except (RuntimeError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as e:
                    errors += 1
                    print(f"Warning: sample {sample_no} failed: {e}", file=sys.stderr, flush=True)
                    if errors >= 3:
                        print("Stopping after 3 sample errors.", file=sys.stderr, flush=True)
                        break
                else:
                    errors = 0
                    records.extend(sample)
                    writer.writerows(sample)
                    fout.flush()
                    if phase == "baseline":
                        print(f"Baseline sample {sample_no}/{args.baseline_samples}", flush=True)
                    elif sample_no % 10 == 0:
                        print(f"Load samples: {sample_no - args.baseline_samples} (Ctrl+C after benchmark)", flush=True)
                # Announce promptly after last baseline sample (before first load sample).
                if sample_no == args.baseline_samples:
                    print("\n>>> BASELINE COMPLETE. START BENCHMARK IN WINDOWS POWERSHELL:", flush=True)
                    print("    py scripts/17_benchmark_retrieval.py --run --repeats 10", flush=True)
                    print(">>> THEN RETURN TO UBUNTU AND PRESS Ctrl+C.\n", flush=True)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nMonitoring stopped by user; saving results...", flush=True)
    summary = create_summary(records, csv_path, args.baseline_samples, started)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SAVED:", csv_path.name, "and", json_path.name, flush=True)
    for service, info in summary["services"].items():
        load = info.get("load")
        base = info.get("baseline")
        if load and base:
            print(f"  {service}: baseline CPU={base['mean_cpu_pct']:.2f}% RAM={base['mean_mem_mib']:.1f}MiB | "
                  f"load CPU={load['mean_cpu_pct']:.2f}% (peak {load['peak_cpu_pct']:.2f}%), "
                  f"RAM={load['mean_mem_mib']:.1f}MiB (peak {load['peak_mem_mib']:.1f}MiB)", flush=True)
    if summary["samples_by_phase"].get("load", 0) < 2:
        print("WARNING: fewer than two load samples; results are not sufficient.", flush=True)
    return 0 if summary["samples_by_phase"].get("load", 0) >= 2 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
