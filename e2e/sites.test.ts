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

  // ---------------------------------------------------------------------------
  // 7. j / k — move the cursor between rows.
  //
  // Proven via the auto-preview detail pane (detail_pane_mode defaults to
  // "right").  We move at the *item* level (inside Project Tracker) because an
  // item's detail shows its "FileLeafRef:" filename — a string that only
  // appears in the detail pane, never in a list row.
  // ---------------------------------------------------------------------------
  test("j and k move the cursor between rows", async ({ terminal }) => {
    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();

    terminal.write("j"); // highlight the first list
    terminal.write("l"); // drill into Project Tracker

    await expect(
      terminal.getByText("Crayon Norway — Q3 delivery roadmap", { strict: false })
    ).toBeVisible();

    terminal.write("j"); // highlight item 1 → detail previews Q3Roadmap.docx
    await expect(terminal.getByText("Q3Roadmap.docx", { strict: false })).toBeVisible();

    terminal.write("j"); // move down to item 2 → detail previews CloudGov.docx
    await expect(terminal.getByText("CloudGov.docx", { strict: false })).toBeVisible();

    terminal.write("k"); // move back up to item 1
    await expect(terminal.getByText("Q3Roadmap.docx", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 8. G / g — jump to bottom / top, proven via the same item-detail preview.
  // ---------------------------------------------------------------------------
  test("G jumps to bottom and g jumps to top", async ({ terminal }) => {
    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();

    terminal.write("j"); // highlight first list
    terminal.write("l"); // drill into Project Tracker

    await expect(
      terminal.getByText("Crayon Norway — Q3 delivery roadmap", { strict: false })
    ).toBeVisible();

    terminal.write("G"); // jump to last item → Onboarding.docx
    await expect(terminal.getByText("Onboarding.docx", { strict: false })).toBeVisible();

    terminal.write("g"); // jump back to first item → Q3Roadmap.docx
    await expect(terminal.getByText("Q3Roadmap.docx", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 9. r — refresh re-fetches the current node; the root lists still render.
  // ---------------------------------------------------------------------------
  test("r refresh keeps the listing rendered", async ({ terminal }) => {
    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();

    terminal.write("r");

    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();
    await expect(terminal.getByText("Risk Register", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 10. / search returning results — type a list title, submit, listing filters.
  //
  // load_node applies a case-insensitive substring filter on the list title.
  // Searching "Risk" keeps "Risk Register" and drops "Project Tracker".
  // ---------------------------------------------------------------------------
  test("/ search filters the listing to matching lists", async ({ terminal }) => {
    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();

    terminal.write("/");
    await expect(
      terminal.getByText("Enter to search", { strict: false })
    ).toBeVisible();

    terminal.write("Risk");
    terminal.submit(); // Enter — run the search

    await expect(terminal.getByText("Risk Register", { strict: false })).toBeVisible();
    await expect(
      terminal.getByText("Project Tracker", { strict: false })
    ).not.toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 11. Deeper navigation: drill into a list, then open an item leaf.
  //
  // Lists drill in (push a node); items are leaves and open the detail pane.
  // After opening an item with "l", its detail renders "Kind:      item".
  // ---------------------------------------------------------------------------
  test("drill into list then open an item leaf shows its detail", async ({ terminal }) => {
    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();

    terminal.write("j"); // highlight first list
    terminal.write("l"); // drill into Project Tracker

    await expect(
      terminal.getByText("Crayon Norway — Q3 delivery roadmap", { strict: false })
    ).toBeVisible();

    terminal.write("j"); // highlight first item
    terminal.write("l"); // open the item leaf (detail mode)

    // Detail pane renders the item metadata — "Kind:" appears only in detail.
    await expect(terminal.getByText("Kind:", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 12. o — open in browser.  Effect (spawning a browser) is not observable in
  // a headless pty; assert only that the screen does not crash and the listing
  // stays rendered.
  // ---------------------------------------------------------------------------
  test("o (open browser) does not crash the screen", async ({ terminal }) => {
    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();

    terminal.write("j"); // need a selected item
    terminal.write("o");

    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 13. d — page_down on the short fixture listing scrolls but is a visual
  // no-op; assert the listing still renders (no-crash check).
  // ---------------------------------------------------------------------------
  test("d page-down does not crash the listing", async ({ terminal }) => {
    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();
    terminal.write("j"); // highlight a row first
    terminal.write("d"); // page_down
    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 14. u — page_up on the short fixture listing scrolls but is a visual no-op;
  // assert the listing still renders (no-crash check).
  // ---------------------------------------------------------------------------
  test("u page-up does not crash the listing", async ({ terminal }) => {
    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();
    terminal.write("j"); // highlight a row first
    terminal.write("u"); // page_up
    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 15. tab — focus_pane toggles focus between list and detail pane.  No
  // distinct visible text; assert the listing still renders (no-crash check).
  // ---------------------------------------------------------------------------
  test("tab toggles pane focus without crashing", async ({ terminal }) => {
    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();
    terminal.write("j"); // highlight a row (populates the detail preview)
    terminal.write("\t"); // tab -> focus detail pane
    terminal.write("\t"); // tab -> focus list again
    await expect(terminal.getByText("Project Tracker", { strict: false })).toBeVisible();
  });
});
