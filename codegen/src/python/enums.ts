/** Enums: every enum of an API version becomes a `Literal[...]` type alias in the models module. */
import type { Enum } from '@workos/oagen';
import { enumAlias, type TypeContext } from './types.js';

export function renderEnum(e: Enum, ctx: TypeContext): string[] {
  const values = e.values.map((v) => JSON.stringify(v.value));
  return [`${enumAlias(ctx, e.name)}: TypeAlias = Literal[${values.join(', ')}]`];
}

/** Enums sorted by name, rendered one per line. */
export function renderEnums(enums: Enum[], ctx: TypeContext): string[] {
  return [...enums].sort((a, b) => a.name.localeCompare(b.name)).flatMap((e) => renderEnum(e, ctx));
}
