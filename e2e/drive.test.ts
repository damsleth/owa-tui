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

  // ---------------------------------------------------------------------------
  // 7. j / k — move the cursor between rows.
  //
  // Movement is proven via the auto-preview detail pane (detail_pane_mode
  // defaults to "right"): on_list_view_highlighted previews the highlighted
  // item.  Row 1 = "Q2 Reports" folder (detail shows "Children:"), row 2 =
  // the .docx file (detail shows the formatted size "180.0 KB", a string that
  // only appears in the file detail, never in a row).
  // ---------------------------------------------------------------------------
  test("j and k move the cursor between rows", async ({ terminal }) => {
    await expect(terminal.getByText("Q2 Reports", { strict: false })).toBeVisible();

    terminal.write("j"); // highlight row 1 (folder)
    terminal.write("j"); // move down to row 2 (the .docx file)

    // File detail preview — size string is unique to the file detail pane.
    await expect(terminal.getByText("180.0 KB", { strict: false })).toBeVisible();

    terminal.write("k"); // move back up to row 1 (the folder)

    // Folder detail preview — "Children:" only appears for the folder.
    await expect(terminal.getByText("Children:", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 8. G / g — jump to bottom / top of the listing.
  //
  // Proven via the same auto-preview pane: G lands on the last row (file →
  // "180.0 KB"), g returns to the first row (folder → "Children:").
  // ---------------------------------------------------------------------------
  test("G jumps to bottom and g jumps to top", async ({ terminal }) => {
    await expect(terminal.getByText("Q2 Reports", { strict: false })).toBeVisible();

    terminal.write("G"); // jump to last row (the file)
    await expect(terminal.getByText("180.0 KB", { strict: false })).toBeVisible();

    terminal.write("g"); // jump to first row (the folder)
    await expect(terminal.getByText("Children:", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 9. r — refresh re-fetches the current node; the tree still renders.
  // ---------------------------------------------------------------------------
  test("r refresh keeps the listing rendered", async ({ terminal }) => {
    await expect(terminal.getByText("Q2 Reports", { strict: false })).toBeVisible();

    terminal.write("r");

    // After refresh the same root items must still be visible.
    await expect(terminal.getByText("Q2 Reports", { strict: false })).toBeVisible();
    await expect(
      terminal.getByText("Architecture Decision Record.docx", { strict: false })
    ).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 10. / search returning results — type a name, submit, listing is filtered.
  //
  // load_node applies a case-insensitive substring filter on the item name.
  // Searching "Architecture" keeps the .docx and drops the "Q2 Reports" folder.
  // ---------------------------------------------------------------------------
  test("/ search filters the listing to matching items", async ({ terminal }) => {
    await expect(terminal.getByText("Q2 Reports", { strict: false })).toBeVisible();

    terminal.write("/");
    await expect(
      terminal.getByText("Enter to search", { strict: false })
    ).toBeVisible();

    terminal.write("Architecture");
    terminal.submit(); // Enter — run the search

    // Match stays visible; the non-matching folder is filtered out.
    await expect(
      terminal.getByText("Architecture Decision Record.docx", { strict: false })
    ).toBeVisible();
    await expect(terminal.getByText("Q2 Reports", { strict: false })).not.toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 11. Deeper navigation: drill into the folder, then open a file leaf.
  //
  // Folders drill in (push a node); files are leaves and open the detail pane.
  // After drilling into "Q2 Reports", opening a file with "l" shows its detail
  // (MIME line is unique to the detail pane).
  // ---------------------------------------------------------------------------
  test("drill into folder then open a file leaf shows its detail", async ({ terminal }) => {
    await expect(terminal.getByText("Q2 Reports", { strict: false })).toBeVisible();

    terminal.write("j"); // highlight folder
    terminal.write("l"); // drill into Q2 Reports

    await expect(
      terminal.getByText("Q2 2026 Financial Summary.xlsx", { strict: false })
    ).toBeVisible();

    terminal.write("j"); // highlight first file
    terminal.write("l"); // open the file leaf (detail mode)

    // Detail pane renders the file metadata — "MIME:" only appears in detail.
    await expect(terminal.getByText("MIME:", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 12. o — open in browser.  Effect (spawning a browser) is not observable in
  // a headless pty; assert only that the screen does not crash and the listing
  // stays rendered.
  // ---------------------------------------------------------------------------
  test("o (open browser) does not crash the screen", async ({ terminal }) => {
    await expect(terminal.getByText("Q2 Reports", { strict: false })).toBeVisible();

    terminal.write("j"); // need a selected item
    terminal.write("o");

    // Stable element still present — no crash.
    await expect(terminal.getByText("Q2 Reports", { strict: false })).toBeVisible();
  });
});
