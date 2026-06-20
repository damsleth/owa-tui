// End-to-end coverage of the ADO tool user actions, driven through the
// real owa-tui binary in a pty. Deterministic data comes from
// OWA_TUI_FIXTURES (see src/owa_tui/fixtures.py) — no live auth needed.
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@microsoft/tui-test";

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), "fixtures");
const env = { ...process.env, OWA_TUI_FIXTURES: FIXTURES };
// Wide enough that a right-side detail pane does not truncate work item titles.
const size = { columns: 120, rows: 40 };

test.describe("ado", () => {
  test.use({ program: { file: "owa-tui", args: ["--tool", "ado"] }, env, ...size });

  // ---------------------------------------------------------------------------
  // 1. Render — list populates from fixture data
  // ---------------------------------------------------------------------------
  test("renders the ADO work item list from fixtures", async ({ terminal }) => {
    await expect(terminal.getByText("Migrate auth flow to MSAL v3")).toBeVisible();
    await expect(terminal.getByText("Add integration tests for ADO fetch layer")).toBeVisible();
    await expect(terminal.getByText("Document owa-tui ADO screen keybindings")).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 2. j then l — opens detail view for the highlighted work item
  //
  // GOTCHA: ListView starts with index=None; Enter/l is a no-op until a row
  // is highlighted. Press "j" first, THEN write("l") — not submit().
  // GOTCHA: title may appear in both list and detail pane — use strict:false.
  // ---------------------------------------------------------------------------
  test("j then l opens the detail view", async ({ terminal }) => {
    await expect(terminal.getByText("Migrate auth flow to MSAL v3")).toBeVisible();
    terminal.write("j"); // highlight first row
    terminal.write("l"); // open detail
    // Title may appear in both list and detail panes — strict:false required.
    await expect(
      terminal.getByText("Migrate auth flow to MSAL v3", { strict: false })
    ).toBeVisible();
    // Assert a detail-only field to confirm we are in detail view.
    // normalize_work_item maps WorkItemType -> "User Story" in the detail pane.
    await expect(terminal.getByText("User Story", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 3. h — closes detail and returns to list
  // ---------------------------------------------------------------------------
  test("h closes detail and returns to list", async ({ terminal }) => {
    await expect(terminal.getByText("Migrate auth flow to MSAL v3")).toBeVisible();
    terminal.write("j");
    terminal.write("l");
    await expect(
      terminal.getByText("Migrate auth flow to MSAL v3", { strict: false })
    ).toBeVisible();
    terminal.write("h"); // back to list
    await expect(terminal.getByText("Add integration tests for ADO fetch layer")).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 4. / — opens search input; Esc cancels and restores list
  // ---------------------------------------------------------------------------
  test("/ opens search and Esc cancels", async ({ terminal }) => {
    await expect(terminal.getByText("Migrate auth flow to MSAL v3")).toBeVisible();
    terminal.write("/");
    // SearchModal hint text confirms the modal is open.
    await expect(terminal.getByText("Enter to search", { strict: false })).toBeVisible();
    terminal.keyEscape();
    await expect(terminal.getByText("Migrate auth flow to MSAL v3")).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 5. Esc — opens overlay menu; Resume and Quit are visible; second Esc closes
  // ---------------------------------------------------------------------------
  test("Esc opens the menu and shows Resume", async ({ terminal }) => {
    await expect(terminal.getByText("Migrate auth flow to MSAL v3")).toBeVisible();
    terminal.keyEscape();
    await expect(terminal.getByText("Resume")).toBeVisible();
    await expect(terminal.getByText("Quit", { strict: false })).toBeVisible();
    terminal.keyEscape();
    await expect(terminal.getByText("Migrate auth flow to MSAL v3")).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 4b. / — search that returns results filters the list to matches
  // ---------------------------------------------------------------------------
  test("/ search filters list to matching work items", async ({ terminal }) => {
    await expect(terminal.getByText("Migrate auth flow to MSAL v3")).toBeVisible();
    terminal.write("/");
    await expect(terminal.getByText("Enter to search", { strict: false })).toBeVisible();
    terminal.write("Migrate");
    terminal.submit(); // Enter -> apply search
    // Matching work item stays visible; a non-matching one is filtered out.
    await expect(terminal.getByText("Migrate auth flow to MSAL v3")).toBeVisible();
    await expect(
      terminal.getByText("Add integration tests for ADO fetch layer")
    ).not.toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 7. j — moves the highlight down to the next work item
  //
  // Drive j twice (row 0 -> row 1), open detail, and confirm it is the second
  // item's detail (State "New", unique to row 1) — proves j moved the cursor.
  // ---------------------------------------------------------------------------
  test("j moves the highlight down", async ({ terminal }) => {
    await expect(terminal.getByText("Migrate auth flow to MSAL v3")).toBeVisible();
    terminal.write("j"); // row 0
    terminal.write("j"); // row 1
    terminal.write("l"); // open detail for row 1
    await expect(
      terminal.getByText("Add integration tests for ADO fetch layer", { strict: false })
    ).toBeVisible();
    // State "New" is unique to the second work item's detail.
    await expect(terminal.getByText("New", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 8. k — moves the highlight back up after moving down
  //
  // Drive j,j down then k up to row 0, open detail, confirm it is the first
  // item's detail (Type "User Story") — proves k moved the cursor up.
  // ---------------------------------------------------------------------------
  test("k moves the highlight up", async ({ terminal }) => {
    await expect(terminal.getByText("Migrate auth flow to MSAL v3")).toBeVisible();
    terminal.write("j"); // row 0
    terminal.write("j"); // row 1
    terminal.write("k"); // back to row 0
    terminal.write("l"); // open detail for row 0
    await expect(
      terminal.getByText("Migrate auth flow to MSAL v3", { strict: false })
    ).toBeVisible();
    await expect(terminal.getByText("User Story", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 9. G / g — jump to bottom then top of the list
  //
  // G -> last row; open detail confirms the last item (State "Resolved",
  // unique to row 2). g -> first row; open detail confirms "User Story".
  // ---------------------------------------------------------------------------
  test("G jumps to bottom and g jumps to top", async ({ terminal }) => {
    await expect(terminal.getByText("Migrate auth flow to MSAL v3")).toBeVisible();
    terminal.write("j"); // highlight a row so the cursor exists
    terminal.write("G"); // jump to last row
    terminal.write("l"); // open detail for last item
    await expect(
      terminal.getByText("Document owa-tui ADO screen keybindings", { strict: false })
    ).toBeVisible();
    await expect(terminal.getByText("Resolved", { strict: false })).toBeVisible();
    terminal.write("h"); // back to list
    terminal.write("g"); // jump to first row
    terminal.write("l"); // open detail for first item
    await expect(terminal.getByText("User Story", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 10. r — refresh re-fetches; list still renders from fixtures afterwards
  // ---------------------------------------------------------------------------
  test("r refreshes and the list still renders", async ({ terminal }) => {
    await expect(terminal.getByText("Migrate auth flow to MSAL v3")).toBeVisible();
    terminal.write("r"); // refresh -> re-runs fetch_items against fixtures
    await expect(terminal.getByText("Migrate auth flow to MSAL v3")).toBeVisible();
    await expect(terminal.getByText("Add integration tests for ADO fetch layer")).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 11. tab — toggles focus between list and detail pane (no crash)
  //
  // focus_pane only moves focus; there is no distinct visible text to assert,
  // so confirm the list is still rendered after the toggle.
  // ---------------------------------------------------------------------------
  test("tab toggles pane focus without crashing", async ({ terminal }) => {
    await expect(terminal.getByText("Migrate auth flow to MSAL v3")).toBeVisible();
    terminal.write("j"); // highlight a row (populates the detail preview)
    terminal.write("\t"); // tab -> focus detail pane
    terminal.write("\t"); // tab -> focus list again
    await expect(
      terminal.getByText("Migrate auth flow to MSAL v3", { strict: false })
    ).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 6. q — quits the ADO screen (list no longer visible)
  // ---------------------------------------------------------------------------
  test("q quits", async ({ terminal }) => {
    await expect(terminal.getByText("Migrate auth flow to MSAL v3")).toBeVisible();
    terminal.write("q");
    await expect(terminal.getByText("Migrate auth flow to MSAL v3")).not.toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 12. d — page_down on the short fixture list scrolls but is a visual no-op;
  // assert the list still renders (no-crash check).
  // ---------------------------------------------------------------------------
  test("d page-down does not crash the list", async ({ terminal }) => {
    await expect(terminal.getByText("Migrate auth flow to MSAL v3")).toBeVisible();
    terminal.write("j"); // highlight a row first
    terminal.write("d"); // page_down
    await expect(
      terminal.getByText("Migrate auth flow to MSAL v3", { strict: false })
    ).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 13. u — page_up on the short fixture list scrolls but is a visual no-op;
  // assert the list still renders (no-crash check).
  // ---------------------------------------------------------------------------
  test("u page-up does not crash the list", async ({ terminal }) => {
    await expect(terminal.getByText("Migrate auth flow to MSAL v3")).toBeVisible();
    terminal.write("j"); // highlight a row first
    terminal.write("u"); // page_up
    await expect(
      terminal.getByText("Migrate auth flow to MSAL v3", { strict: false })
    ).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 14. o — open_browser.  AdoScreen.open_browser_for returns item["url"] (each
  // fixture work item has one), so "o" genuinely launches a browser.  That is
  // not observable in a headless pty; assert only that the screen survives.
  // ---------------------------------------------------------------------------
  test("o (open browser) does not crash the screen", async ({ terminal }) => {
    await expect(terminal.getByText("Migrate auth flow to MSAL v3")).toBeVisible();
    terminal.write("j"); // highlight a row so an item is selected
    terminal.write("o"); // open_browser (item has a url)
    await expect(
      terminal.getByText("Migrate auth flow to MSAL v3", { strict: false })
    ).toBeVisible();
  });
});
