import { expect, type Locator, type Page, test } from "@playwright/test";

import { fieldByLabel, login, uniqueSuffix } from "./helpers";

// dnd-kit starts a drag after the pointer moved a few pixels.
async function drag(page: Page, from: Locator, to: Locator) {
  const a = await from.boundingBox();
  const b = await to.boundingBox();

  if (!a || !b) {
    throw new Error("drag: element not visible");
  }

  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
  await page.mouse.down();
  await page.mouse.move(a.x + a.width / 2 + 8, a.y + a.height / 2 + 8, {
    steps: 4,
  });
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 10 });
  await page.mouse.up();
}

test("schedules a draft by dragging it onto a day, with undo", async ({
  page,
}) => {
  await login(page);
  const title = `E2E calendar ${uniqueSuffix()}`;

  // A draft of its own, so parallel tests keep theirs.
  await page.goto("/admin/content/demo_blog.article/new");
  await fieldByLabel(page, "title").fill(title);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/content\/demo_blog\.article\/\d+$/);

  await page.goto("/admin/content/demo_blog.article");
  await page.getByTitle("Calendar: Published at").click();

  // Next month: every day of it is in the future.
  await page.getByRole("button", { name: "Next month" }).click();
  await expect(page).toHaveURL(/month=\d{4}-\d{2}/);
  const month = new URL(page.url()).searchParams.get("month");
  const day = page.locator(`[data-day="${month}-15"]`);

  // The draft waits in the tray; drop it on the 15th.
  const tray = page.getByRole("complementary", { name: "No date" });
  await drag(page, tray.getByRole("button", { name: title }), day);

  await expect(
    page.locator("[data-sonner-toast]").getByText("Scheduled", { exact: true }),
  ).toBeVisible();
  await expect(day.getByRole("button", { name: title })).toBeVisible();
  await expect(tray.getByRole("button", { name: title })).toBeHidden();

  // Undo makes it a draft again.
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(tray.getByRole("button", { name: title })).toBeVisible();
  await expect(day.getByRole("button", { name: title })).toBeHidden();

  // The month stays in the URL across a reload.
  await page.reload();
  await expect(page).toHaveURL(new RegExp(`month=${month}`));
});
