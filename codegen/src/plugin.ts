import type { OagenConfig } from '@workos/oagen';
import { pythonEmitter } from './python/index.js';

/**
 * The plugin `oagen.config.ts` spreads. The oagen CLI bundles its own copy of
 * the emitter registry, so emitters register through this object (as
 * `oagen init` scaffolds), not through `registerEmitter()`.
 */
export const plugin: Pick<OagenConfig, 'emitters' | 'extractors' | 'smokeRunners'> = {
  emitters: [pythonEmitter],
  extractors: [],
  smokeRunners: {},
};
