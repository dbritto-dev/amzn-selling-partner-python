import { registerEmitter } from '@workos/oagen';
import { pythonEmitter } from './python/index.js';

registerEmitter(pythonEmitter);

// The oagen CLI bundles its own copy of the registry, so it registers the
// emitters listed here (as `oagen init` scaffolds) rather than seeing the
// registerEmitter() call above, which serves library users of this package.
export const myEmittersPlugin = { emitters: [pythonEmitter] };
