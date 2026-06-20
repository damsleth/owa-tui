// End-to-end coverage of the Teams tool user actions, driven through the real
// owa-tui binary in a pty.  Deterministic data comes from OWA_TUI_FIXTURES
// (see src/owa_tui/fixtures.py) — no live auth or Graph calls needed.
//
// FIXTURE SEAM:
//   teams.json                              chats list (raw Graph /me/chats payload)
//   teams_<slug>.json                       per-chat messages (slug = chat id slugified)
//   teams_messages.json                     fallback messages for any unmatched slug
//
// Where <slug> = re.sub(r"[^a-zA-Z0-9]+", "_", chat_id).strip("_")
// e.g. "19:general-engineering_thread.v2" → "19_general_engineering_thread_v2"
//
// KEY GOTCHAS applied throughout:
//   - import { test, expect }  named import (NOT default)
//   - test.use({ columns:120, rows:40 }) via size spread — applied at describe level
//   - getByText strict:true by default; use { strict:false } wherever a string
//     appears in multiple places (sender names in both list row + thread header,
//     chat topic in both chats list AND thread breadcrumb, repeated words)
//   - ListView starts index=None; "l"/Enter is a no-op until "j" highlights a row
//   - open chat thread:  terminal.write("j")  then  terminal.write("l")
//   - back to chats:     terminal.write("h")
//   - OWA_TUI_FIXTURES must be absolute — derive via import.meta.url
//   - env spread: { ...process.env, OWA_TUI_FIXTURES: FIXTURES }
//   - launch args: ["--tool", "teams"]

import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@microsoft/tui-test";

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), "fixtures");
const env = { ...process.env, OWA_TUI_FIXTURES: FIXTURES };
// Wide enough that chat topics and sender columns never truncate.
const size = { columns: 120, rows: 40 };

test.describe("teams", () => {
  test.use({ program: { file: "owa-tui", args: ["--tool", "teams"] }, env, ...size });

  // ---------------------------------------------------------------------------
  // 1. Chats list — all three fixture chats render from teams.json
  // ---------------------------------------------------------------------------
  test("renders the chats list from fixtures", async ({ terminal }) => {
    // All three chat topics/names must appear in the list.
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();
    await expect(terminal.getByText("Q2 Review", { strict: false })).toBeVisible();
    // The 1:1 chat has no topic — displayed as member names joined.
    // "Alice Strand" appears as the derived display name for that chat row.
    await expect(terminal.getByText("Alice Strand", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 2. j then l — opens a chat thread; messages from teams_<slug>.json render
  //
  // GOTCHA: ListView starts index=None; pressing "l" before "j" is a no-op.
  // GOTCHA: chat topic appears in both the chats-list row AND the thread
  //         breadcrumb after opening — use strict:false everywhere.
  // GOTCHA: sender names (e.g. "Alice Strand") appear in multiple message
  //         blocks — always strict:false for those.
  // ---------------------------------------------------------------------------
  test("j then l opens a chat thread and shows message content", async ({ terminal }) => {
    // Wait for chats list to be ready.
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();

    // Highlight the first row.
    terminal.write("j");
    // Open the thread (equivalent to Enter / right-arrow for list screens).
    terminal.write("l");

    // Thread breadcrumb should contain the chat topic.
    // strict:false — topic now appears in breadcrumb AND possibly status bar.
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();

    // At least one message body from teams_19_general_engineering_thread_v2.json
    // must be visible in the RichLog.  Each sender line also has the sender name,
    // so use strict:false for any text that repeats.
    await expect(
      terminal.getByText("Standup in 10 minutes", { strict: false })
    ).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 3. h — goes back to the chats list from the thread
  // ---------------------------------------------------------------------------
  test("h goes back to the chats list from the thread", async ({ terminal }) => {
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();

    terminal.write("j");
    terminal.write("l");

    // Confirm thread is open.
    await expect(
      terminal.getByText("Standup in 10 minutes", { strict: false })
    ).toBeVisible();

    // Pop back to the chats list.
    terminal.write("h");

    // All three chats must be visible again.
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();
    await expect(terminal.getByText("Q2 Review", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 4. / — opens search input; Esc cancels and restores the chats list
  //
  // NOTE: TeamsScreen passes search_prompt="Filter chats:" to OwaListScreen,
  //       so the search modal hint text contains "Enter to search".
  // ---------------------------------------------------------------------------
  test("/ opens search and Esc cancels", async ({ terminal }) => {
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();

    terminal.write("/");
    // SearchModal hint text confirms the input is open.
    await expect(
      terminal.getByText("Enter to search", { strict: false })
    ).toBeVisible();

    terminal.keyEscape();
    // Chats list is restored.
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 5. Esc — opens overlay menu; Resume is visible; second Esc closes menu
  // ---------------------------------------------------------------------------
  test("Esc opens the menu and shows Resume", async ({ terminal }) => {
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();

    terminal.keyEscape();
    await expect(terminal.getByText("Resume")).toBeVisible();
    await expect(terminal.getByText("Quit", { strict: false })).toBeVisible();

    terminal.keyEscape();
    // Menu dismissed; chats list is back.
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 6. q — quits the Teams screen (chats list no longer visible)
  // ---------------------------------------------------------------------------
  test("q quits", async ({ terminal }) => {
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();
    terminal.write("q");
    await expect(
      terminal.getByText("General Engineering", { strict: false })
    ).not.toBeVisible();
  });
});
