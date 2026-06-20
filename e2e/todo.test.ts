// End-to-end coverage of the Todo/Tasks tool user actions, driven through the
// real owa-tui binary in a pty. Deterministic data comes from
// OWA_TUI_FIXTURES (see src/owa_tui/fixtures.py) — no live auth needed.
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@microsoft/tui-test";

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), "fixtures");
const env = { ...process.env, OWA_TUI_FIXTURES: FIXTURES };
// Wide enough that a right-side detail pane does not truncate task titles.
const size = { columns: 120, rows: 40 };

test.describe("todo", () => {
  test.use({ program: { file: "owa-tui", args: ["--tool", "todo"] }, env, ...size });

  // ---------------------------------------------------------------------------
  // 1. Render — list populates from fixture data
  // ---------------------------------------------------------------------------
  test("renders the task list from fixtures", async ({ terminal }) => {
    await expect(terminal.getByText("Review quarterly report")).toBeVisible();
    await expect(terminal.getByText("Send onboarding docs to new hire")).toBeVisible();
    await expect(terminal.getByText("Book team offsite venue")).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 2. j then l — opens detail view for the highlighted task
  //
  // GOTCHA: ListView starts with index=None; Enter/l is a no-op until a row
  // is highlighted. Press "j" first, THEN "l" (terminal.write, not submit()).
  // GOTCHA: task title may appear in both list and detail pane — use strict:false.
  // ---------------------------------------------------------------------------
  test("j then l opens the detail view", async ({ terminal }) => {
    await expect(terminal.getByText("Review quarterly report")).toBeVisible();
    terminal.write("j"); // highlight first row
    terminal.write("l"); // open detail
    // Title may now appear in both list and detail pane — strict:false required.
    await expect(
      terminal.getByText("Review quarterly report", { strict: false })
    ).toBeVisible();
    // Assert a detail-only field to confirm we are actually in detail view.
    await expect(terminal.getByText("High", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 3. h — closes detail and returns to list
  // ---------------------------------------------------------------------------
  test("h closes detail and returns to list", async ({ terminal }) => {
    await expect(terminal.getByText("Review quarterly report")).toBeVisible();
    terminal.write("j");
    terminal.write("l");
    await expect(
      terminal.getByText("Review quarterly report", { strict: false })
    ).toBeVisible();
    terminal.write("h"); // back to list
    await expect(terminal.getByText("Send onboarding docs to new hire")).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 4. / — opens search input; Esc cancels and restores list
  // ---------------------------------------------------------------------------
  test("/ opens search and Esc cancels", async ({ terminal }) => {
    await expect(terminal.getByText("Review quarterly report")).toBeVisible();
    terminal.write("/");
    // SearchModal hint text confirms the modal is open.
    await expect(terminal.getByText("Enter to search", { strict: false })).toBeVisible();
    terminal.keyEscape();
    await expect(terminal.getByText("Review quarterly report")).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 4b. / — search that returns results filters the list to matches
  // ---------------------------------------------------------------------------
  test("/ search filters list to matching tasks", async ({ terminal }) => {
    await expect(terminal.getByText("Send onboarding docs to new hire")).toBeVisible();
    terminal.write("/");
    await expect(terminal.getByText("Enter to search", { strict: false })).toBeVisible();
    terminal.write("Review");
    terminal.submit(); // Enter -> apply search
    // Matching task stays visible; a non-matching one is filtered out.
    await expect(terminal.getByText("Review quarterly report")).toBeVisible();
    await expect(
      terminal.getByText("Send onboarding docs to new hire")
    ).not.toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 4c. k / up — moves the highlight back up after moving down
  //
  // Drive j,j down then k up to row 0, open detail, and confirm it is the
  // first task's detail (High importance) — proves k moved the cursor up.
  // ---------------------------------------------------------------------------
  test("k moves the highlight up", async ({ terminal }) => {
    await expect(terminal.getByText("Review quarterly report")).toBeVisible();
    terminal.write("j"); // row 0
    terminal.write("j"); // row 1
    terminal.write("k"); // back to row 0
    terminal.write("l"); // open detail for row 0
    await expect(
      terminal.getByText("Review quarterly report", { strict: false })
    ).toBeVisible();
    await expect(terminal.getByText("High", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 5. Complete-toggle key — no-op in fixture mode; list stays visible
  //
  // TodoScreen binds "c" to toggle Status between NotStarted and Completed.
  // In fixture mode _patch_complete returns early so the list must still be
  // present after the key press.
  // ---------------------------------------------------------------------------
  test("complete-toggle key does not crash in fixture mode", async ({ terminal }) => {
    await expect(terminal.getByText("Review quarterly report")).toBeVisible();
    terminal.write("j"); // highlight first row
    terminal.write("c"); // complete-toggle
    // List must still be rendered — mutation was a no-op.
    await expect(
      terminal.getByText("Review quarterly report", { strict: false })
    ).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 6. Esc — opens overlay menu; Resume and Quit are visible; second Esc closes
  // ---------------------------------------------------------------------------
  test("Esc opens the menu and shows Resume", async ({ terminal }) => {
    await expect(terminal.getByText("Review quarterly report")).toBeVisible();
    terminal.keyEscape();
    await expect(terminal.getByText("Resume")).toBeVisible();
    await expect(terminal.getByText("Quit", { strict: false })).toBeVisible();
    terminal.keyEscape();
    await expect(terminal.getByText("Review quarterly report")).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 7. q — quits the todo screen (list no longer visible)
  // ---------------------------------------------------------------------------
  test("q quits", async ({ terminal }) => {
    await expect(terminal.getByText("Review quarterly report")).toBeVisible();
    terminal.write("q");
    await expect(terminal.getByText("Review quarterly report")).not.toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 8. j — moves the highlight down one row
  //
  // Fixture order: Review quarterly report (0, High), Send onboarding docs
  // (1, Normal), Book team offsite (2, Low). Press j twice to land on row 1,
  // open detail, and confirm row 1's detail (Normal importance) — proving the
  // cursor advanced past row 0.
  // ---------------------------------------------------------------------------
  test("j moves the highlight down", async ({ terminal }) => {
    await expect(terminal.getByText("Review quarterly report")).toBeVisible();
    terminal.write("j"); // row 0
    terminal.write("j"); // row 1
    terminal.write("l"); // open detail for row 1
    await expect(
      terminal.getByText("Send onboarding docs to new hire", { strict: false })
    ).toBeVisible();
    // Detail-only field confirms we are on row 1 (Normal), not row 0 (High).
    await expect(terminal.getByText("Normal", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 9. G then g — jump to bottom then back to top
  //
  // G lands on the last task (Book team offsite, Low); open detail to confirm.
  // g returns to the first task (Review quarterly report, High); open detail
  // to confirm — proving both jumps moved the cursor.
  // ---------------------------------------------------------------------------
  test("G jumps to bottom and g back to top", async ({ terminal }) => {
    await expect(terminal.getByText("Review quarterly report")).toBeVisible();
    terminal.write("j"); // highlight a row first
    terminal.write("G"); // jump to last row
    terminal.write("l"); // open detail
    await expect(
      terminal.getByText("Book team offsite venue", { strict: false })
    ).toBeVisible();
    await expect(terminal.getByText("Low", { strict: false })).toBeVisible();
    terminal.write("h"); // back to list
    terminal.write("g"); // jump to first row
    terminal.write("l"); // open detail
    await expect(
      terminal.getByText("Review quarterly report", { strict: false })
    ).toBeVisible();
    await expect(terminal.getByText("High", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 10. tab — focus_pane toggle does not crash; list still renders
  // ---------------------------------------------------------------------------
  test("tab focuses the pane without crashing", async ({ terminal }) => {
    await expect(terminal.getByText("Review quarterly report")).toBeVisible();
    terminal.write("j"); // highlight a row
    terminal.write("\t"); // focus_pane
    await expect(
      terminal.getByText("Review quarterly report", { strict: false })
    ).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 11. r — refresh re-fetches from fixtures; list still renders
  // ---------------------------------------------------------------------------
  test("r refresh re-renders the list", async ({ terminal }) => {
    await expect(terminal.getByText("Review quarterly report")).toBeVisible();
    terminal.write("r"); // refresh
    await expect(terminal.getByText("Review quarterly report")).toBeVisible();
    await expect(terminal.getByText("Book team offsite venue")).toBeVisible();
  });
});
