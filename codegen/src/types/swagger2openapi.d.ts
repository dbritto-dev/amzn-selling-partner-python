declare module 'swagger2openapi' {
  export interface ConvertOptions {
    patch?: boolean;
    warnOnly?: boolean;
    resolve?: boolean;
    direct?: boolean;
  }
  export interface ConvertResult {
    openapi: Record<string, unknown>;
    warnings?: unknown[];
  }
  const converter: {
    convertObj(swagger: Record<string, unknown>, options: ConvertOptions): Promise<ConvertResult>;
  };
  export default converter;
}
