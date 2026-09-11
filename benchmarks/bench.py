"""Benchmarks against a local uvicorn echo server.

Scenarios (sync and async, async with and without the aiohttp transport):

  (a) transport only            httpx2 client GET
  (b) transport + BaseClient    generated op, raw=True (JSON parse, no models)
  (c) full client               generated op with model decoding
  (d) generated vs hand-written generated method vs an equivalent hand-written
                                function using the same httpx2 client and
                                model class; the generated path must be within
                                10 % (the ratio is printed and checked)

Decode-only timings for 100 KB / 1 MB / 5 MB responses in model and raw mode.

    python benchmarks/bench.py [--iterations N] [--json out.json]
    python benchmarks/bench.py --compare baseline.json --threshold 0.15

``--compare`` fails (exit 1) when any "ops/s" figure regressed by more than
the threshold relative to the baseline file (used by the nightly CI job).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any

import httpx2
from pydantic_core import from_json

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))  # the generated petstore package (codegen/)

from petstore_sdk.client import AsyncClient, Client  # noqa: E402

from amzn_selling_partner.runtime._transports import aiohttp_available  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class Server:
    def __init__(self) -> None:
        self.port = _free_port()
        self.proc: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> Server:
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "echo_app:app", "--port", str(self.port), "--log-level", "error", "--no-access-log"],
            cwd=ROOT / "benchmarks",
        )
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                httpx2.get(f"http://127.0.0.1:{self.port}/v1/pets/1", timeout=0.5)
                return self
            except httpx2.TransportError:
                time.sleep(0.05)
        raise RuntimeError("uvicorn did not start")

    def __exit__(self, *args: Any) -> None:
        if self.proc is not None:
            self.proc.terminate()
            self.proc.wait(5)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"


def timeit(fn: Callable[[], Any], iterations: int, *, repeats: int = 3) -> float:
    """Best-of-N wall time per call in microseconds."""
    best = float("inf")
    for _ in range(repeats):
        fn()  # warm-up
        t0 = time.perf_counter()
        for _ in range(iterations):
            fn()
        best = min(best, (time.perf_counter() - t0) / iterations)
    return best * 1e6


async def atimeit(fn: Callable[[], Any], iterations: int, *, repeats: int = 3) -> float:
    best = float("inf")
    for _ in range(repeats):
        await fn()
        t0 = time.perf_counter()
        for _ in range(iterations):
            await fn()
        best = min(best, (time.perf_counter() - t0) / iterations)
    return best * 1e6


def sync_scenarios(base_url: str, iterations: int) -> dict[str, float]:
    results: dict[str, float] = {}
    http = httpx2.Client(base_url=base_url, timeout=10.0)
    client = Client(base_url=base_url, http_client=http, throttle=False)
    api = client.petstore.v3
    Pet = api.models.Pet
    url = f"{base_url}/pets/1"

    results["sync/transport_only"] = timeit(lambda: http.get(url).content, iterations)
    results["sync/base_client_raw"] = timeit(lambda: api.get_pet(pet_id=1, raw=True), iterations)
    results["sync/full_model"] = timeit(lambda: api.get_pet(pet_id=1), iterations)

    def hand_written(pet_id: int) -> Any:
        request = http.build_request("GET", f"/pets/{pet_id}", headers={"Accept": "application/json"})
        response = http.send(request)
        if response.status_code >= 400:
            raise RuntimeError(response.status_code)
        return Pet.model_validate_json(response.content)

    results["sync/hand_written"] = timeit(lambda: hand_written(1), iterations)
    results["sync/dynamic_op"] = timeit(lambda: api.get_pet(pet_id=1), iterations)
    http.close()
    return results


async def async_scenarios(base_url: str, iterations: int, *, prefer_aiohttp: bool) -> dict[str, float]:
    label = "async_aiohttp" if prefer_aiohttp else "async"
    results: dict[str, float] = {}
    client = AsyncClient(base_url=base_url, throttle=False, prefer_aiohttp=prefer_aiohttp)
    api = client.petstore.v3
    Pet = api.models.Pet
    http = client.http_client
    url = f"{base_url}/pets/1"

    async def transport_only() -> bytes:
        return (await http.get(url)).content

    async def hand_written(pet_id: int) -> Any:
        request = http.build_request("GET", f"{base_url}/pets/{pet_id}", headers={"Accept": "application/json"})
        response = await http.send(request)
        if response.status_code >= 400:
            raise RuntimeError(response.status_code)
        return Pet.model_validate_json(response.content)

    results[f"{label}/transport_only"] = await atimeit(transport_only, iterations)
    results[f"{label}/base_client_raw"] = await atimeit(lambda: api.get_pet(pet_id=1, raw=True), iterations)
    results[f"{label}/full_model"] = await atimeit(lambda: api.get_pet(pet_id=1), iterations)
    results[f"{label}/hand_written"] = await atimeit(lambda: hand_written(1), iterations)
    results[f"{label}/dynamic_op"] = await atimeit(lambda: api.get_pet(pet_id=1), iterations)
    await client.aclose()
    return results


def decode_scenarios(base_url: str) -> dict[str, float]:
    from echo_app import pet_list

    client = Client(base_url=base_url, throttle=False)
    api = client.petstore.v3
    adapter = api.operation("listPets").default_decoder.adapter
    results: dict[str, float] = {}
    for label, size in (("100KB", 100_000), ("1MB", 1_000_000), ("5MB", 5_000_000)):
        body = pet_list(size)
        n = max(3, 3_000_000 // size)
        results[f"decode/{label}/model"] = timeit(lambda body=body: adapter.validate_json(body), n, repeats=2)
        results[f"decode/{label}/raw"] = timeit(lambda body=body: from_json(body), n, repeats=2)
        results[f"decode/{label}/bytes"] = float(len(body))
    return results


def run(iterations: int) -> dict[str, float]:
    results: dict[str, float] = {}
    with Server() as server:
        results.update(sync_scenarios(server.base_url, iterations))
        results.update(asyncio.run(async_scenarios(server.base_url, iterations, prefer_aiohttp=False)))
        if aiohttp_available():
            results.update(asyncio.run(async_scenarios(server.base_url, iterations, prefer_aiohttp=True)))
        results.update(decode_scenarios(server.base_url))
    return results


def report(results: dict[str, float]) -> list[str]:
    lines = [f"{'scenario':32} {'µs/call':>10} {'ops/s':>10}"]
    for key, us in results.items():
        if key.endswith("/bytes"):
            continue
        lines.append(f"{key:32} {us:10.1f} {1e6 / us:10.0f}")
    problems: list[str] = []
    for prefix in ("sync", "async", "async_aiohttp"):
        hw, dyn = results.get(f"{prefix}/hand_written"), results.get(f"{prefix}/dynamic_op")
        if hw and dyn:
            ratio = dyn / hw
            flag = "OK" if ratio <= 1.10 else "SLOW"
            lines.append(f"{prefix}: dynamic op / hand-written = {ratio:.3f} ({flag}, limit 1.10)")
            if ratio > 1.10:
                problems.append(f"{prefix} dynamic path is {ratio:.3f}x the hand-written function")
    for label in ("100KB", "1MB", "5MB"):
        m, r = results.get(f"decode/{label}/model"), results.get(f"decode/{label}/raw")
        if m and r:
            mb = results[f"decode/{label}/bytes"] / 1e6
            lines.append(
                f"decode {label}: model {m / 1000:.2f} ms ({mb / (m / 1e6):.0f} MB/s), raw {r / 1000:.2f} ms ({mb / (r / 1e6):.0f} MB/s)"
            )
    return lines + problems


def compare(results: dict[str, float], baseline: dict[str, float], threshold: float) -> list[str]:
    regressions: list[str] = []
    for key, us in results.items():
        if key.endswith("/bytes") or key not in baseline:
            continue
        base = baseline[key]
        if base > 0 and us > base * (1 + threshold):
            regressions.append(f"{key}: {us:.1f} µs vs baseline {base:.1f} µs (+{(us / base - 1) * 100:.0f}%)")
    return regressions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=300)
    parser.add_argument("--json", help="write results to this file")
    parser.add_argument("--compare", help="baseline JSON to compare against")
    parser.add_argument("--threshold", type=float, default=0.15)
    parser.add_argument("--strict-ratio", action="store_true", help="fail when the dynamic path exceeds 110%% of hand-written")
    args = parser.parse_args(argv)
    results = run(args.iterations)
    lines = report(results)
    print("\n".join(lines))
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(results, indent=1))
    rc = 0
    if args.strict_ratio and any(line.endswith("hand-written function") for line in lines):
        rc = 1
    if args.compare:
        baseline = json.loads(pathlib.Path(args.compare).read_text())
        regressions = compare(results, baseline, args.threshold)
        if regressions:
            print("REGRESSIONS:\n" + "\n".join(regressions))
            rc = 1
        else:
            print(f"no regressions above {args.threshold:.0%}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
