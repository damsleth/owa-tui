// End-to-end coverage of the Sites (SharePoint Lists) tool user actions,
// driven through the real owa-tui binary in a pty.  Deterministic data comes
// from OWA_TUI_FIXTURES (see src/owa_tui/fixtures.py) — no live auth needed.
//
// FIXTURE SEAM:
//   sites.json                  root SharePoint lists payload ({"value":[...]})
//   sites_<listslug>.json       list items payload for the slugified list title
//   fallback: sites.json        used when no keyed fixture matches the list slug
//
// KEY GOTCHAS applied throughout (mirrors drive.test.ts):
//   - import { test, expect } named import (not default)
//   - test.use({ columns:120, rows:40 }) via size spread
//   - getByText is strict by default; use { strict:false } wherever text
//     appears in both breadcrumb AND list row (title, status)
//   - ListView starts index=None; press "j" BEFORE "l"/enter to drill
//   - drill into list: terminal.write("l") after "j"
//   - go up: terminal.write("h")
//   - OWA_TUI_FIXTURES must be an absolute path — derive from import.meta.url
//   - env spread: { ...process.env, OWA_TUI_FIXTURES: FIXTURES }
//   - launch args: ["--tool", "sites"]

import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@microsoft/tui-test";

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), "fixtures");
const env = { ...process.env, OWA_TUI_FIXTURES: FIXTURES };
// Wide enough that breadcrumb + title columns do not truncate.
const size = { columns: 120, rows: 40 };

test.describe("sites", () => {
  test.use({ program: { file: "owa-tui", args: ["--tool", "sites"] }, env, ...size });

  // ---------------------------------------------------------------------------
  // 1. Root listing — both lists render from sites.json
  // ---------------------------------------------------------------------------
  test("renders the root SharePoint lists from fixtures", async ({ terminal }) => {
    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();
    await expect(terminal.getByText("Risk Register", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 2. j then l — drills into a list; items from sites_Project_Tracker.json
  //
  // GOTCHA: ListView starts index=None; "l" is a no-op until "j" highlights a row.
  // GOTCHA: list title appears in both the list row AND the breadcrumb after
  //         drilling — use strict:false everywhere the title might be duplicated.
  // ---------------------------------------------------------------------------
  test("j then l drills into a list and shows its items", async ({ terminal }) => {
    // Wait for root to be ready.
    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();

    // Highlight the first row.
    terminal.write("j");
    // Drill into the list.
    terminal.write("l");

    // After drilling, the breadcrumb should contain the list title AND
    // at least one item from sites_Project_Tracker.json should be visible.
    // strict:false because "Project Tracker" now appears in breadcrumb + possibly status.
    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();
    // Item from sites_Project_Tracker.json.
    await expect(
      terminal.getByText("Crayon Norway — Q3 delivery roadmap", { strict: false })
    ).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 3. h — goes back up to root; root lists are visible again
  // ---------------------------------------------------------------------------
  test("h goes back up to root listing", async ({ terminal }) => {
    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();

    terminal.write("j"); // highlight first list
    terminal.write("l"); // drill in

    await expect(
      terminal.getByText("Crayon Norway — Q3 delivery roadmap", { strict: false })
    ).toBeVisible();

    terminal.write("h"); // go up

    // Root lists must be visible again.
    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();
    await expect(terminal.getByText("Risk Register", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 4. / — opens search input; Esc cancels and restores the listing
  // ---------------------------------------------------------------------------
  test("/ opens search and Esc cancels", async ({ terminal }) => {
    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();

    terminal.write("/");
    // SearchModal hint text confirms the modal is open.
    await expect(
      terminal.getByText("Enter to search", { strict: false })
    ).toBeVisible();

    terminal.keyEscape();
    // Listing is restored.
    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 5. Esc — opens overlay menu; Resume is visible; second Esc closes
  // ---------------------------------------------------------------------------
  test("Esc opens the menu and shows Resume", async ({ terminal }) => {
    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();

    terminal.keyEscape();
    await expect(terminal.getByText("Resume")).toBeVisible();
    await expect(terminal.getByText("Quit", { strict: false })).toBeVisible();

    terminal.keyEscape();
    // Menu closed; listing is back.
    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 6. q — quits the sites screen (listing no longer visible)
  // ---------------------------------------------------------------------------
  test("q quits", async ({ terminal }) => {
    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();
    terminal.write("q");
    await expect(
      terminal.getByText("Project Tracker", { strict: false })
    ).not.toBeVisible();
  });
});
