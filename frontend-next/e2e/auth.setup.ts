import { test as setup } from "@playwright/test"
import path from "path"

const authFile = path.resolve(process.cwd(), ".auth", "user.json")

setup("authenticate", async ({ page }) => {
  await page.goto("/login")
  await page.waitForSelector("#email")

  await page.fill("#email", "test@example.com")
  await page.fill("#password", "password123")
  await page.click('button[type="submit"]')

  await page.waitForURL(/\/dashboard|\/login/, { timeout: 10000 })

  await page.context().storageState({ path: authFile })
})
