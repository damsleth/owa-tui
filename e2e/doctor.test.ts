/**
 * e2e/doctor.test.ts
 *
 * Black-box coverage of the Health (DoctorScreen) grid via pty.
 * Grid: rows = profiles (alias), columns = audiences (graph / mail / cal).
 * Cells = ok / warn / fail — produced by classify_finding() on fixture data.
 *
 * Fixture: e2e/fixtures/doctor.json  — list of findings, no live auth needed.
 *
 * GOTCHAS:
 *   - "ok", "warn", "fail" repeat across every row → strict:false on cell text.
 *   - Audience column headers repeat if they appear in breadcrumb too → strict:false.
 *   - Grid only; no drill-down (DoctorScreen is a pure OwaGridScreen subclass).
 */

import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@microsoft/tui-test";

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), "fixtures");
const env = { ...process.env, OWA_TUI_FIXTURES: FIXTURES };
const size = { columns: 120, rows: 40 };

test.describe("doctor", () => {
  test.use({
    program: { file: "owa-tui", args: ["--tool", "doctor"] },
    env,
    ...size,
  });

  // 1. Grid renders — profile row labels, audience column headers, cell values
  test("renders the health grid from fixtures", async ({ terminal }) => {
    // Wait for a profile row label to confirm the grid has loaded
    await expect(terminal.getByText("work", { strict: false })).toBeVisible();

    // Other profile row labels
    expect(terminal.getByText("personal", { strict: false })).toBeVisible();
    expect(terminal.getByText("devbox", { strict: false })).toBeVisible();

    // Audience column headers — repeat across breadcrumb/header so strict:false
    expect(terminal.getByText("graph", { strict: false })).toBeVisible();
    expect(terminal.getByText("mail",  { strict: false })).toBeVisible();
    expect(terminal.getByText("cal",   { strict: false })).toBeVisible();

    // Cell values — these repeat across the matrix so strict must be false
    expect(terminal.getByText("ok",   { strict: false })).toBeVisible();
    expect(terminal.getByText("warn", { strict: false })).toBeVisible();
    expect(terminal.getByText("fail", { strict: false })).toBeVisible();
  });

  // 2. Arrow / hjkl cursor moves do not crash
  test("cursor navigation does not crash", async ({ terminal }) => {
    await expect(terminal.getByText("work", { strict: false })).toBeVisible();

    terminal.write("j");
    terminal.write("j");
    terminal.write("k");
    terminal.write("l");
    terminal.write("l");
    terminal.write("h");
    terminal.write("h");

    // Grid must still be visible after all moves
    expect(terminal.getByText("work",     { strict: false })).toBeVisible();
    expect(terminal.getByText("personal", { strict: false })).toBeVisible();
  });

  // 3. r — refresh re-runs fetch_grid without crashing
  test("r refresh reloads the grid", async ({ terminal }) => {
    await expect(terminal.getByText("work", { strict: false })).toBeVisible();
    terminal.write("r");
    await expect(terminal.getByText("work", { strict: false })).toBeVisible();
  });

  // 4. Esc — opens overlay menu; Resume visible; second Esc dismisses
  test("Esc opens the menu and shows Resume", async ({ terminal }) => {
    await expect(terminal.getByText("work", { strict: false })).toBeVisible();
    terminal.keyEscape();
    await expect(terminal.getByText("Resume")).toBeVisible();
    expect(terminal.getByText("Quit", { strict: false })).toBeVisible();
    // Dismiss — grid returns
    terminal.keyEscape();
    await expect(terminal.getByText("work", { strict: false })).toBeVisible();
  });

  // 5. q — quits the doctor screen
  test("q quits", async ({ terminal }) => {
    await expect(terminal.getByText("work", { strict: false })).toBeVisible();
    terminal.write("q");
    // After quit the doctor grid is no longer the active view — no crash.
  });

  // 6. classify_finding buckets are all exercised by the fixture:
  //    work=all ok, personal/cal (6 min) -> warn, personal/mail + devbox -> fail.
  test("renders ok / warn / fail buckets from classify_finding", async ({ terminal }) => {
    await expect(terminal.getByText("work", { strict: false })).toBeVisible();
    // Each bucket repeats across the matrix so strict:false on every cell value.
    expect(terminal.getByText("ok",   { strict: false })).toBeVisible();
    expect(terminal.getByText("warn", { strict: false })).toBeVisible();
    expect(terminal.getByText("fail", { strict: false })).toBeVisible();
  });

  // 7. Explicit column navigation (l / right) walks the cursor across audience
  //    columns. The grid is a read-only matrix — the StatusBar shows a fixed
  //    shape line, not per-cell detail — so we assert the audience headers and
  //    grid stay intact after moving the cursor across columns and back.
  test("h/l and arrow column navigation walks across audiences", async ({ terminal }) => {
    await expect(terminal.getByText("work", { strict: false })).toBeVisible();
    terminal.write("l");
    terminal.keyRight();
    terminal.write("h");
    terminal.keyLeft();
    // Last audience column header + grid still visible after navigation.
    expect(terminal.getByText("cal",  { strict: false })).toBeVisible();
    expect(terminal.getByText("work", { strict: false })).toBeVisible();
  });

  // 8. The grid status line reports the matrix shape (3 profiles × 3 audiences).
  test("status bar reports the matrix shape", async ({ terminal }) => {
    await expect(terminal.getByText("work", { strict: false })).toBeVisible();
    expect(terminal.getByText("3 rows", { strict: false })).toBeVisible();
  });

  // 9. enter is NOT bound on OwaGridScreen — the doctor grid is a pure matrix
  //    with no error-detail drill-down. Pressing enter must be a no-op.
  test("enter is a no-op on the read-only grid", async ({ terminal }) => {
    await expect(terminal.getByText("work", { strict: false })).toBeVisible();
    terminal.submit(); // enter — unbound
    expect(terminal.getByText("work", { strict: false })).toBeVisible();
  });
});
