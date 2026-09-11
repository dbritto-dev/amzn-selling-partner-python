# ruff: noqa: B023, B007
"""Survey of the pinned Amazon SP-API models used for docs/PLAN.md.

Run from the repository root:  python scripts/spec_inventory.py

Prints per-file counts (operations, definitions, rate-limit tables, sandbox examples,
pagination candidates), spec irregularities, duplicate operationIds and definition-name
collisions across APIs. Stdlib only, so it works before the package is installed.
"""

import collections
import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path("spec/selling-partner-api-models/models")
files = sorted(ROOT.glob("**/*.json"))
METHODS = {"get", "put", "post", "delete", "options", "head", "patch"}
RATE_RE = re.compile(
    r"\|\s*Rate\s*\(requests per second\)\s*\|\s*Burst\s*\|\s*\n\s*\|\s*-+\s*\|\s*-+\s*\|\s*\n\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|", re.I
)
TOKEN_NAMES = {"nexttoken", "pagetoken", "paginationtoken"}
report = {}
defs_by_name = collections.defaultdict(list)  # name -> [(file, hash)]
opids = collections.defaultdict(list)
totals = collections.Counter()
ext_root = collections.Counter()
ext_op = collections.Counter()
for f in files:
    d = json.loads(f.read_text())
    api_dir = f.parent.name
    r = {
        "file": str(f.relative_to(ROOT)),
        "swagger": d.get("swagger") or d.get("openapi"),
        "title": d["info"].get("title"),
        "version": d["info"].get("version"),
        "basePath": d.get("basePath"),
        "host": d.get("host"),
        "schemes": d.get("schemes"),
        "produces": d.get("produces"),
        "consumes": d.get("consumes"),
        "ops": [],
        "missing_opid": [],
        "nonjson": [],
        "tags": collections.Counter(),
        "param_in": collections.Counter(),
        "collectionFormat": collections.Counter(),
        "rate_ok": 0,
        "rate_missing": [],
        "sandbox": [],
        "sandbox_only": [],
        "paginated": [],
        "pag_ambiguous": [],
        "external_refs": set(),
        "defs": len(d.get("definitions", {}) or d.get("components", {}).get("schemas", {})),
        "resp_codes": collections.Counter(),
        "body_params": 0,
        "formdata": 0,
        "file_params": 0,
        "no_schema_2xx": [],
        "path_params": collections.Counter(),
    }
    for k in d:
        if k.startswith("x-"):
            ext_root[k] += 1
    defs = d.get("definitions", {}) or d.get("components", {}).get("schemas", {})
    for name, schema in defs.items():
        h = hashlib.sha1(json.dumps(schema, sort_keys=True).encode()).hexdigest()[:8]
        defs_by_name[name].append((api_dir, f.stem, h))

    # refs
    def walk(o):
        if isinstance(o, dict):
            if "$ref" in o and isinstance(o["$ref"], str) and not o["$ref"].startswith("#/"):
                r["external_refs"].add(o["$ref"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(d)
    for path, item in d.get("paths", {}).items():
        path_level_params = item.get("parameters", [])
        for m, op in item.items():
            if m not in METHODS:
                continue
            totals["ops"] += 1
            oid = op.get("operationId")
            if not oid:
                r["missing_opid"].append(f"{m.upper()} {path}")
            else:
                opids[oid].append(f.stem)
            for k in op:
                if k.startswith("x-"):
                    ext_op[k] += 1
            r["ops"].append(oid)
            for t in op.get("tags", []):
                r["tags"][t] += 1
            prod = op.get("produces", d.get("produces"))
            if prod and any("json" not in p for p in prod):
                r["nonjson"].append((oid, prod))
            params = path_level_params + op.get("parameters", [])
            q_token = None
            for p in params:
                r["param_in"][p.get("in")] += 1
                if p.get("in") == "body":
                    r["body_params"] += 1
                if p.get("in") == "formData":
                    r["formdata"] += 1
                if p.get("type") == "file":
                    r["file_params"] += 1
                if p.get("in") == "path":
                    r["path_params"][p["name"]] += 1
                if "collectionFormat" in p:
                    r["collectionFormat"][p["collectionFormat"]] += 1
                if p.get("in") == "query" and p["name"].lower() in TOKEN_NAMES:
                    q_token = p["name"]
            desc = op.get("description", "") or ""
            mm = RATE_RE.search(desc)
            if mm:
                r["rate_ok"] += 1
            else:
                r["rate_missing"].append(oid)
            if "x-amzn-api-sandbox" in op:
                r["sandbox"].append(oid)
            if "x-amzn-api-sandbox-only" in op:
                r["sandbox_only"].append(oid)
            # responses
            ok = None
            for code, resp in op.get("responses", {}).items():
                r["resp_codes"][code] += 1
                if code.startswith("2"):
                    if "schema" not in resp and "content" not in resp:
                        r["no_schema_2xx"].append((oid, code))
                    elif ok is None:
                        ok = resp
            # pagination heuristic
            if q_token and ok is not None:

                def resolve(s):
                    seen = 0
                    while isinstance(s, dict) and "$ref" in s and seen < 20:
                        s = defs[s["$ref"].split("/")[-1]]
                        seen += 1
                    return s

                s = resolve(ok.get("schema", {}))
                props = {k: resolve(v) for k, v in (s.get("properties") or {}).items()}
                candidates = []
                for container_name, container in [(None, props)] + [
                    (k, {kk: resolve(vv) for kk, vv in (v.get("properties") or {}).items()})
                    for k, v in props.items()
                    if v.get("type") == "object" or "properties" in v
                ]:
                    tok = [k for k in container if k.lower() in TOKEN_NAMES]
                    if tok:
                        arrays = [k for k, v in container.items() if v.get("type") == "array"]
                        if not arrays and container_name:  # arrays next to the container (e.g. pagination sibling)
                            arrays = [k for k, v in props.items() if v.get("type") == "array"]
                            where = "sibling"
                        else:
                            where = "inside"
                        candidates.append((container_name, tok[0], arrays, where))
                if len(candidates) == 1 and len(candidates[0][2]) == 1:
                    r["paginated"].append((oid, q_token, candidates[0][0], candidates[0][1], candidates[0][2][0]))
                else:
                    r["pag_ambiguous"].append((oid, q_token, [(c[0], c[1], c[2]) for c in candidates]))
            elif q_token:
                r["pag_ambiguous"].append((oid, q_token, "no 2xx schema"))
    r["external_refs"] = sorted(r["external_refs"])
    report[f.stem] = r
    totals["files"] += 1
    totals["rate_ok"] += r["rate_ok"]
    totals["rate_missing"] += len(r["rate_missing"])
    totals["sandbox"] += len(r["sandbox"])
    totals["paginated"] += len(r["paginated"])
    totals["ambiguous"] += len(r["pag_ambiguous"])
    totals["defs"] += r["defs"]
    totals["missing_opid"] += len(r["missing_opid"])

print("TOTALS", dict(totals))
print("ROOT EXT", dict(ext_root))
print("OP EXT", dict(ext_op))
print()
print(f"{'file':55} {'sw':4} {'ver':12} {'basePath':40} ops defs rate sbx pag amb tags")
for k, r in report.items():
    print(
        f"{r['file']:55} {r['swagger']:4} {str(r['version']):12} {str(r['basePath']):40} {len(r['ops']):3} {r['defs']:4} {r['rate_ok']:4} {len(r['sandbox']):3} {len(r['paginated']):3} {len(r['pag_ambiguous']):3} {dict(r['tags'])}"
    )
print()
for k, r in report.items():
    for key in ["missing_opid", "nonjson", "rate_missing", "external_refs", "no_schema_2xx", "pag_ambiguous"]:
        if r[key]:
            print(f"{k}: {key}: {r[key]}")
    if r["formdata"] or r["file_params"]:
        print(f"{k}: formData={r['formdata']} file={r['file_params']}")
    if r["produces"] and any("json" not in p for p in r["produces"]):
        print(f"{k}: root produces {r['produces']}")
    if r["consumes"] and any("json" not in p for p in r["consumes"]):
        print(f"{k}: root consumes {r['consumes']}")
    if r["schemes"] != ["https"] or r["host"] not in ("sellingpartnerapi-na.amazon.com",):
        print(f"{k}: host={r['host']} schemes={r['schemes']}")
    if r["collectionFormat"]:
        print(f"{k}: collectionFormat={dict(r['collectionFormat'])}")
    if r["sandbox_only"]:
        print(f"{k}: sandbox_only={r['sandbox_only']}")
print()
print("PAGINATED:")
for k, r in report.items():
    for p in r["paginated"]:
        print(" ", k, p)
print()
print("DUP OPERATION IDS ACROSS FILES:")
for oid, fs in sorted(opids.items()):
    if len(fs) > 1:
        print(" ", oid, fs)
    if len(set(fs)) != len(fs):
        print("  WITHIN-FILE DUP", oid, fs)
print()
print("DEFINITION NAME COLLISIONS (name: #apis, #distinct shapes):")
coll = [(n, v) for n, v in defs_by_name.items() if len({a for a, _, _ in v}) > 1]
coll.sort(key=lambda x: -len(x[1]))
print(
    " total distinct def names:",
    len(defs_by_name),
    " names used by >1 API:",
    len(coll),
    " names with >1 distinct shape:",
    sum(1 for n, v in coll if len({h for _, _, h in v}) > 1),
)
for n, v in coll[:40]:
    print(f"  {n}: {len({a for a, _, _ in v})} apis, {len({h for _, _, h in v})} shapes")
# resp codes
rc = collections.Counter()
for r in report.values():
    rc.update(r["resp_codes"])
print("RESPONSE CODES", dict(rc))
pi = collections.Counter()
for r in report.values():
    pi.update(r["param_in"])
print("PARAM IN", dict(pi))
