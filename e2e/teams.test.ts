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

  // ===========================================================================
  // List screen — cursor movement (j / k) and search returning results
  // ===========================================================================

  // ---------------------------------------------------------------------------
  // 7. j j l — moving the cursor down twice then opening picks the SECOND chat
  //
  // Chats are sorted newest-first by lastUpdatedDateTime:
  //   row 0  General Engineering   (2026-06-19)  → teams_19_general_…json
  //   row 1  Q2 Review             (2026-06-18)  → teams_messages.json (fallback)
  //   row 2  Alice Strand (1:1)    (2026-06-17)  → teams_messages.json (fallback)
  // So "j" highlights row 0, a second "j" moves to row 1 (Q2 Review).  Opening
  // that row proves the cursor actually moved — the fallback thread body
  // ("Hello from the fallback thread.") is unique to NON-General threads.
  // ---------------------------------------------------------------------------
  test("j moves the cursor down (second chat opens its thread)", async ({ terminal }) => {
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();

    terminal.write("j"); // highlight row 0 (General Engineering)
    terminal.write("j"); // move to row 1 (Q2 Review)
    terminal.write("l"); // open the highlighted thread

    // Q2 Review breadcrumb + its fallback messages confirm the SECOND row opened,
    // not the first.  "Standup in 10 minutes" (General-only) must NOT show.
    await expect(terminal.getByText("Q2 Review", { strict: false })).toBeVisible();
    await expect(
      terminal.getByText("Hello from the fallback thread", { strict: false })
    ).toBeVisible();
    await expect(
      terminal.getByText("Standup in 10 minutes", { strict: false })
    ).not.toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 8. k moves the cursor back up — j j (row 1) then k (back to row 0) opens
  //    General Engineering, whose unique body is "Standup in 10 minutes".
  // ---------------------------------------------------------------------------
  test("k moves the cursor up (returns to the first chat)", async ({ terminal }) => {
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();

    terminal.write("j"); // row 0
    terminal.write("j"); // row 1 (Q2 Review)
    terminal.write("k"); // back to row 0 (General Engineering)
    terminal.write("l"); // open the highlighted thread

    // General Engineering thread body is unique to the specific fixture.
    await expect(
      terminal.getByText("Standup in 10 minutes", { strict: false })
    ).toBeVisible();
    // The fallback body must NOT appear — proves we opened row 0, not row 1.
    await expect(
      terminal.getByText("Hello from the fallback thread", { strict: false })
    ).not.toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 9. / search RETURNING RESULTS — typing a chat keyword + Enter filters the
  //    list down to the matching chat; non-matches disappear.
  //
  // fetch_items filters on _chat_display_name(c) containing the search string
  // (case-insensitive).  Searching "Q2" matches only "Q2 Review".
  // ---------------------------------------------------------------------------
  test("/ search filters the chats list to matches", async ({ terminal }) => {
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();
    await expect(terminal.getByText("Q2 Review", { strict: false })).toBeVisible();

    terminal.write("/");
    await expect(
      terminal.getByText("Enter to search", { strict: false })
    ).toBeVisible();

    terminal.write("Q2");
    terminal.submit(); // Enter — apply the filter

    // Matching chat stays; non-matching chat is filtered out.
    await expect(terminal.getByText("Q2 Review", { strict: false })).toBeVisible();
    await expect(
      terminal.getByText("General Engineering", { strict: false })
    ).not.toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 9b. o — open_browser on the CHATS LIST screen.  TeamsScreen now overrides
  // open_browser_for to return the chat's webUrl, so `o` launches the browser
  // (host-dependent in a headless pty) — assert the screen survives.
  // ---------------------------------------------------------------------------
  test("o open browser does not crash the chats list", async ({ terminal }) => {
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();
    terminal.write("j"); // highlight a chat so an item is selected
    terminal.write("o"); // open_browser (webUrl present)
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 9c. tab — focus_pane on the CHATS LIST screen toggles focus between list
  // and detail pane.  No distinct visible text; assert the chats list still
  // renders (no-crash check).
  // ---------------------------------------------------------------------------
  test("tab toggles pane focus on the chats list without crashing", async ({ terminal }) => {
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();
    terminal.write("j"); // highlight a chat (populates the detail preview)
    terminal.write("\t"); // tab -> focus detail pane
    terminal.write("\t"); // tab -> focus list again
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();
  });

  // ===========================================================================
  // Thread screen — its OWN scroll bindings (j/k line, d/u page, g/G top/bottom,
  // r refresh).  Open General Engineering first (j then l).  These are scroll
  // operations with no easily-asserted visual delta on a tall RichLog, so each
  // asserts "no crash": a known message body is still visible afterward.
  // ===========================================================================

  // ---------------------------------------------------------------------------
  // 10. j / k scroll the thread by a line — content survives (no crash).
  // ---------------------------------------------------------------------------
  test("thread j/k scroll without crashing", async ({ terminal }) => {
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();
    terminal.write("j");
    terminal.write("l");
    await expect(
      terminal.getByText("Standup in 10 minutes", { strict: false })
    ).toBeVisible();

    // Scroll up a line then back down a line — thread must stay intact.
    terminal.write("k");
    terminal.write("j");
    await expect(
      terminal.getByText("Standup in 10 minutes", { strict: false })
    ).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 11. d / u page the thread — content survives (no crash).
  // ---------------------------------------------------------------------------
  test("thread d/u page scroll without crashing", async ({ terminal }) => {
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();
    terminal.write("j");
    terminal.write("l");
    await expect(
      terminal.getByText("Standup in 10 minutes", { strict: false })
    ).toBeVisible();

    // Page up then page down — no observable delta on a short thread; assert no crash.
    terminal.write("u");
    terminal.write("d");
    await expect(
      terminal.getByText("Standup in 10 minutes", { strict: false })
    ).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 12. g / G jump to top / bottom of the thread.  g (top) reveals the FIRST
  //     message ("Standup in 10 minutes"); G (bottom) is the default view.
  // ---------------------------------------------------------------------------
  test("thread g/G jump to top and bottom", async ({ terminal }) => {
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();
    terminal.write("j");
    terminal.write("l");
    await expect(
      terminal.getByText("Standup in 10 minutes", { strict: false })
    ).toBeVisible();

    terminal.write("g"); // jump to top — first message is visible
    await expect(
      terminal.getByText("Standup in 10 minutes", { strict: false })
    ).toBeVisible();

    terminal.write("G"); // jump to bottom — last message body is visible
    // msg-004 is HTML; tags are stripped leaving plain text.
    await expect(
      terminal.getByText("architecture review", { strict: false })
    ).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 13. r refreshes the thread — re-fetches + re-renders; content reappears.
  // ---------------------------------------------------------------------------
  test("thread r refreshes and keeps content visible", async ({ terminal }) => {
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();
    terminal.write("j");
    terminal.write("l");
    await expect(
      terminal.getByText("Standup in 10 minutes", { strict: false })
    ).toBeVisible();

    terminal.write("r"); // refresh — clears + re-fetches from the fixture
    await expect(
      terminal.getByText("Standup in 10 minutes", { strict: false })
    ).toBeVisible();
  });

  // ---------------------------------------------------------------------------
  // 14. Esc pops the thread back to the chats list (mirror of the h test).
  // ---------------------------------------------------------------------------
  test("thread Esc pops back to the chats list", async ({ terminal }) => {
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();
    terminal.write("j");
    terminal.write("l");
    await expect(
      terminal.getByText("Standup in 10 minutes", { strict: false })
    ).toBeVisible();

    terminal.keyEscape(); // pop_back to the chats list

    // All chats visible again; the thread body is gone.
    await expect(terminal.getByText("General Engineering", { strict: false })).toBeVisible();
    await expect(terminal.getByText("Q2 Review", { strict: false })).toBeVisible();
  });
});
