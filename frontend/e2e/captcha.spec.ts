import { expect, test } from "@playwright/test";

/**
 * The demo site's contact form behind the captcha
 * (content_studio.contrib.captcha): the browser solves the proof of work
 * with the vendored widget and solver, under the page's
 * Content-Security-Policy, and the form accepts the token once.
 */

test.beforeEach(async ({ page }) => {
  // Fail on anything the page's CSP blocks.
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (event) => {
      console.error(
        `CSP violation: ${event.violatedDirective} ${event.blockedURI}`,
      );
    });
  });
});

test("the contact form needs the captcha", async ({ page }) => {
  await page.goto("/contact/");
  await page.getByLabel("Email").fill("reader@example.com");
  await page.getByLabel("Message").fill("Hello");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByText("Verify that you are human.")).toBeVisible();
  await expect(page.getByRole("status")).toHaveCount(0);
});

test("the widget solves the captcha and the form is sent", async ({ page }) => {
  const violations: string[] = [];
  page.on("console", (message) => {
    if (message.text().startsWith("CSP violation"))
      violations.push(message.text());
  });

  await page.goto("/contact/");
  await page.getByLabel("Email").fill("reader@example.com");
  await page.getByLabel("Message").fill("Hello");

  await page.locator("cap-widget").click();
  const token = page.locator('input[name="captcha"]');
  await expect(token).toHaveValue(/^[0-9a-f]{16}:[0-9a-f]{30}$/, {
    timeout: 20_000,
  });

  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByRole("status")).toHaveText(
    "Thanks, your message was sent.",
  );
  expect(violations).toEqual([]);
});
