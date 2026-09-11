"""Report per-API load + compile time for the Amazon models (cold and from the IR cache).

python scripts/report_load_times.py [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


def measure(label: str) -> dict[str, float]:
    # each measurement runs in a fresh interpreter so imports/model memo don't leak
    code = r"""
import json, sys, time
t0 = time.perf_counter()
import amzn_selling_partner
from amzn_selling_partner.plugins.amazon_spapi import SellingPartner
import_ms = (time.perf_counter() - t0) * 1000
client = SellingPartner(transport=None, credentials=None, throttle=False)
out = {"__import__": import_ms}
for api in client.apis:
    container = client.api(api)
    for version in container.versions:
        av = container.version(version)
        t0 = time.perf_counter()
        av.operations          # load IR (+cache) + compile ops (lazy models)
        getattr(container, version)
        out[av.key] = (time.perf_counter() - t0) * 1000
print(json.dumps(out))
"""
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    return json.loads(proc.stdout.strip().splitlines()[-1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json")
    args = parser.parse_args()
    cold = measure("cold")
    warm = measure("cache")
    warm2 = measure("cache")
    keys = [k for k in cold if k != "__import__"]
    total_cold = sum(cold[k] for k in keys)
    total_warm = sum(min(warm[k], warm2[k]) for k in keys)
    print(f"{'api.version':45} {'cold ms':>9} {'cache ms':>9}")
    for k in sorted(keys, key=lambda k: -cold[k]):
        print(f"{k:45} {cold[k]:9.1f} {min(warm[k], warm2[k]):9.1f}")
    print(f"{'TOTAL (' + str(len(keys)) + ' api versions)':45} {total_cold:9.1f} {total_warm:9.1f}")
    print(f"import amzn_selling_partner + SellingPartner(): cold {cold['__import__']:.1f} ms, warm {warm['__import__']:.1f} ms")
    worst_warm = max(min(warm[k], warm2[k]) for k in keys)
    worst_cold = max(cold[k] for k in keys)
    print(f"worst per-API: cold {worst_cold:.1f} ms (target < 300), cache {worst_warm:.1f} ms (target < 50)")
    if args.json:
        with open(args.json, "w") as fh:
            json.dump({"cold": cold, "cache": {k: min(warm[k], warm2[k]) for k in keys}}, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
