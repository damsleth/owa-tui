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
});
