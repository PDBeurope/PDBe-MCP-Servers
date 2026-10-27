/** MP4 export is not enabled by this MCP App's Mol* viewer configuration. */
export async function createH264MP4Encoder(): Promise<never> {
  throw new Error("MP4 video export is unavailable in this Molecular Workspace.");
}
