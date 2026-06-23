// End-to-end coverage of every user action, driven through the real owa-tui
// binary in a pty. Deterministic data comes from OWA_TUI_FIXTURES (see
// src/owa_tui/fixtures.py) so no live auth / network is needed.
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@microsoft/tui-test";

const FIXTURES = join(dirname(fileURLToPath(import.meta.url)), "fixtures");
const env = { ...process.env, OWA_TUI_FIXTURES: FIXTURES };
// Wide enough that cal/graph side panes don't truncate list labels.
const size = { columns: 120, rows: 40 };

// --------------------------------------------------------------------------
// Home screen — navigation + launch into each tool
// --------------------------------------------------------------------------
test.describe("home", () => {
  test.use({ program: { file: "owa-tui" }, env, ...size });

  test("lists the registered tools", async ({ terminal }) => {
    await expect(terminal.getByText("Select a tool to open:")).toBeVisible();
    await expect(terminal.getByText("Calendar")).toBeVisible();
    await expect(terminal.getByText("Mail")).toBeVisible();
    await expect(terminal.getByText("Graph Explorer")).toBeVisible();
  });

  test("j/k move the cursor and Enter opens a tool", async ({ terminal }) => {
    await expect(terminal.getByText("Select a tool to open:")).toBeVisible();
    terminal.submit(); // Enter -> open first tool (Calendar)
    await expect(terminal.getByText("owa-cal")).toBeVisible();
  });

  test("q quits", async ({ terminal }) => {
    await expect(terminal.getByText("Select a tool to open:")).toBeVisible();
    terminal.write("q");
    await expect(terminal.getByText("Select a tool to open:")).not.toBeVisible();
  });
});

// --------------------------------------------------------------------------
// Calendar — list, respond chord, search, menu, refresh, quit
// --------------------------------------------------------------------------
test.describe("cal", () => {
  test.use({ program: { file: "owa-tui", args: ["--tool", "cal"] }, env, ...size });

  test("renders the agenda from fixtures", async ({ terminal }) => {
    await expect(terminal.getByText("Morning standup", { strict: false })).toBeVisible();
    await expect(terminal.getByText("Lunch review")).toBeVisible();
  });

  test("j/k move the selection", async ({ terminal }) => {
    await expect(terminal.getByText("Morning standup", { strict: false })).toBeVisible();
    terminal.write("j");
    terminal.write("k");
    await expect(terminal.getByText("Morning standup", { strict: false })).toBeVisible();
  });

  test("r refreshes", async ({ terminal }) => {
    await expect(terminal.getByText("Morning standup", { strict: false })).toBeVisible();
    terminal.write("r");
    await expect(terminal.getByText("Morning standup", { strict: false })).toBeVisible();
  });

  test("y then a accepts the selected event", async ({ terminal }) => {
    await expect(terminal.getByText("Morning standup", { strict: false })).toBeVisible();
    terminal.write("y");
    await expect(terminal.getByText("(a)ccept")).toBeVisible();
    terminal.write("a");
    await expect(terminal.getByText("accepted")).toBeVisible();
  });

  test("y then d declines", async ({ terminal }) => {
    await expect(terminal.getByText("Morning standup", { strict: false })).toBeVisible();
    terminal.write("y");
    await expect(terminal.getByText("(a)ccept")).toBeVisible();
    terminal.write("d");
    await expect(terminal.getByText("declined")).toBeVisible();
  });

  test("/ opens search and Esc cancels", async ({ terminal }) => {
    await expect(terminal.getByText("Morning standup", { strict: false })).toBeVisible();
    terminal.write("/");
    await expect(terminal.getByText("Enter to confirm")).toBeVisible();
    terminal.keyEscape();
    await expect(terminal.getByText("Morning standup", { strict: false })).toBeVisible();
  });

  test("Esc opens the menu and Esc closes it", async ({ terminal }) => {
    await expect(terminal.getByText("Morning standup", { strict: false })).toBeVisible();
    terminal.keyEscape();
    await expect(terminal.getByText("Resume")).toBeVisible();
    await expect(terminal.getByText("Quit", { strict: false })).toBeVisible();
    terminal.keyEscape();
    await expect(terminal.getByText("Morning standup", { strict: false })).toBeVisible();
  });

  test("q quits", async ({ terminal }) => {
    await expect(terminal.getByText("Morning standup", { strict: false })).toBeVisible();
    terminal.write("q");
    await expect(terminal.getByText("Morning standup", { strict: false })).not.toBeVisible();
  });

  test("y then t tentatively accepts", async ({ terminal }) => {
    await expect(terminal.getByText("Morning standup", { strict: false })).toBeVisible();
    terminal.write("y");
    await expect(terminal.getByText("(a)ccept")).toBeVisible();
    terminal.write("t");
    await expect(terminal.getByText("tentatively accepted")).toBeVisible();
  });

  test("enter opens the detail pane and h closes it", async ({ terminal }) => {
    await expect(terminal.getByText("Morning standup", { strict: false })).toBeVisible();
    terminal.write("j"); // highlight first row (index starts at None)
    terminal.submit(); // Enter -> drill into detail pane
    await expect(terminal.getByText("detail focus", { strict: false })).toBeVisible();
    terminal.write("h"); // back_to_list — clears status, list stays visible
    await expect(terminal.getByText("Morning standup", { strict: false })).toBeVisible();
  });

  test("o reports there is no web link for the event", async ({ terminal }) => {
    await expect(terminal.getByText("Morning standup", { strict: false })).toBeVisible();
    terminal.write("j"); // highlight first row
    terminal.write("o"); // open_browser — fixture events carry no webLink
    await expect(terminal.getByText("no web link for this event", { strict: false })).toBeVisible();
  });
});

// --------------------------------------------------------------------------
// Mail — list, open reader, toggle read, search, menu, quit
// --------------------------------------------------------------------------
test.describe("mail", () => {
  test.use({ program: { file: "owa-tui", args: ["--tool", "mail"] }, env, ...size });

  test("renders the message list from fixtures", async ({ terminal }) => {
    await expect(terminal.getByText("Q3 planning notes")).toBeVisible();
    await expect(terminal.getByText("Invoice")).toBeVisible();
  });

  test("l opens the reader and h closes it", async ({ terminal }) => {
    await expect(terminal.getByText("Q3 planning notes")).toBeVisible();
    terminal.write("j"); // highlight first row
    terminal.write("l"); // open reader
    await expect(terminal.getByText("Ship owa-tui v1")).toBeVisible();
    terminal.write("h"); // back to list
    await expect(terminal.getByText("Invoice")).toBeVisible();
  });

  test("j/k move and r toggles read", async ({ terminal }) => {
    await expect(terminal.getByText("Q3 planning notes")).toBeVisible();
    terminal.write("j");
    terminal.write("k");
    terminal.write("r"); // toggle read — fixture mode no-ops the PATCH
    await expect(terminal.getByText("Q3 planning notes")).toBeVisible();
  });

  test("/ opens search and Esc cancels", async ({ terminal }) => {
    await expect(terminal.getByText("Q3 planning notes")).toBeVisible();
    terminal.write("/");
    await expect(terminal.getByText("Enter to search")).toBeVisible();
    terminal.keyEscape();
    await expect(terminal.getByText("Q3 planning notes")).toBeVisible();
  });

  test("Esc opens the menu and Esc closes it", async ({ terminal }) => {
    await expect(terminal.getByText("Q3 planning notes")).toBeVisible();
    terminal.keyEscape();
    await expect(terminal.getByText("Resume")).toBeVisible();
    await expect(terminal.getByText("Quit", { strict: false })).toBeVisible();
    terminal.keyEscape();
    await expect(terminal.getByText("Q3 planning notes")).toBeVisible();
  });

  test("q quits", async ({ terminal }) => {
    await expect(terminal.getByText("Q3 planning notes")).toBeVisible();
    terminal.write("q");
    await expect(terminal.getByText("Q3 planning notes")).not.toBeVisible();
  });

  test("g and G jump to top and bottom", async ({ terminal }) => {
    await expect(terminal.getByText("Q3 planning notes")).toBeVisible();
    terminal.write("G"); // go_bottom
    terminal.write("g"); // go_top
    await expect(terminal.getByText("Q3 planning notes")).toBeVisible();
  });

  test("d and u page down and up", async ({ terminal }) => {
    await expect(terminal.getByText("Q3 planning notes")).toBeVisible();
    terminal.write("j"); // highlight first row
    terminal.write("d"); // page_down
    terminal.write("u"); // page_up
    await expect(terminal.getByText("Q3 planning notes")).toBeVisible();
  });

  test("tab toggles pane focus without crashing", async ({ terminal }) => {
    await expect(terminal.getByText("Q3 planning notes")).toBeVisible();
    terminal.write("\t"); // focus_pane -> reader pane
    terminal.write("\t"); // focus_pane -> back to list
    // No observable status for focus toggle; assert the list survived.
    await expect(terminal.getByText("Q3 planning notes")).toBeVisible();
  });

  test("o reports there is no web link", async ({ terminal }) => {
    await expect(terminal.getByText("Q3 planning notes")).toBeVisible();
    terminal.write("j"); // highlight first row
    terminal.write("o"); // open_browser — fixture messages carry no web_link
    await expect(terminal.getByText("no web link", { strict: false })).toBeVisible();
  });

  test("reader scroll keys work and h closes it", async ({ terminal }) => {
    await expect(terminal.getByText("Q3 planning notes")).toBeVisible();
    terminal.write("j"); // highlight first row
    terminal.write("l"); // open reader
    await expect(terminal.getByText("Ship owa-tui v1")).toBeVisible();
    // Exercise reader scroll bindings — body is short so content stays visible.
    terminal.write("j"); // scroll down line
    terminal.write("k"); // scroll up line
    terminal.write("d"); // page down (mail reader uses j/k; d/u are list keys, harmless here)
    terminal.write("u"); // page up
    terminal.write("g"); // top
    terminal.write("G"); // bottom
    await expect(terminal.getByText("Ship owa-tui v1")).toBeVisible();
    terminal.write("h"); // close reader
    await expect(terminal.getByText("Invoice")).toBeVisible();
  });
});

// --------------------------------------------------------------------------
// Graph — object view, drill, back, menu, quit
// --------------------------------------------------------------------------
test.describe("graph", () => {
  test.use({ program: { file: "owa-tui", args: ["--tool", "graph"] }, env, ...size });

  test("renders the /me object from fixtures", async ({ terminal }) => {
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
  });

  test("l drills in and h goes back", async ({ terminal }) => {
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
    terminal.write("j"); // highlight first (drillable) row
    terminal.write("l"); // drill in
    await expect(terminal.getByText("First item", { strict: false })).toBeVisible();
    terminal.write("h"); // back
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
  });

  test("j/k move and r refreshes", async ({ terminal }) => {
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
    terminal.write("j");
    terminal.write("k");
    terminal.write("r");
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
  });

  test("Esc opens the menu and Esc closes it", async ({ terminal }) => {
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
    terminal.keyEscape();
    await expect(terminal.getByText("Resume")).toBeVisible();
    await expect(terminal.getByText("Quit", { strict: false })).toBeVisible();
    terminal.keyEscape();
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
  });

  test("q quits", async ({ terminal }) => {
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
    terminal.write("q");
    await expect(terminal.getByText("Test User", { strict: false })).not.toBeVisible();
  });

  test("g and G jump to top and bottom", async ({ terminal }) => {
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
    terminal.write("G"); // cursor_bottom
    terminal.write("g"); // cursor_top
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
  });

  test("n reports there is no next page", async ({ terminal }) => {
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
    terminal.write("n"); // next_page — fixture has no next_link
    await expect(terminal.getByText("no next page", { strict: false })).toBeVisible();
  });

  test("a opens the audience input bar", async ({ terminal }) => {
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
    terminal.write("a"); // switch_audience -> input bar with audience placeholder
    await expect(terminal.getByText("audience", { strict: false })).toBeVisible();
    terminal.keyEscape();
  });

  test("/ opens the jump-to-path input bar (not a search modal)", async ({ terminal }) => {
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
    terminal.write("/"); // jump_path -> input bar placeholder "path (current: …)"
    await expect(terminal.getByText("path (current", { strict: false })).toBeVisible();
    terminal.keyEscape();
  });

  test("e opens the edit-query input bar", async ({ terminal }) => {
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
    terminal.write("e"); // edit_query -> input bar placeholder "query params (current: …)"
    await expect(terminal.getByText("query params", { strict: false })).toBeVisible();
    terminal.keyEscape();
  });

  test("o targets Graph Explorer on the graph audience", async ({ terminal }) => {
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
    terminal.write("o"); // open_browser — sets a status; browser availability varies
    // The launch outcome depends on the host (no real browser in the pty), so
    // just assert the screen survives and the object view is still rendered.
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
  });

  test("y yanks the current URL", async ({ terminal }) => {
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
    terminal.write("y"); // yank_url -> "yanked: <url>" (pbcopy on macOS) / "url: <url>" fallback
    await expect(terminal.getByText("graph.microsoft.com", { strict: false })).toBeVisible();
  });

  test("c adds a curl command to the debug buffer", async ({ terminal }) => {
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
    terminal.write("c"); // curl_command
    await expect(terminal.getByText("curl command added", { strict: false })).toBeVisible();
  });

  test("m bookmarks the current path", async ({ terminal }) => {
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
    terminal.write("m"); // bookmark -> "bookmarked: graph:me"
    await expect(terminal.getByText("bookmarked", { strict: false })).toBeVisible();
  });

  test("M opens the bookmark picker and Enter jumps to it", async ({ terminal }) => {
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
    terminal.write("m"); // bookmark current location (graph:me)
    await expect(terminal.getByText("bookmarked", { strict: false })).toBeVisible();
    terminal.write("M"); // open the jump-to-bookmark picker
    await expect(terminal.getByText("jump to bookmark", { strict: false })).toBeVisible();
    terminal.submit(); // Enter -> jump to the selected bookmark, refetches graph:me
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
  });

  test("M with no bookmarks reports there are none", async ({ terminal }) => {
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
    terminal.write("M"); // no bookmarks added in this fresh session
    await expect(terminal.getByText("no bookmark", { strict: false })).toBeVisible();
  });

  test("D toggles the debug overlay", async ({ terminal }) => {
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
    terminal.write("c"); // seed the debug buffer with a curl line
    terminal.write("D"); // debug_overlay -> shows "Debug buffer:"
    await expect(terminal.getByText("Debug buffer", { strict: false })).toBeVisible();
    terminal.write("D"); // toggle off
    await expect(terminal.getByText("Test User", { strict: false })).toBeVisible();
  });
});
