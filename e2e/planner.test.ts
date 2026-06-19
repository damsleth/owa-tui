// End-to-end coverage of the Planner tool user actions, driven through the
// real owa-tui binary in a pty. Deterministic data comes from
// OWA_TUI_FIXTURES (see src/owa_tui/fixtures.py) — no live auth needed.
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@microsoft/tui-test";

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), "fixtures");
const env = { ...process.env, OWA_TUI_FIXTURES: FIXTURES };
// Wide enough that a right-side detail pane does not truncate task titles.
const size = { columns: 120, rows: 40 };

test.describe("planner", () => {
  test.use({ program: { file: "owa-tui", args: ["--tool", "planner"] }, env, ...size });

  // ---------------------------------------------------------------------------
  // 1. Render — list populates from fixture data
  // ---------------------------------------------------------------------------
  test("renders the planner task list from fixtures", async ({ terminal }) => {
    await expect(terminal.getByText("Define Q3 OKRs")).toBeVisible();
    await expect(terminal.getByText("Review architecture proposal")).toBeVisible();
    await expect(terminal.getByText("Update onboarding runbook")).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 2. j then l — opens detail view for the highlighted task
  //
  // GOTCHA: ListView starts with index=None; Enter/l is a no-op until a row
  // is highlighted. Press "j" first, THEN write("l") — not submit().
  // GOTCHA: task title may appear in both list and detail pane — use strict:false.
  // ---------------------------------------------------------------------------
  test("j then l opens the detail view", async ({ terminal }) => {
    await expect(terminal.getByText("Define Q3 OKRs")).toBeVisible();
    terminal.write("j"); // highlight first row
    terminal.write("l"); // open detail
    // Title may appear in both panes — strict:false required.
    await expect(
      terminal.getByText("Define Q3 OKRs", { strict: false })
    ).toBeVisible();
    // Assert a detail-only field to confirm we are in detail view.
    // normalize_task maps priority 1 -> priorityLabel "urgent"
    await expect(terminal.getByText("urgent", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 3. h — closes detail and returns to list
  // ---------------------------------------------------------------------------
  test("h closes detail and returns to list", async ({ terminal }) => {
    await expect(terminal.getByText("Define Q3 OKRs")).toBeVisible();
    terminal.write("j");
    terminal.write("l");
    await expect(
      terminal.getByText("Define Q3 OKRs", { strict: false })
    ).toBeVisible();
    terminal.write("h"); // back to list
    await expect(terminal.getByText("Review architecture proposal")).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 4. / — opens search input; Esc cancels and restores list
  // ---------------------------------------------------------------------------
  test("/ opens search and Esc cancels", async ({ terminal }) => {
    await expect(terminal.getByText("Define Q3 OKRs")).toBeVisible();
    terminal.write("/");
    // SearchModal hint text confirms the modal is open.
    await expect(terminal.getByText("Enter to search", { strict: false })).toBeVisible();
    terminal.keyEscape();
    await expect(terminal.getByText("Define Q3 OKRs")).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 5. Esc — opens overlay menu; Resume and Quit are visible; second Esc closes
  // ---------------------------------------------------------------------------
  test("Esc opens the menu and shows Resume", async ({ terminal }) => {
    await expect(terminal.getByText("Define Q3 OKRs")).toBeVisible();
    terminal.keyEscape();
    await expect(terminal.getByText("Resume")).toBeVisible();
    await expect(terminal.getByText("Quit", { strict: false })).toBeVisible();
    terminal.keyEscape();
    await expect(terminal.getByText("Define Q3 OKRs")).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 6. q — quits the planner screen (list no longer visible)
  // ---------------------------------------------------------------------------
  test("q quits", async ({ terminal }) => {
    await expect(terminal.getByText("Define Q3 OKRs")).toBeVisible();
    terminal.write("q");
    await expect(terminal.getByText("Define Q3 OKRs")).not.toBeVisible();
  });
});
