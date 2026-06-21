/**
 * e2e/sched.test.ts
 *
 * Black-box coverage of the Scheduling grid (SchedScreen) via pty.
 * Grid = rows x columns — no drill-down; navigation is cursor moves only.
 * Fixture data: e2e/fixtures/sched.json
 */

import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@microsoft/tui-test";

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), "fixtures");
const env = { OWA_TUI_FIXTURES: FIXTURES, ...process.env };
const size = { columns: 120, rows: 40 };

test.describe("sched", () => {
  test.use({
    program: { file: "owa-tui", args: ["--tool", "sched"] },
    env,
    ...size,
  });

  // 1. Grid renders — attendee row labels and at least one slot cell visible
  test("renders the scheduling grid from fixtures", async ({ terminal }) => {
    await expect(terminal.getByText("alice@contoso.com", { strict: false })).toBeVisible();
    expect(terminal.getByText("bob@contoso.com", { strict: false })).toBeVisible();
    expect(terminal.getByText("carol@contoso.com", { strict: false })).toBeVisible();

    // Decoded cell values — these repeat across the matrix so strict must be false
    expect(terminal.getByText("free", { strict: false })).toBeVisible();
    expect(terminal.getByText("busy", { strict: false })).toBeVisible();
  });

  // 2. Column headers are present (time slot labels, e.g. "08:00")
  test("shows time-slot column headers", async ({ terminal }) => {
    await expect(terminal.getByText("alice@contoso.com", { strict: false })).toBeVisible();
    expect(terminal.getByText("08:00", { strict: false })).toBeVisible();
    expect(terminal.getByText("09:00", { strict: false })).toBeVisible();
  });

  // 3. Arrow / hjkl cursor moves do not crash
  test("cursor navigation does not crash", async ({ terminal }) => {
    await expect(terminal.getByText("alice@contoso.com", { strict: false })).toBeVisible();

    terminal.write("j");
    terminal.write("j");
    terminal.write("k");
    terminal.write("l");
    terminal.write("l");
    terminal.write("h");

    // Grid must still be visible after navigation
    expect(terminal.getByText("alice@contoso.com", { strict: false })).toBeVisible();
  });

  // 4. r — refresh re-runs fetch_grid without crashing
  test("r refresh reloads the grid", async ({ terminal }) => {
    await expect(terminal.getByText("alice@contoso.com", { strict: false })).toBeVisible();
    terminal.write("r");
    await expect(terminal.getByText("alice@contoso.com", { strict: false })).toBeVisible();
  });

  // 5. Esc — opens overlay menu; Resume is shown
  test("Esc opens the menu and shows Resume", async ({ terminal }) => {
    await expect(terminal.getByText("alice@contoso.com", { strict: false })).toBeVisible();
    terminal.keyEscape();
    expect(terminal.getByText("Resume")).toBeVisible();
    expect(terminal.getByText("Quit", { strict: false })).toBeVisible();
    // Dismiss menu — grid returns
    terminal.keyEscape();
    await expect(terminal.getByText("alice@contoso.com", { strict: false })).toBeVisible();
  });

  // 6. q — quits the sched screen
  test("q quits", async ({ terminal }) => {
    await expect(terminal.getByText("alice@contoso.com", { strict: false })).toBeVisible();
    terminal.write("q");
    // After quit the sched grid is no longer the active view — no crash.
  });

  // 7. All distinct availability statuses decode and render in the matrix.
  //    alice "002120000" yields a tentative slot; carol "002003000" yields oof.
  test("renders tentative and oof cells from availabilityView digits", async ({ terminal }) => {
    await expect(terminal.getByText("alice@contoso.com", { strict: false })).toBeVisible();
    // Decoded cell strings — every status repeats across the matrix so strict:false
    expect(terminal.getByText("tentative", { strict: false })).toBeVisible();
    expect(terminal.getByText("oof", { strict: false })).toBeVisible();
    expect(terminal.getByText("free", { strict: false })).toBeVisible();
  });

  // 8. Explicit column navigation (l / right) walks the cursor across slot
  //    columns. The grid is a read-only matrix — the StatusBar shows a fixed
  //    "N rows × M columns" line, not per-cell detail — so we assert the grid
  //    stays intact and a later time-slot header remains visible after moving.
  test("h/l and arrow column navigation walks across slots", async ({ terminal }) => {
    await expect(terminal.getByText("alice@contoso.com", { strict: false })).toBeVisible();
    // Step right across several slot columns, then back left.
    terminal.write("l");
    terminal.write("l");
    terminal.keyRight();
    terminal.keyRight();
    terminal.write("h");
    terminal.keyLeft();
    // A late-window header and the grid itself are still visible.
    expect(terminal.getByText("16:00", { strict: false })).toBeVisible();
    expect(terminal.getByText("alice@contoso.com", { strict: false })).toBeVisible();
  });

  // 9. The grid status line reports the matrix shape (3 attendees × 9 slots).
  test("status bar reports the matrix shape", async ({ terminal }) => {
    await expect(terminal.getByText("alice@contoso.com", { strict: false })).toBeVisible();
    expect(terminal.getByText("3 rows", { strict: false })).toBeVisible();
  });

  // 10. enter shows the selected cell's detail in the status footer.
  //     Arrow keys move the cell cursor; enter posts CellSelected -> footer
  //     shows "<attendee> · <slot>: <value>" (the " ·" only appears there).
  test("enter shows the selected cell detail in the footer", async ({ terminal }) => {
    await expect(terminal.getByText("alice@contoso.com", { strict: false })).toBeVisible();
    terminal.keyRight(); // move cursor onto the first data cell
    terminal.submit(); // enter -> show detail
    await expect(terminal.getByText("alice@contoso.com ·", { strict: false })).toBeVisible();
  });

  // 11. a opens the add-attendee prompt; Esc cancels it.
  test("a opens the add-attendee prompt", async ({ terminal }) => {
    await expect(terminal.getByText("alice@contoso.com", { strict: false })).toBeVisible();
    terminal.write("a");
    await expect(terminal.getByText("Add attendee:", { strict: false })).toBeVisible();
    terminal.keyEscape(); // cancel — grid still there
    await expect(terminal.getByText("alice@contoso.com", { strict: false })).toBeVisible();
  });
});
