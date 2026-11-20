import { expect, test } from "@playwright/test";

import { fieldByLabel, login, uniqueSuffix } from "./helpers";

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("the HTMLField model renders the rich text widget", async ({ page }) => {
  const title = `Landing page ${uniqueSuffix()}`;
  // Digit-only suffix: TipTap's typography extension rewrites "x" between
  // digits into a multiplication sign, which would break text matching.
  const body = `Rich text body ${Date.now()}`;

  await page.goto("/admin/content/demo_blog.landingpage");
  // The empty list renders a second Create link in its empty state;
  // the header's is the first.
  await page.getByRole("link", { name: "Create" }).first().click();
  await expect(page).toHaveURL(/\/content\/demo_blog\.landingpage\/new$/);

  await fieldByLabel(page, "title").fill(title);

  // The HTMLField renders a TipTap editor, not a plain textarea.
  const editor = page.locator("div[contenteditable=true]");
  await expect(editor).toBeVisible();
  await editor.click();
  await page.keyboard.type(body);

  await page.getByRole("button", { name: "Create" }).click();
  // Saving keeps the editor open; the route becomes the new object's.
  await expect(page).toHaveURL(/\/content\/demo_blog\.landingpage\/\d+$/);

  await page.getByRole("button", { name: "Back to the list" }).click();
  await expect(
    page.getByRole("row", { name: new RegExp(title) }),
  ).toBeVisible();

  // Reopening shows the persisted rich text.
  await page.getByRole("row", { name: new RegExp(title) }).click();
  await expect(page).toHaveURL(/\/content\/demo_blog\.landingpage\/\d+$/);
  await expect(page.getByText(body)).toBeVisible();
});

// A 1x1 PNG.
const PIXEL = Buffer.from(
  "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c6300010000050001" +
    "0d0a2db40000000049454e44ae426082",
  "hex",
);

test("inserts an image, a table and a link to an article", async ({ page }) => {
  const title = `Rich page ${uniqueSuffix()}`;
  const imageName = `rich-${uniqueSuffix()}.png`;

  await page.goto("/admin/content/demo_blog.landingpage/new");
  await fieldByLabel(page, "title").fill(title);

  const editor = page.locator("div[contenteditable=true]").first();
  const toolbar = page
    .locator(".rich-text-field")
    .first()
    .locator("xpath=../../..");
  await editor.click();
  await page.keyboard.type("Start here: ");

  // A link to an article, found through the Content tab.
  await toolbar.getByRole("button", { name: "Add link" }).click();
  const linkDialog = page.getByRole("dialog");
  await linkDialog
    .getByPlaceholder("Search for content to link to")
    .fill("Hello");
  await linkDialog.getByRole("option").first().click();
  await linkDialog.getByRole("button", { name: "Add link" }).click();
  const link = editor.locator("a[data-link-model='demo_blog.article']");
  await expect(link).toHaveAttribute("href", /^\/blog\/.+\/$/);

  // An image from the media library, uploaded in the picker.
  await page.keyboard.press("End");
  await page.keyboard.press("Enter");
  await toolbar.getByRole("button", { name: "Insert image" }).click();
  const picker = page.getByRole("dialog");
  await picker.locator("input[type=file]").setInputFiles({
    name: imageName,
    mimeType: "image/png",
    buffer: PIXEL,
  });
  await picker.getByRole("button", { name: new RegExp(imageName) }).click();
  await picker.getByRole("button", { name: "Select media" }).click();
  await expect(editor.locator("figure.rich-text-figure img")).toHaveCount(1);

  // A table, with a row added from its menu.
  await editor.locator("figure .figcaption").click();
  await page.keyboard.type("A caption");
  await page.keyboard.press("ArrowDown");
  await toolbar.getByRole("button", { name: "Insert table" }).click();
  await page.keyboard.type("Leg");
  await page.getByRole("button", { name: "Add row below" }).click();
  await expect(editor.locator("table tr")).toHaveCount(4);

  await page.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/content\/demo_blog\.landingpage\/\d+$/);

  // Reopening shows all three.
  await page.reload();
  const saved = page.locator(".rich-text-field").first();
  await expect(
    saved.locator("a[data-link-model='demo_blog.article']"),
  ).toBeVisible();
  await expect(saved.locator("figure.rich-text-figure img")).toBeVisible();
  await expect(saved.getByText("A caption")).toBeVisible();
  await expect(saved.locator("th").first()).toHaveText("Leg");
});
