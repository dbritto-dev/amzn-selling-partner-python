/**
 * Models: pydantic v2 classes, one `models/<package>/models.py` per package
 * (plus the shared base class in `models/_base.py` and the package
 * `__init__.py` files that re-export models and enums).
 */
import type { ApiSpec, EmitterContext, GeneratedFile, Model } from '@workos/oagen';
import { HEADER_DOC, file } from './header.js';
import { docstring, fieldName, pyStr, Uniquer } from './naming.js';
import { SHARED, packagesOf, type Packages } from './packages.js';
import { renderTypeRef, type TypeContext } from './types.js';

const SYNTHETIC_ADDITIONAL = 'Additional properties not captured by named fields';

/** Type context inside `models/<pkg>/models.py`: same-package classes by name, others through their package alias. */
function moduleContext(pkg: string, packages: Packages, foreign: Set<string>): TypeContext {
  const ref = (place: { pkg: string; cls: string } | undefined, name: string): string => {
    if (!place) return 'Any';
    if (place.pkg === pkg) return place.cls;
    const alias = packages.alias(place.pkg);
    foreign.add(place.pkg);
    return `${alias}.${place.cls}`;
  };
  return {
    model: (name) => ref(packages.models.get(name), name),
    enum: (name) => ref(packages.enums.get(name), name),
  };
}

export function isDiscriminatedAlias(model: Model): boolean {
  return model.fields.length === 0 && model.discriminator !== undefined;
}

export function renderModel(model: Model, cls: string, ctx: TypeContext, packages: Packages): string[] {
  const lines: string[] = [];
  if (isDiscriminatedAlias(model)) {
    const variants = [...new Set(Object.values(model.discriminator!.mapping))].map((v) => ctx.model(v));
    const expr = variants.join(' | ') || 'Any';
    if (variants.length > 1 && !variants.includes('Any')) {
      lines.push(`${cls}: TypeAlias = Annotated[${expr}, Field(discriminator=${pyStr(fieldName(model.discriminator!.property))})]`);
    } else {
      lines.push(`${cls}: TypeAlias = ${expr}`);
    }
    return lines;
  }
  lines.push(`class ${cls}(SpecModel):`);
  if (model.description) lines.push(...docstring(model.description, '    '), '');
  const used = new Uniquer(['model_config']);
  const required = model.fields.filter((f) => f.required);
  const optional = model.fields.filter((f) => !f.required);
  let count = 0;
  for (const f of [...required, ...optional]) {
    if (f.name === 'additionalProperties' && f.description === SYNTHETIC_ADDITIONAL) continue;
    const py = used.take(fieldName(f.domainName ?? f.name));
    const t = renderTypeRef(f.type, ctx);
    const aliased = py !== f.name;
    if (f.required) {
      lines.push(aliased ? `    ${py}: ${t} = Field(alias=${pyStr(f.name)})` : `    ${py}: ${t}`);
    } else {
      const opt = t.split(' | ').includes('None') ? t : `${t} | None`;
      lines.push(aliased ? `    ${py}: ${opt} = Field(default=None, alias=${pyStr(f.name)})` : `    ${py}: ${opt} = None`);
    }
    count++;
  }
  if (count === 0 && !model.description) lines.push('    pass');
  void packages;
  return lines;
}

export function renderModelsModule(pkg: string, models: [Model, string][], packages: Packages): string {
  const foreign = new Set<string>();
  const ctx = moduleContext(pkg, packages, foreign);
  const body: string[] = [];
  const classes = models.filter(([m]) => !isDiscriminatedAlias(m));
  const aliases = models.filter(([m]) => isDiscriminatedAlias(m));
  for (const [m, cls] of classes) body.push(...renderModel(m, cls, ctx, packages), '', '');
  for (const [m, cls] of aliases) body.push(...renderModel(m, cls, ctx, packages));
  const text = body.join('\n');
  const out: string[] = [];
  out.push(`"""Models of ${pkg || 'the API'}.`, '', HEADER_DOC, '"""', '', 'from __future__ import annotations', '');
  if (text.includes('datetime.')) out.push('import datetime');
  const typingNames = ['Annotated', 'Any', 'Literal', 'TypeAlias'].filter((n) => new RegExp(`\\b${n}\\b`).test(text));
  if (typingNames.length) out.push(`from typing import ${typingNames.join(', ')}`);
  out.push('');
  if (text.includes('Field(')) out.push('from pydantic import Field', '');
  const depth = pkg ? pkg.split('.').length : 0;
  const up = '.'.repeat(depth + 1);
  out.push(`from ${up}_base import SpecModel`);
  const enumsHere = [...packages.enums.values()].filter((p) => p.pkg === pkg).map((p) => p.cls).sort();
  const usedEnums = enumsHere.filter((n) => new RegExp(`\\b${n}\\b`).test(text));
  if (usedEnums.length) out.push(`from .enums import ${usedEnums.join(', ')}`);
  for (const other of [...foreign].sort()) {
    const parts = other.split('.');
    const last = parts.pop()!;
    const parent = parts.length ? `${up}${parts.join('.')}` : up.slice(0, -1) || '.';
    const alias = packages.alias(other);
    out.push(alias === last ? `from ${parent} import ${last}` : `from ${parent} import ${last} as ${alias}`);
  }
  out.push('', '', text.trimEnd(), '', '');
  out.push('__all__ = [', ...models.map(([, cls]) => cls).sort().map((n) => `    ${pyStr(n)},`), ']', '');
  return out.join('\n');
}

export const BASE_MODULE = `"""Base class of every generated model.

${HEADER_DOC}
"""

from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel, ConfigDict, TypeAdapter

MODEL_CONFIG = ConfigDict(
    defer_build=True,
    extra="allow",
    populate_by_name=True,
    frozen=True,
    val_json_bytes="base64",
    ser_json_bytes="base64",
)

#: Config for TypeAdapters over non-model types (lists, unions, primitives).
ADAPTER_CONFIG = ConfigDict(
    populate_by_name=True,
    val_json_bytes="base64",
    ser_json_bytes="base64",
)


class SpecModel(BaseModel):
    """Frozen, alias-aware model; unknown wire fields are kept (\`\`extra="allow"\`\`).

    Attributes are snake_case, the wire names are aliases
    (\`\`Order(AmazonOrderId=...)\`\` and \`\`Order(amazon_order_id=...)\`\` both work),
    and the schema is built on first use (\`\`defer_build\`\`), so importing a
    models module only creates classes.
    """

    model_config = MODEL_CONFIG


def adapter_for(python_type: Any) -> TypeAdapter[Any]:
    """\`\`TypeAdapter\`\` for a response/body type (models carry their own config)."""
    if isinstance(python_type, type) and issubclass(python_type, BaseModel):
        return TypeAdapter(python_type)
    return TypeAdapter(cast(Any, python_type), config=ADAPTER_CONFIG)


__all__ = ["ADAPTER_CONFIG", "MODEL_CONFIG", "SpecModel", "adapter_for"]
`;

function packageInit(pkg: string, modelNames: string[], enumNames: string[], children: string[]): string {
  const lines = [`"""Models package \`\`${pkg}\`\`.`, '', HEADER_DOC, '"""', '', 'from __future__ import annotations', ''];
  const exported = [...enumNames, ...modelNames].sort();
  if (enumNames.length) lines.push(`from .enums import ${[...enumNames].sort().join(', ')}`);
  if (modelNames.length) lines.push(`from .models import ${[...modelNames].sort().join(', ')}`);
  if (exported.length) {
    lines.push('', '__all__ = [', ...exported.map((n) => `    ${pyStr(n)},`), ']');
  } else {
    lines.push(`#: subpackages: ${children.join(', ')}`);
  }
  return lines.join('\n') + '\n';
}

export function generateModels(_models: Model[], ctx: EmitterContext): GeneratedFile[] {
  const spec = ctx.spec;
  const packages = packagesOf(ctx);
  const byPkg = new Map<string, [Model, string][]>();
  for (const m of spec.models) {
    const place = packages.models.get(m.name);
    if (!place) continue;
    let list = byPkg.get(place.pkg);
    if (!list) byPkg.set(place.pkg, (list = []));
    list.push([m, place.cls]);
  }
  const enumPkgs = new Set([...packages.enums.values()].map((p) => p.pkg));
  const files: GeneratedFile[] = [file('models/_base.py', BASE_MODULE)];
  for (const [pkg, list] of [...byPkg.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
    list.sort((a, b) => a[1].localeCompare(b[1]));
    files.push(file(`models/${packages.modulePath(pkg)}/models.py`, renderModelsModule(pkg, list, packages)));
  }
  // package __init__ files (every package and every intermediate package)
  const inits = new Map<string, { models: string[]; enums: string[]; children: Set<string> }>();
  const ensure = (pkg: string) => {
    let e = inits.get(pkg);
    if (!e) inits.set(pkg, (e = { models: [], enums: [], children: new Set() }));
    return e;
  };
  for (const pkg of packages.pkgs) {
    const e = ensure(pkg);
    e.models = (byPkg.get(pkg) ?? []).map(([, cls]) => cls);
    e.enums = [...packages.enums.values()].filter((p) => p.pkg === pkg).map((p) => p.cls);
    const parts = pkg.split('.');
    for (let i = parts.length - 1; i > 0; i--) ensure(parts.slice(0, i).join('.')).children.add(parts[i]!);
  }
  for (const [pkg, e] of [...inits.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
    files.push(file(`models/${packages.modulePath(pkg)}/__init__.py`, packageInit(pkg, e.models, e.enums, [...e.children].sort())));
  }
  const top = [...new Set(packages.pkgs.map((p) => p.split('.')[0]!))].sort();
  files.push(
    file(
      'models/__init__.py',
      `"""Generated models of ${spec.name}: one package per API version.

${HEADER_DOC}

Packages: ${top.join(', ')}.
"""

from __future__ import annotations
`,
    ),
  );
  void SHARED;
  void enumPkgs;
  return files;
}
