// Live-auth smoke test against the *real* Microsoft Graph.
//
// Deliberately separate from the fixture-mode suite (actions.test.ts et al.):
// it mints real tokens via owa-piggy and hits the network, so it is flaky and
// CI-hostile. It only runs when OWA_TUI_LIVE_E2E=1 is set in the environment —
// otherwise every case below is skipped via test.when(LIVE, ...).
//
// Run locally with a signed-in owa-piggy profile:
//   OWA_TUI_LIVE_E2E=1 npx tui-test e2e/live.test.ts
//
// Crucially this does NOT set OWA_TUI_FIXTURES, so the app authenticates for
// real instead of loading canned data.
import { test, expect } from "@microsoft/tui-test";

const LIVE = process.env.OWA_TUI_LIVE_E2E === "1";

// A live /me fetch renders the response object as "key: value" rows. The
// "userPrincipalName" key is identity-independent and only ever appears when a
// real token successfully fetched /me — so it is our proof that live auth and
// the network round-trip both worked. (Avoids hardcoding any specific UPN, and
// sidesteps regex/multi-match quirks in getByText.)
const ME_FIELD = "userPrincipalName";
// .not.toBeVisible uses matchAll, so this RegExp must carry the global flag.
const AUTH_ERROR = /auth.*fail|no token|connection error/gi;

test.describe("live graph smoke", () => {
  // Launch straight into the Graph screen via --tool (no fragile menu nav), with
  // the real environment: no OWA_TUI_FIXTURES, so owa-piggy auth + live Graph.
  test.use({
    program: { file: "owa-tui", args: ["--tool", "graph"] },
    columns: 120,
    rows: 40,
  });

  test.when(LIVE, "Graph opens against live Graph and renders the live /me object", async ({ terminal }) => {
    // A real token mints, /me is fetched, and its fields render as rows.
    await expect(terminal.getByText(ME_FIELD, { strict: false })).toBeVisible({ timeout: 30_000 });

    // And we did not land on an auth/connection failure.
    await expect(terminal.getByText(AUTH_ERROR)).not.toBeVisible();
  });
});
