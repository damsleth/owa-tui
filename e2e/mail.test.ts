// End-to-end coverage of the Mail tool folder panel, driven through the real
// owa-tui binary in a pty. Deterministic data comes from OWA_TUI_FIXTURES
// (see src/owa_tui/fixtures.py) — no live auth needed.
//
// XDG_CONFIG_HOME is redirected to a throwaway dir so toggling the folder panel
// (which persists tui_show_folders via owa_mail.config) never touches the real
// user config.
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { test, expect } from "@microsoft/tui-test";

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), "fixtures");
const CONFIG = mkdtempSync(join(tmpdir(), "owa-tui-mail-e2e-"));
const env = { ...process.env, OWA_TUI_FIXTURES: FIXTURES, XDG_CONFIG_HOME: CONFIG };
const size = { columns: 120, rows: 40 };

test.describe("mail", () => {
  test.use({ program: { file: "owa-tui", args: ["--tool", "mail"] }, env, ...size });

  // 1. Render — message list populates from fixture data.
  test("renders the message list from fixtures", async ({ terminal }) => {
    await expect(terminal.getByText("Q3 planning notes")).toBeVisible();
    await expect(terminal.getByText("Re: Invoice #4821", { strict: false })).toBeVisible();
  });

  // 2. F toggles the folder panel; folders load from mail_folders.json with
  //    unread badges. Default is off, so the panel is absent until pressed.
  test("F shows the folder panel with folders from fixtures", async ({ terminal }) => {
    await expect(terminal.getByText("Q3 planning notes")).toBeVisible();
    terminal.write("F");
    await expect(terminal.getByText("Inbox", { strict: false })).toBeVisible();
    await expect(terminal.getByText("Archive", { strict: false })).toBeVisible();
    await expect(terminal.getByText("Deleted Items", { strict: false })).toBeVisible();
  });

  // 3. F again hides the panel — folder-only labels disappear, list remains.
  test("F again hides the folder panel", async ({ terminal }) => {
    await expect(terminal.getByText("Q3 planning notes")).toBeVisible();
    terminal.write("F");
    await expect(terminal.getByText("Archive", { strict: false })).toBeVisible();
    terminal.write("F");
    await expect(terminal.getByText("Archive", { strict: false })).not.toBeVisible();
    await expect(terminal.getByText("Q3 planning notes")).toBeVisible();
  });
});
