import { expect, test } from "@playwright/test";

import { fieldByLabel, login, rowByText, uniqueSuffix } from "./helpers";

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("edits table cells in place, undoes and reports errors", async ({
  page,
}) => {
  const title = `E2E inline ${uniqueSuffix()}`;
  const renamed = `${title} renamed`;

  // An article of its own, so parallel tests keep theirs.
  await page.goto("/admin/content/demo_blog.article/new");
  await fieldByLabel(page, "title").fill(title);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/content\/demo_blog\.article\/\d+$/);
  await page.getByRole("button", { name: "Back to the list" }).click();

  const row = rowByText(page, title);
  await expect(row).toBeVisible();

  // A number cell saves on Enter; the toast names the field.
  await row.getByRole("button", { name: "views" }).click();
  await row.getByRole("textbox", { name: "views" }).fill("4321");
  await row.getByRole("textbox", { name: "views" }).press("Enter");
  await expect(page.getByText("Views saved")).toBeVisible();
  await expect(row.getByText("4,321")).toBeVisible();

  // Undo saves the old value back.
  await page.getByRole("button", { name: "Undo" }).first().click();
  await expect(row.getByText("4,321")).toBeHidden();

  // A switch saves on click; the row does not open.
  await row.getByRole("switch", { name: "featured" }).click();
  await expect(page.getByText("Featured saved")).toBeVisible();
  await expect(page).toHaveURL(/\/content\/demo_blog\.article$/);
  await expect(row.getByRole("switch", { name: "featured" })).toBeChecked();

  // An invalid value stays in the cell with the reason; Esc reverts it.
  // (While the title is in an input the row has no title text, so the
  // open input is found on the page.)
  const titleInput = page.getByRole("textbox", { name: "title" });
  await row.getByRole("button", { name: "title" }).click();
  await titleInput.fill("");
  await titleInput.press("Enter");
  const failed = page.getByRole("button", { name: "title" }).filter({
    has: page.getByRole("img", { name: "This field may not be blank." }),
  });
  await expect(failed).toBeVisible();
  await failed.press("Escape");
  await expect(row.getByText(title)).toBeVisible();

  // Tab saves and moves on to the next editable cell.
  await row.getByRole("button", { name: "title" }).click();
  await titleInput.fill(renamed);
  await titleInput.press("Tab");
  const renamedRow = rowByText(page, renamed);
  await expect(renamedRow).toBeVisible();
  await expect(
    renamedRow.getByRole("switch", { name: "featured" }),
  ).toBeFocused();

  // The other cells still open the article.
  await renamedRow.getByText("Draft").click();
  await expect(page).toHaveURL(/\/content\/demo_blog\.article\/\d+$/);
  await expect(fieldByLabel(page, "title")).toHaveValue(renamed);
});
