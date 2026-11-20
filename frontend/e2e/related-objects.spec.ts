import { expect, test } from "@playwright/test";

import { fieldByLabel, login, rowByText, uniqueSuffix } from "./helpers";

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("creates a category from the article's picker", async ({ page }) => {
  const title = `E2E related ${uniqueSuffix()}`;
  const category = `E2E category ${uniqueSuffix()}`;

  await page.goto("/admin/content/demo_blog.article/new");
  await fieldByLabel(page, "title").fill(title);

  // The picker ends with an entry that creates what was typed.
  await page.locator("div[role=combobox]").click();
  await page.getByPlaceholder("Search").fill(category);
  await page.getByText(`Create category “${category}”`).click();

  // The category studio's create form, the name filled in.
  const dialog = page.getByRole("dialog");
  await expect(fieldByLabel(dialog, "name")).toHaveValue(category);
  await dialog.getByRole("button", { name: "Create" }).click();
  await expect(dialog).toBeHidden();

  // The new category is chosen, and the article kept its changes.
  await expect(
    page.locator("div[role=combobox]").getByText(category),
  ).toBeVisible();
  await expect(fieldByLabel(page, "title")).toHaveValue(title);
  await expect(page).toHaveURL(/\/content\/demo_blog\.article\/new$/);

  // Remove the category again: other tests count the seeded ones. A new
  // tab, so the unsaved article does not hold the page.
  const other = await page.context().newPage();
  await other.goto("/admin/content/demo_blog.category");
  await rowByText(other, category).click();
  await other.getByRole("button", { name: "More actions" }).click();
  await other.getByRole("menuitem", { name: "Delete" }).click();
  await other.getByRole("button", { name: "Continue" }).click();
  await expect(rowByText(other, category)).toHaveCount(0);
});
