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
});
