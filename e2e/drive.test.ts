// End-to-end coverage of the Drive (OneDrive) tool user actions, driven
// through the real owa-tui binary in a pty.  Deterministic data comes from
// OWA_TUI_FIXTURES (see src/owa_tui/fixtures.py) — no live auth needed.
//
// FIXTURE SEAM:
//   drive.json            root listing (folder + file)
//   drive_Q2_Reports.json drilled-folder listing (files inside "Q2 Reports")
//
// KEY GOTCHAS applied throughout:
//   - import { test, expect } named import (not default)
//   - test.use({ columns:120, rows:40 }) via size spread
//   - getByText is strict by default; use { strict:false } wherever text
//     appears in both breadcrumb AND list row (name, path)
//   - ListView starts index=None; press "j" BEFORE "l"/enter to drill
//   - drill into folder: terminal.write("l") after "j"
//   - go up: terminal.write("h")
//   - OWA_TUI_FIXTURES must be an absolute path — derive from import.meta.url
//   - env spread: { ...process.env, OWA_TUI_FIXTURES: FIXTURES }
//   - launch args: ["--tool", "drive"]

import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@microsoft/tui-test";

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), "fixtures");
const env = { ...process.env, OWA_TUI_FIXTURES: FIXTURES };
// Wide enough that breadcrumb + name columns do not truncate.
const size = { columns: 120, rows: 40 };

test.describe("drive", () => {
  test.use({ program: { file: "owa-tui", args: ["--tool", "drive"] }, env, ...size });

  // ---------------------------------------------------------------------------
  // 1. Root listing — folder and file both render from drive.json
  // ---------------------------------------------------------------------------
  test("renders the root OneDrive listing from fixtures", async ({ terminal }) => {
    // Both entries are in the root fixture.
    await expect(terminal.getByText("Q2 Reports", { strict: false })).toBeVisible();
    await expect(
      terminal.getByText("Architecture Decision Record.docx", { strict: false })
    ).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 2. j then l — drills into a folder; child items from drive_Q2_Reports.json
  //
  // GOTCHA: ListView starts index=None; "l" is a no-op until "j" highlights a row.
  // GOTCHA: folder name appears in both the list row AND the breadcrumb after
  //         drilling — use strict:false everywhere the name might be duplicated.
  // ---------------------------------------------------------------------------
  test("j then l drills into a folder and shows its children", async ({ terminal }) => {
    // Wait for root to be ready.
    await expect(terminal.getByText("Q2 Reports", { strict: false })).toBeVisible();

    // Highlight the first row (the folder).
    terminal.write("j");
    // Drill into the folder.
    terminal.write("l");

    // After drilling, the breadcrumb should contain the folder name AND
    // at least one child file should be visible.
    // strict:false because "Q2 Reports" now appears in breadcrumb + possibly status.
    await expect(terminal.getByText("Q2 Reports", { strict: false })).toBeVisible();
    // Child from drive_Q2_Reports.json (fallback: drive.json re-renders if slug mismatches).
    await expect(
      terminal.getByText("Q2 2026 Financial Summary.xlsx", { strict: false })
    ).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 3. h — goes back up to root; root items are visible again
  // ---------------------------------------------------------------------------
  test("h goes back up to root listing", async ({ terminal }) => {
    await expect(terminal.getByText("Q2 Reports", { strict: false })).toBeVisible();

    terminal.write("j"); // highlight folder
    terminal.write("l"); // drill in

    await expect(
      terminal.getByText("Q2 2026 Financial Summary.xlsx", { strict: false })
    ).toBeVisible();

    terminal.write("h"); // go up

    // Root items must be visible again.
    await expect(terminal.getByText("Q2 Reports", { strict: false })).toBeVisible();
    await expect(
      terminal.getByText("Architecture Decision Record.docx", { strict: false })
    ).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 4. / — opens search input; Esc cancels and restores the listing
  // ---------------------------------------------------------------------------
  test("/ opens search and Esc cancels", async ({ terminal }) => {
    await expect(terminal.getByText("Q2 Reports", { strict: false })).toBeVisible();

    terminal.write("/");
    // SearchModal hint text confirms the modal is open.
    await expect(
      terminal.getByText("Enter to search", { strict: false })
    ).toBeVisible();

    terminal.keyEscape();
    // Listing is restored.
    await expect(terminal.getByText("Q2 Reports", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 5. Esc — opens overlay menu; Resume is visible; second Esc closes
  // ---------------------------------------------------------------------------
  test("Esc opens the menu and shows Resume", async ({ terminal }) => {
    await expect(terminal.getByText("Q2 Reports", { strict: false })).toBeVisible();

    terminal.keyEscape();
    await expect(terminal.getByText("Resume")).toBeVisible();
    await expect(terminal.getByText("Quit", { strict: false })).toBeVisible();

    terminal.keyEscape();
    // Menu closed; listing is back.
    await expect(terminal.getByText("Q2 Reports", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 6. q — quits the drive screen (listing no longer visible)
  // ---------------------------------------------------------------------------
  test("q quits", async ({ terminal }) => {
    await expect(terminal.getByText("Q2 Reports", { strict: false })).toBeVisible();
    terminal.write("q");
    await expect(
      terminal.getByText("Q2 Reports", { strict: false })
    ).not.toBeVisible();
  });
});
