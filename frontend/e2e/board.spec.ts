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

test("moves a card to another column by dragging, with undo", async ({
  page,
}) => {
  await login(page);
  const title = `E2E board ${uniqueSuffix()}`;

  // An article of its own, so parallel tests keep theirs. New articles
  // start as ideas.
  await page.goto("/admin/content/demo_blog.article/new");
  await fieldByLabel(page, "title").fill(title);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/content\/demo_blog\.article\/\d+$/);

  await page.goto("/admin/content/demo_blog.article");
  await page.getByTitle("Board: Stage").click();
  await page.getByPlaceholder("Search", { exact: true }).fill(title);

  const idea = page.getByRole("region", { name: "Idea", exact: true });
  const writing = page.getByRole("region", { name: "Writing", exact: true });
  const card = (column: Locator) =>
    column.locator("[data-card]").filter({ hasText: title });

  await expect(card(idea)).toBeVisible();
  await drag(page, card(idea), writing);

  await expect(
    page
      .locator("[data-sonner-toast]")
      .getByText("Stage saved", { exact: true }),
  ).toBeVisible();
  await expect(card(writing)).toBeVisible();
  await expect(card(idea)).toBeHidden();

  // The new stage is saved.
  await page.reload();
  await expect(card(writing)).toBeVisible();

  // Undo puts it back.
  await drag(page, card(writing), idea);
  await expect(card(idea)).toBeVisible();
  await page.getByRole("button", { name: "Undo" }).first().click();
  await expect(card(writing)).toBeVisible();
  await expect(card(idea)).toBeHidden();
});
