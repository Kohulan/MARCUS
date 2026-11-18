// ketcher-standalone 3.18.0's package.json "exports" maps "./dist/binaryWasm" to JavaScript
// only (no "types"), so TypeScript cannot see dist/binaryWasm/index.d.ts. That file is
// `export * from './infrastructure/services'`, the same API as the package root.
declare module "ketcher-standalone/dist/binaryWasm" {
  export * from "ketcher-standalone";
}
