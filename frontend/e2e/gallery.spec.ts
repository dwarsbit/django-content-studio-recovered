import { expect, test } from "@playwright/test";

import { login } from "./helpers";

test("shows articles as tiles, in two sizes", async ({ page }) => {
  await login(page);
  await page.goto("/admin/content/demo_blog.article");
  await page.getByTitle("Gallery view").click();

  const tiles = page.locator("[data-tile]");
  await expect(tiles.first()).toBeVisible();
  await expect(
    tiles.filter({ hasText: "Hello, Content Studio" }),
  ).toBeVisible();

  // Small tiles, remembered across a reload.
  await page.getByTitle("Small tiles").click();
  await expect(page.locator("ul[data-size]")).toHaveAttribute(
    "data-size",
    "small",
  );
  await page.reload();
  await expect(page.locator("ul[data-size]")).toHaveAttribute(
    "data-size",
    "small",
  );

  // A tile opens the article.
  await tiles.filter({ hasText: "Hello, Content Studio" }).click();
  await expect(page).toHaveURL(/\/content\/demo_blog\.article\/\d+$/);
});
