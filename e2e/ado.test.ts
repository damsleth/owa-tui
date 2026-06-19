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
  // 6. q — quits the ADO screen (list no longer visible)
  // ---------------------------------------------------------------------------
  test("q quits", async ({ terminal }) => {
    await expect(terminal.getByText("Migrate auth flow to MSAL v3")).toBeVisible();
    terminal.write("q");
    await expect(terminal.getByText("Migrate auth flow to MSAL v3")).not.toBeVisible();
  });
});
