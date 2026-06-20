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
});
