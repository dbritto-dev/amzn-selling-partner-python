/** The Python emitter: models, enums, resources, client + HTTP client, errors. */
import type { ApiSpec, Emitter, EmitterContext, Enum, GeneratedFile, Model, Service } from '@workos/oagen';
import { generateClient } from './client.js';
import { generateEnums } from './enums.js';
import { generateErrors } from './errors.js';
import { FILE_HEADER } from './header.js';
import { generateHttpClient } from './http_client.js';
import { generateModels } from './models.js';
import { optionsOf } from './options.js';
import { planPackages, type Packages } from './packages.js';
import { generateResources } from './resources.js';

const plans = new WeakMap<ApiSpec, Packages>();

/** Generated files are never hand-edited: always overwrite (oagen merges `__init__.py` files additively by default). */
function overwrite(files: GeneratedFile[]): GeneratedFile[] {
  return files.map((f) => ({ ...f, overwriteExisting: true }));
}

/** Package plan of a spec (computed once per generation). */
export function packagesOf(ctx: EmitterContext): Packages {
  let p = plans.get(ctx.spec);
  if (!p) plans.set(ctx.spec, (p = planPackages(ctx.spec)));
  return p;
}

/** Notes collected while generating (unparsed rate limits, pagination decisions); read by the tests and the CLI wrapper. */
export const notes: string[] = [];

export const pythonEmitter: Emitter = {
  language: 'python',
  generateModels(models: Model[], ctx: EmitterContext): GeneratedFile[] {
    return overwrite(generateModels(models, ctx, ctx.spec, packagesOf(ctx)));
  },
  generateEnums(enums: Enum[], ctx: EmitterContext): GeneratedFile[] {
    return overwrite(generateEnums(enums, ctx, packagesOf(ctx)));
  },
  generateResources(services: Service[], ctx: EmitterContext): GeneratedFile[] {
    notes.length = 0;
    return overwrite(generateResources(services, ctx, packagesOf(ctx), optionsOf(ctx), notes));
  },
  generateClient(spec: ApiSpec, ctx: EmitterContext): GeneratedFile[] {
    const opts = optionsOf(ctx);
    return overwrite([...generateClient(spec, ctx, packagesOf(ctx), opts), ...generateHttpClient(ctx, opts)]);
  },
  generateErrors(ctx: EmitterContext): GeneratedFile[] {
    return overwrite(generateErrors(ctx));
  },
  generateTests(_spec: ApiSpec, _ctx: EmitterContext): GeneratedFile[] {
    return [];
  },
  fileHeader(): string {
    return FILE_HEADER;
  },
};

export { FILE_HEADER } from './header.js';
