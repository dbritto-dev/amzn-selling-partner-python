/** Plugin bundle (what `oagen init` scaffolds): every emitter this project provides. */
import type { OagenConfig } from '@workos/oagen';
import { pythonEmitter } from './python/index.js';

export const plugin: Pick<OagenConfig, 'emitters' | 'extractors' | 'smokeRunners'> = {
  emitters: [pythonEmitter],
  extractors: [],
  smokeRunners: {},
};
