/** Python identifier rules, ported from the former `compile/naming.py`. */

const PY_KEYWORDS = new Set([
  'False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue', 'def', 'del', 'elif', 'else',
  'except', 'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise',
  'return', 'try', 'while', 'with', 'yield', 'match', 'case', 'type',
]);

/** Names that must not be used as pydantic field names. */
const MODEL_RESERVED = new Set([
  'schema', 'copy', 'json', 'dict', 'validate', 'construct', 'fields', 'parse_obj', 'parse_raw', 'parse_file', 'from_orm',
  'update_forward_refs', 'schema_json',
]);

/**
 * Names that must not be used as class/alias names inside a generated module:
 * the module's own imports plus every Python builtin. A class shadowing a
 * builtin (``Warning``) would resolve to the builtin in annotations evaluated
 * before the class statement runs.
 */
const MODULE_RESERVED = new Set([
  'Any', 'Optional', 'Union', 'Literal', 'Annotated', 'datetime', 'date', 'Field', 'BaseModel', 'SpecModel', 'TypeAlias', 'annotations',
  'models', 'runtime',
  // builtins (python 3.10+)
  'ArithmeticError', 'AssertionError', 'AttributeError', 'BaseException', 'BaseExceptionGroup', 'BlockingIOError', 'BrokenPipeError',
  'BufferError', 'BytesWarning', 'ChildProcessError', 'ConnectionAbortedError', 'ConnectionError', 'ConnectionRefusedError',
  'ConnectionResetError', 'DeprecationWarning', 'EOFError', 'Ellipsis', 'EncodingWarning', 'EnvironmentError', 'Exception',
  'ExceptionGroup', 'False', 'FileExistsError', 'FileNotFoundError', 'FloatingPointError', 'FutureWarning', 'GeneratorExit', 'IOError',
  'ImportError', 'ImportWarning', 'IndentationError', 'IndexError', 'InterruptedError', 'IsADirectoryError', 'KeyError',
  'KeyboardInterrupt', 'LookupError', 'MemoryError', 'ModuleNotFoundError', 'NameError', 'None', 'NotADirectoryError', 'NotImplemented',
  'NotImplementedError', 'OSError', 'OverflowError', 'PendingDeprecationWarning', 'PermissionError', 'ProcessLookupError',
  'RecursionError', 'ReferenceError', 'ResourceWarning', 'RuntimeError', 'RuntimeWarning', 'StopAsyncIteration', 'StopIteration',
  'SyntaxError', 'SyntaxWarning', 'SystemError', 'SystemExit', 'TabError', 'TimeoutError', 'True', 'TypeError', 'UnboundLocalError',
  'UnicodeDecodeError', 'UnicodeEncodeError', 'UnicodeError', 'UnicodeTranslateError', 'UnicodeWarning', 'UserWarning', 'ValueError',
  'Warning', 'ZeroDivisionError', 'abs', 'aiter', 'all', 'anext', 'any', 'ascii', 'bin', 'bool', 'breakpoint', 'bytearray', 'bytes',
  'callable', 'chr', 'classmethod', 'compile', 'complex', 'copyright', 'credits', 'delattr', 'dict', 'dir', 'divmod', 'enumerate',
  'eval', 'exec', 'exit', 'filter', 'float', 'format', 'frozenset', 'getattr', 'globals', 'hasattr', 'hash', 'help', 'hex', 'id',
  'input', 'int', 'isinstance', 'issubclass', 'iter', 'len', 'license', 'list', 'locals', 'map', 'max', 'memoryview', 'min', 'next',
  'object', 'oct', 'open', 'ord', 'pow', 'print', 'property', 'quit', 'range', 'repr', 'reversed', 'round', 'set', 'setattr', 'slice',
  'sorted', 'staticmethod', 'str', 'sum', 'super', 'tuple', 'type', 'vars', 'zip',
]);

export function snakeCase(name: string): string {
  let s = name.replace(/[^0-9a-zA-Z_]+/g, '_');
  s = s.replace(/(.)([A-Z][a-z]+)/g, '$1_$2');
  s = s.replace(/([a-z0-9])([A-Z])/g, '$1_$2');
  s = s.replace(/_+/g, '_').replace(/^_+|_+$/g, '').toLowerCase();
  return s || 'field';
}

export function pascalCase(name: string): string {
  const parts = name.replace(/[^0-9a-zA-Z_]+/g, '_').split('_').filter(Boolean);
  return parts.map((p) => p.charAt(0).toUpperCase() + p.slice(1)).join('') || 'Model';
}

/** Make `name` a valid, non-keyword python identifier (keeps case). */
export function identifier(name: string): string {
  let s = name.replace(/[^0-9a-zA-Z_]+/g, '_');
  if (!s || /^[0-9]/.test(s)) s = '_' + s;
  if (PY_KEYWORDS.has(s)) s += '_';
  return s;
}

/** Python attribute name for a spec property name. */
export function fieldName(wireName: string): string {
  let s = snakeCase(wireName);
  if (/^[0-9]/.test(s)) s = 'n' + s;
  if (s.startsWith('_')) s = 'x' + s;
  if (PY_KEYWORDS.has(s) || MODEL_RESERVED.has(s) || s.startsWith('model_')) s += '_';
  return s;
}

/** Python keyword name for an operation parameter. */
export function paramName(wireName: string): string {
  let s = snakeCase(wireName);
  if (/^[0-9]/.test(s)) s = 'p' + s;
  if (PY_KEYWORDS.has(s) || ['self', 'raw', 'request_options', 'body', 'paginate'].includes(s)) s += '_';
  return s;
}

export function methodName(operationId: string): string {
  let s = snakeCase(operationId);
  if (PY_KEYWORDS.has(s)) s += '_';
  return s;
}

/**
 * Class / type-alias name for a schema. The first letter is upper-cased so a
 * class never shares its name with a snake_case field (a field assignment in
 * the class body would shadow the class when pydantic evaluates annotations),
 * and names that shadow a builtin or an import get a trailing underscore.
 */
export function className(schemaName: string): string {
  let s = identifier(schemaName);
  s = s.charAt(0).toUpperCase() + s.slice(1);
  if (s.startsWith('_')) s = 'X' + s.slice(1);
  if (MODULE_RESERVED.has(s)) s += '_';
  return s;
}

/** Python string literal (double quoted). */
export function pyStr(value: string): string {
  return JSON.stringify(value);
}

export function pyLiteral(value: unknown): string {
  if (value === null || value === undefined) return 'None';
  if (typeof value === 'string') return pyStr(value);
  if (typeof value === 'boolean') return value ? 'True' : 'False';
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : 'None';
  if (Array.isArray(value)) return '[' + value.map(pyLiteral).join(', ') + ']';
  if (typeof value === 'object') {
    return '{' + Object.entries(value as Record<string, unknown>).map(([k, v]) => `${pyStr(k)}: ${pyLiteral(v)}`).join(', ') + '}';
  }
  return 'None';
}

/** Triple-quoted docstring body, safe against embedded quotes/backslashes. */
export function docstring(text: string, indent: string): string[] {
  const clean = text.replace(/\\/g, '\\\\').replace(/"""/g, '\\"\\"\\"').replace(/\r\n?/g, '\n').trimEnd();
  const lines = clean.split('\n').map((l) => l.trimEnd());
  if (lines.length === 1) return [`${indent}"""${lines[0]}"""`];
  return [`${indent}"""${lines[0]}`, ...lines.slice(1).map((l) => (l ? `${indent}${l}` : '')), `${indent}"""`];
}

/** Allocate unique names within one scope (`foo`, `foo_2`, ...). */
export class Uniquer {
  private readonly used = new Set<string>();
  constructor(reserved: Iterable<string> = []) {
    for (const r of reserved) this.used.add(r);
  }
  take(name: string): string {
    let cand = name;
    let n = 2;
    while (this.used.has(cand)) cand = `${name}_${n++}`;
    this.used.add(cand);
    return cand;
  }
  has(name: string): boolean {
    return this.used.has(name);
  }
}
