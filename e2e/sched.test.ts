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
});
