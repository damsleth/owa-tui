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
});
