import { expect, test } from "@playwright/test";

import { fieldByLabel, login, rowByText, uniqueSuffix } from "./helpers";

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("creates articles one after another and saves with the keyboard", async ({
  page,
}) => {
  const first = `E2E first ${uniqueSuffix()}`;
  const second = `E2E second ${uniqueSuffix()}`;

  await page.goto("/admin/content/demo_blog.article/new");
  await fieldByLabel(page, "title").fill(first);
  await fieldByLabel(page, "body").fill("Written by the e2e suite.");

  // Create and add another: a fresh create form, and a toast that links
  // back to the first article.
  await page.getByRole("button", { name: "More save options" }).click();
  await page.getByRole("menuitem", { name: "Create and add another" }).click();
  await expect(page.getByText(`"${first}" was created.`)).toBeVisible();
  await expect(page).toHaveURL(/\/content\/demo_blog\.article\/new$/);
  await expect(fieldByLabel(page, "title")).toHaveValue("");

  // Ctrl+S from inside a field saves, and the editor stays open.
  await fieldByLabel(page, "title").fill(second);
  await fieldByLabel(page, "body").fill("Saved with the keyboard.");
  await fieldByLabel(page, "body").press("ControlOrMeta+s");
  await expect(page).toHaveURL(/\/content\/demo_blog\.article\/\d+$/);
  await expect(page.getByText("Unsaved changes")).toBeHidden();

  // Save and close goes back to the list.
  await fieldByLabel(page, "title").fill(`${second} (edited)`);
  await page.getByRole("button", { name: "More save options" }).click();
  await page.getByRole("menuitem", { name: "Save and close" }).click();
  await expect(page).toHaveURL(/\/content\/demo_blog\.article$/);
  await expect(rowByText(page, first)).toBeVisible();
  await expect(rowByText(page, `${second} (edited)`)).toBeVisible();
});
