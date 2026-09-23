/**
 * e2e/swodp.test.ts
 *
 * Black-box coverage of the SWODP week grid (SwodpScreen) via pty.
 * Fixture data: e2e/fixtures/swodp.json (cards), swodp_cal.json (calendar).
 * Fixture mode never launches Edge; `w` is a dry-run.
 */

import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@microsoft/tui-test";

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), "fixtures");
const CONFIG = mkdtempSync(join(tmpdir(), "owa-tui-swodp-"));
const env = { ...process.env, OWA_TUI_FIXTURES: FIXTURES, XDG_CONFIG_HOME: CONFIG };

test.describe("swodp", () => {
  test.use({
    program: { file: "owa-tui", args: ["--tool", "swodp"] },
    env,
    columns: 140,
    rows: 40,
  });

  test("renders the week-38 grid with sums", async ({ terminal }) => {
    await expect(terminal.getByText("Uke 38", { strict: false })).toBeVisible();
    expect(terminal.getByText("NOCOS T1PRJTSK4228809", { strict: false })).toBeVisible();
    expect(terminal.getByText("per dag", { strict: false })).toBeVisible();
    expect(terminal.getByText("39.5", { strict: false })).toBeVisible();
  });

  test("edit one cell, w shows the diff, y writes (dry-run)", async ({ terminal }) => {
    await expect(terminal.getByText("3 kort", { strict: false })).toBeVisible();
    terminal.write("l"); // NOCOS, tirsdag (7)
    terminal.write("i");
    await expect(terminal.getByText("now 7", { strict: false })).toBeVisible();
    terminal.write("6\r");
    await expect(terminal.getByText("1 unwritten", { strict: false })).toBeVisible();
    terminal.write("w");
    await expect(terminal.getByText("update  NOCOS T1PRJTSK4228809: tir 7→6", { strict: false })).toBeVisible();
    terminal.write("y\r");
    await expect(terminal.getByText("1 updated (fixture dry-run)", { strict: false })).toBeVisible();
  });

  test("c fills from the calendar and names unmapped categories", async ({ terminal }) => {
    await expect(terminal.getByText("3 kort", { strict: false })).toBeVisible();
    terminal.write("c");
    await expect(terminal.getByText("unmapped: XX KUNDE 2h", { strict: false })).toBeVisible();
  });

  test("[ goes to the previous week", async ({ terminal }) => {
    await expect(terminal.getByText("Uke 38", { strict: false })).toBeVisible();
    terminal.write("[");
    await expect(terminal.getByText("Uke 37", { strict: false })).toBeVisible();
  });
});
