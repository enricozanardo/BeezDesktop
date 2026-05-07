#!/usr/bin/env python3
"""Self-contained production probe for the Beez Network.

Mirrors the gate-fail logic from
`<monorepo>/deploy/scripts/reproduce_desktop_bugs.py` but ships inside
BeezDesktop so it can run on this repo's GitHub Actions without needing
the rest of the monorepo on disk.

Exit codes:
    0  -- every probed endpoint behaved within budget; safe-to-release
    1  -- at least one regression was detected; CI fails the workflow

Usage:
    python3 scripts/prod_probe.py --out-dir reports/probe_$(date +%s)/
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

DIRECTORIES = [
    ("dir1", "167.235.25.169"),
    ("dir2", "157.180.40.116"),
    ("dir3", "128.140.114.51"),
]
CHAINS = [
    ("chain1", "138.199.217.130"),
    ("chain2", "88.99.13.161"),
    ("chain3", "37.27.35.61"),
]
SMARTS = [
    ("smart1", "5.75.185.115"),
    ("smart2", "94.130.150.215"),
    ("smart3", "128.140.105.169"),
]
DAMS = [
    ("dam1", "157.180.73.12"),
    ("dam2", "138.199.169.34"),
    ("dam3", "188.245.255.255"),
]
STORAGES = [
    ("storage1", "188.245.236.152"),
    ("storage2", "116.203.60.210"),
    ("storage3", "157.180.68.8"),
]


def http(label: str, method: str, url: str, timeout: float = 8.0,
         **kwargs: Any) -> tuple[int, Any, str]:
    t0 = time.monotonic()
    status = -1
    body: Any = None
    err = ""
    try:
        r = requests.request(method, url, timeout=timeout, **kwargs)
        status = r.status_code
        try:
            body = r.json()
        except Exception:
            body = r.text[:1000]
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
    dt = round((time.monotonic() - t0) * 1000)
    print(f"[{status if status > 0 else 'ERR'}] {method} {url}  ({dt}ms){' '+err if err else ''}")
    return status, body, err


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=None,
                    help="Directory for raw artefacts. Default: reports/<utc>/")
    args = ap.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else (
        Path("reports") / f"probe_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    artefact: dict[str, Any] = {}

    # ---- Smart node liveness (D-04, D-05 detector) ---------------------
    print("=== SMART probes ===")
    smart_results: dict[str, Any] = {}
    listing_counts: dict[str, int] = {}
    for name, ip in SMARTS:
        info_st, info_body, info_err = http(name, "GET", f"http://{ip}:5000/info")
        ws_st, _, _ = http(name, "GET",
                            f"http://{ip}:5000/workspace/stats?wallet_address=bezPROBE")
        mk_st, mk_body, _ = http(name, "GET",
                            f"http://{ip}:5000/marketplace/search?q=&limit=100")
        listing_count = 0
        if isinstance(mk_body, dict):
            listing_count = int(mk_body.get("count", 0) or 0)
        listing_counts[name] = listing_count
        smart_results[name] = {
            "info": info_st, "workspace_stats": ws_st,
            "marketplace_search": mk_st, "marketplace_count": listing_count,
            "node_id": info_body.get("node_id") if isinstance(info_body, dict) else None,
        }
        if info_st != 200 or not isinstance(info_body, dict):
            failures.append(f"smart:{name}:/info")
        if ws_st != 200:
            failures.append(f"smart:{name}:/workspace/stats={ws_st}")
        if mk_st != 200:
            failures.append(f"smart:{name}:/marketplace/search={mk_st}")
    artefact["smart"] = smart_results

    # ---- B-16 marketplace replication detector -------------------------
    # If at least one smart node sees listings, every smart node must see
    # the SAME number (within tolerance), otherwise marketplace state is
    # not being replicated and the desktop will hit "listing not found"
    # depending on which node it picked.
    if listing_counts:
        max_seen = max(listing_counts.values())
        min_seen = min(listing_counts.values())
        if max_seen > 0 and (max_seen - min_seen) > 0:
            failures.append(
                f"smart:marketplace replication drift: counts={listing_counts} "
                f"(B-16: knowledge_publish on one smart node is not propagated "
                f"to the others)"
            )
    artefact["smart_marketplace_counts"] = listing_counts

    # ---- Chain liveness + Phase 7-G4 public health probe ---------------
    print("=== CHAIN probes ===")
    chain_results: dict[str, Any] = {}
    for name, ip in CHAINS:
        bi_st, _, _ = http(name, "GET", f"http://{ip}:5000/api/blockchain/info")
        cons_st, cons_body, _ = http(name, "GET",
                                      f"http://{ip}:5000/network/consensus")
        ph_st, ph_body, _ = http(name, "GET",
                                  f"http://{ip}:5000/api/postgres/health")
        chain_results[name] = {"blockchain_info": bi_st, "network_consensus": cons_st,
                                "postgres_health": ph_st}
        if bi_st != 200:
            failures.append(f"chain:{name}:/api/blockchain/info={bi_st}")
        if ph_st not in (200, 503):
            failures.append(
                f"chain:{name}:/api/postgres/health={ph_st} "
                f"(expect 200 or 503; 403/404 means PUBLIC_OVERRIDES not deployed)"
            )

    # Chain consensus visibility (audit A-07 detector)
    seen = []
    for n, info in chain_results.items():
        if info.get("network_consensus") == 200:
            try:
                _, body, _ = http(f"{n}:cons-recheck", "GET",
                                   f"http://{dict(CHAINS)[n]}:5000/network/consensus")
                if isinstance(body, dict) and isinstance(body.get("statistics"), dict):
                    seen.append(body["statistics"].get("total_nodes", 0))
            except Exception:
                pass
    if seen and max(seen) <= 1:
        failures.append(
            f"chain:network/consensus all chains see <=1 node "
            f"(directory consensus has many more); A-07 regression"
        )
    artefact["chain"] = chain_results
    artefact["chain_consensus_widths"] = seen

    # ---- Directory + DAM + Storage liveness ----------------------------
    print("=== DIRECTORY/DAM/STORAGE health ===")
    dir_results = {n: http(n, "POST", f"http://{ip}:5000/request_consensus")[0]
                   for n, ip in DIRECTORIES}
    dam_results = {n: http(n, "GET", f"http://{ip}:5000/health")[0]
                   for n, ip in DAMS}
    storage_results = {n: http(n, "GET", f"http://{ip}:5000/health")[0]
                       for n, ip in STORAGES}
    artefact["directory"] = dir_results
    artefact["dam"] = dam_results
    artefact["storage"] = storage_results

    for n, st in dir_results.items():
        if st != 200:
            failures.append(f"directory:{n}:/request_consensus={st}")
    for n, st in dam_results.items():
        if st != 200:
            failures.append(f"dam:{n}:/health={st}")
    for n, st in storage_results.items():
        if st != 200:
            failures.append(f"storage:{n}:/health={st}")

    # ---- Write artefacts + verdict -------------------------------------
    artefact["failures"] = failures
    artefact["timestamp"] = datetime.now(timezone.utc).isoformat()
    (out_dir / "probe.json").write_text(json.dumps(artefact, indent=2))

    md = ["# Production probe report", f"Run: {artefact['timestamp']}", ""]
    if failures:
        md.append(f"## Verdict: FAIL ({len(failures)} issues)")
        for f in failures:
            md.append(f"- {f}")
    else:
        md.append("## Verdict: PASS")
        md.append("All probed smart/chain/directory/dam/storage endpoints behaved within budget.")
    md.append("")
    md.append("## Raw response codes")
    md.append("```json")
    md.append(json.dumps(artefact, indent=2)[:8000])
    md.append("```")
    (out_dir / "summary.md").write_text("\n".join(md))

    if failures:
        print("")
        print(f"=== PROD PROBE FAILED: {len(failures)} issues ===")
        for f in failures:
            print(f"  FAIL: {f}")
        return 1

    print("")
    print("=== PROD PROBE PASSED ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
