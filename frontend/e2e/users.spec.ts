import { expect, type Page, test } from "@playwright/test";

import { login, rowByText } from "./helpers";

// The built-in user studio's edit page: account details and permissions
// on tabs, the status, dates and activity in the sidebar.
const USERS = "/admin/content/auth.user";
// Field labels are capitalized by CSS, so match them in any case.
const ACTIVE = /^active$/i;
const STAFF = /^staff status$/i;
const SUPERUSER = /^superuser status$/i;

async function openEditor(page: Page) {
  await page.goto(USERS);
  await rowByText(page, "editor").first().click();
  await expect(page.getByRole("tab", { name: "Profile" })).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("lays out a user on tabs and in the sidebar", async ({ page }) => {
  await openEditor(page);

  const main = page.getByRole("tabpanel");
  const sidebar = page.locator("aside");

  await expect(main.getByText("Account", { exact: true })).toBeVisible();
  await expect(main.getByText("Personal info")).toBeVisible();

  for (const label of [ACTIVE, STAFF, SUPERUSER]) {
    await expect(sidebar.getByLabel(label)).toBeVisible();
    await expect(main.getByLabel(label)).toHaveCount(0);
  }

  await expect(sidebar.getByText("Important dates")).toBeVisible();
  await expect(
    sidebar.getByRole("heading", { name: "Activity" }),
  ).toBeVisible();
});

test("tells what a status means for the user", async ({ page }) => {
  await openEditor(page);

  const callouts = page.locator("aside").getByTestId("callout");
  const inactive = callouts.filter({ hasText: "Inactive users cannot log in" });
  const notStaff = callouts.filter({ hasText: "Only staff users can log in" });
  const sidebar = page.locator("aside");

  await expect(inactive).toHaveCount(0);
  await expect(notStaff).toHaveCount(0);

  await sidebar.getByLabel(STAFF).click();
  await expect(notStaff).toBeVisible();

  // One reason at a time.
  await sidebar.getByLabel(ACTIVE).click();
  await expect(inactive).toBeVisible();
  await expect(notStaff).toHaveCount(0);
});

test("a superuser gets a callout instead of the permission matrix", async ({
  page,
}) => {
  await openEditor(page);
  await page.getByRole("tab", { name: "Permissions" }).click();

  const matrix = page.getByPlaceholder("Search permissions");
  const callout = page
    .getByRole("tabpanel")
    .getByTestId("callout")
    .filter({ hasText: "A superuser has every permission" });

  await expect(matrix).toBeVisible();
  await expect(callout).toHaveCount(0);

  await page.locator("aside").getByLabel(SUPERUSER).click();
  await expect(callout).toBeVisible();
  await expect(matrix).toHaveCount(0);
  // Groups still apply to whatever else a project uses them for.
  await expect(page.getByRole("tabpanel").getByText(/^groups$/i)).toBeVisible();
});

test("the create form shows no empty cards", async ({ page }) => {
  await page.goto(`${USERS}/new`);
  await expect(page.getByRole("tab", { name: "Profile" })).toBeVisible();

  // A new user has no dates and no activity: only the status shows.
  const cards = page.locator("aside section:visible");

  await expect(cards).toHaveCount(1);
  await expect(cards.getByRole("heading", { name: "Status" })).toBeVisible();
});

test("the sidebar sits under the main column on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openEditor(page);

  const main = await page.getByRole("tabpanel").boundingBox();
  const sidebar = await page.locator("aside").boundingBox();

  expect(main).not.toBeNull();
  expect(sidebar).not.toBeNull();
  expect(sidebar!.y).toBeGreaterThanOrEqual(main!.y + main!.height);
  expect(sidebar!.x).toBeCloseTo(main!.x, 0);

  // The name fields stack instead of squeezing into two columns.
  const first = await page
    .getByRole("tabpanel")
    .getByText(/^first name$/i)
    .boundingBox();
  const last = await page
    .getByRole("tabpanel")
    .getByText(/^last name$/i)
    .boundingBox();

  expect(last!.y).toBeGreaterThan(first!.y);
  expect(last!.x).toBeCloseTo(first!.x, 0);
});
