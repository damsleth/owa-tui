import { defineConfig } from "@microsoft/tui-test";

// Run the locally-installed owa-tui CLI under a real pty.
export default defineConfig({
  retries: 2,
  trace: true,
});
