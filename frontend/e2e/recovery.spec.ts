import { expect, test } from "@playwright/test";

import { fieldByLabel, login, uniqueSuffix } from "./helpers";

/**
 * Unsaved changes are kept in the browser: a reload mid-edit offers
 * them back, Restore puts them in the form, and Save forgets them.
 */
test("recovers unsaved changes after a reload", async ({ page }) => {
  const title = `Recovery ${uniqueSuffix()}`;

  await login(page);
  await page.goto("/admin/content/demo_blog.article/new");
  await fieldByLabel(page, "title").fill(title);
  await fieldByLabel(page, "body").fill("Written by the e2e suite.");
  await page.locator("[data-slot=select-trigger]").click();
  await page.getByRole("option", { name: "Published" }).click();
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/content\/demo_blog\.article\/\d+$/);

  await fieldByLabel(page, "title").fill(`${title} (unsaved)`);
  await expect(page.getByTestId("changes-kept")).toBeVisible();

  await page.reload();
  const banner = page.getByTestId("recovery-banner");
  await expect(banner).toBeVisible();
  await expect(fieldByLabel(page, "title")).toHaveValue(title);

  await banner.getByRole("button", { name: "Restore unsaved changes" }).click();
  await expect(fieldByLabel(page, "title")).toHaveValue(`${title} (unsaved)`);
  await expect(banner).toBeHidden();

  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText(`${title} (unsaved)`).first()).toBeVisible();

  await page.reload();
  await expect(fieldByLabel(page, "title")).toHaveValue(`${title} (unsaved)`);
  await expect(page.getByTestId("recovery-banner")).toBeHidden();
});
