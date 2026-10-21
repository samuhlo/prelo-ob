declare module "*.svg" {
  const svg: string;
  export default svg;
}
declare module "*.wasm" {
  const binary: Uint8Array;
  export default binary;
}
