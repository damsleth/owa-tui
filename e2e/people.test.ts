// End-to-end coverage of the People tool user actions, driven through the
// real owa-tui binary in a pty. Deterministic data comes from
// OWA_TUI_FIXTURES (see src/owa_tui/fixtures.py) — no live auth needed.
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@microsoft/tui-test";

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), "fixtures");
const env = { ...process.env, OWA_TUI_FIXTURES: FIXTURES };
// Wide enough that a right-side detail pane does not truncate list labels.
const size = { columns: 120, rows: 40 };

test.describe("people", () => {
  test.use({ program: { file: "owa-tui", args: ["--tool", "people"] }, env, ...size });

  // -------------------------------------------------------------------------
  // 1. Render — list populates from fixture data
  // -------------------------------------------------------------------------
  test("renders the people list from fixtures", async ({ terminal }) => {
    // Names are unique across list + detail pane — no strict:false needed here.
    await expect(terminal.getByText("Alice Andersen")).toBeVisible();
    await expect(terminal.getByText("Bob Bakken")).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // 2. j then l — opens detail pane / detail screen for highlighted person
  //
  // GOTCHA: ListView starts with index=None; Enter/l is a no-op until a row
  // is highlighted. Press "j" first, THEN "l" (not submit() — screen-level
  // binding is more reliably triggered by terminal.write).
  // -------------------------------------------------------------------------
  test("j then l opens the detail view", async ({ terminal }) => {
    await expect(terminal.getByText("Alice Andersen")).toBeVisible();
    terminal.write("j"); // highlight first row
    terminal.write("l"); // open detail
    // "Alice Andersen" may now appear in both list and detail; use strict:false.
    await expect(terminal.getByText("Alice Andersen", { strict: false })).toBeVisible();
    // Assert a detail-only field (email or job title) to confirm we're in detail.
    await expect(terminal.getByText("alice.andersen@example.com", { strict: false })).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // 3. h — closes detail, returns to list
  // -------------------------------------------------------------------------
  test("h closes detail and returns to list", async ({ terminal }) => {
    await expect(terminal.getByText("Alice Andersen")).toBeVisible();
    terminal.write("j");
    terminal.write("l");
    await expect(terminal.getByText("alice.andersen@example.com", { strict: false })).toBeVisible();
    terminal.write("h"); // back to list
    await expect(terminal.getByText("Bob Bakken")).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // 4. / — opens search input; Esc cancels and restores list
  // -------------------------------------------------------------------------
  test("/ opens search and Esc cancels", async ({ terminal }) => {
    await expect(terminal.getByText("Alice Andersen")).toBeVisible();
    terminal.write("/");
    // Assert the search prompt hint text — mirrors the SearchModal render.
    await expect(terminal.getByText("Enter to search", { strict: false })).toBeVisible();
    terminal.keyEscape();
    await expect(terminal.getByText("Alice Andersen")).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // 5. Esc — opens the overlay menu (Resume + Quit visible); second Esc closes
  // -------------------------------------------------------------------------
  test("Esc opens the menu and shows Resume", async ({ terminal }) => {
    await expect(terminal.getByText("Alice Andersen")).toBeVisible();
    terminal.keyEscape();
    await expect(terminal.getByText("Resume")).toBeVisible();
    await expect(terminal.getByText("Quit", { strict: false })).toBeVisible();
    terminal.keyEscape();
    await expect(terminal.getByText("Alice Andersen")).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // 6. q — quits the people screen (list no longer visible)
  // -------------------------------------------------------------------------
  test("q quits", async ({ terminal }) => {
    await expect(terminal.getByText("Alice Andersen")).toBeVisible();
    terminal.write("q");
    await expect(terminal.getByText("Alice Andersen")).not.toBeVisible();
  });

  // -------------------------------------------------------------------------
  // 7. j — moves the cursor down one row
  //
  // People sort name_asc: Alice (0), Bob (1), Carol (2). Press j twice to land
  // on Bob, open detail, and confirm it is Bob's detail (his email) — proving
  // the cursor advanced past row 0.
  // -------------------------------------------------------------------------
  test("j moves the cursor down", async ({ terminal }) => {
    await expect(terminal.getByText("Alice Andersen")).toBeVisible();
    terminal.write("j"); // highlight row 0 (Alice)
    terminal.write("j"); // move to row 1 (Bob)
    terminal.write("l"); // open detail for row 1
    await expect(terminal.getByText("bob.bakken@example.com", { strict: false })).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // 8. k — moves the cursor back up after moving down
  //
  // j,j down to Bob then k up to Alice, open detail, confirm Alice's email —
  // proving k moved the cursor up.
  // -------------------------------------------------------------------------
  test("k moves the cursor up", async ({ terminal }) => {
    await expect(terminal.getByText("Alice Andersen")).toBeVisible();
    terminal.write("j"); // row 0 (Alice)
    terminal.write("j"); // row 1 (Bob)
    terminal.write("k"); // back to row 0 (Alice)
    terminal.write("l"); // open detail for row 0
    await expect(terminal.getByText("alice.andersen@example.com", { strict: false })).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // 9. G then g — jump to bottom then top of the list
  //
  // G lands on Carol (last); open detail to confirm. Then g returns to Alice
  // (first); open detail to confirm — proving both jumps moved the cursor.
  // -------------------------------------------------------------------------
  test("G jumps to bottom and g back to top", async ({ terminal }) => {
    await expect(terminal.getByText("Alice Andersen")).toBeVisible();
    terminal.write("j"); // highlight a row first
    terminal.write("G"); // jump to last row (Carol)
    terminal.write("l"); // open detail
    await expect(terminal.getByText("carol.christensen@example.com", { strict: false })).toBeVisible();
    terminal.write("h"); // back to list
    terminal.write("g"); // jump to first row (Alice)
    terminal.write("l"); // open detail
    await expect(terminal.getByText("alice.andersen@example.com", { strict: false })).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // 10. tab — focus_pane toggle does not crash; list still renders
  //
  // Detail pane may be 'off' (action returns early) or visible (focus toggles);
  // either way the list must remain visible after pressing tab.
  // -------------------------------------------------------------------------
  test("tab focuses the pane without crashing", async ({ terminal }) => {
    await expect(terminal.getByText("Alice Andersen")).toBeVisible();
    terminal.write("j"); // highlight a row
    terminal.write("\t"); // focus_pane
    await expect(terminal.getByText("Alice Andersen", { strict: false })).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // 11. r — refresh re-fetches from fixtures; list still renders
  // -------------------------------------------------------------------------
  test("r refresh re-renders the list", async ({ terminal }) => {
    await expect(terminal.getByText("Alice Andersen")).toBeVisible();
    terminal.write("r"); // refresh
    await expect(terminal.getByText("Alice Andersen")).toBeVisible();
    await expect(terminal.getByText("Bob Bakken")).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // 12. / — search that returns results filters the list to matches
  //
  // NB: people search re-fetches via fixtures (no client-side filter), so the
  // search box hint confirms the modal; typing a name + Enter keeps the list
  // populated. Assert the searched-for person stays visible.
  // -------------------------------------------------------------------------
  test("/ search returns results", async ({ terminal }) => {
    await expect(terminal.getByText("Alice Andersen")).toBeVisible();
    terminal.write("/");
    await expect(terminal.getByText("Enter to search", { strict: false })).toBeVisible();
    terminal.write("Bob"); // search term
    terminal.submit(); // Enter -> apply search
    // Match stays visible after the search round-trip.
    await expect(terminal.getByText("Bob Bakken", { strict: false })).toBeVisible();
  });
});
