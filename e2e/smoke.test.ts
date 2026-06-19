import { test, expect } from "@microsoft/tui-test";

// Black-box e2e: spawn the real owa-tui binary in a pty and assert on what it
// actually renders. Complements the in-process pytest/pilot tests in src/tests.

test.describe("owa-tui CLI", () => {
  test.use({ program: { file: "owa-tui", args: ["--help"] } });

  test("shows usage", async ({ terminal }) => {
    await expect(terminal.getByText("usage: owa-tui")).toBeVisible();
  });
});

test.describe("owa-tui home screen", () => {
  test.use({ program: { file: "owa-tui" } });

  test("launches to the tool selector", async ({ terminal }) => {
    await expect(terminal.getByText("Select a tool to open:")).toBeVisible();
  });
});
