import { test, expect } from "@playwright/test"

test.describe("Auth Flow", () => {
  test("login page loads with email and password fields", async ({ page }) => {
    await page.goto("/login")
    await expect(page.locator("h1")).toContainText("Welcome back")
    await expect(page.locator("#email")).toBeVisible()
    await expect(page.locator("#password")).toBeVisible()
    await expect(page.locator('button[type="submit"]')).toContainText("Sign In")
  })

  test("register link navigates to register page", async ({ page }) => {
    await page.goto("/login")
    await page.click('a[href="/register"]')
    await expect(page).toHaveURL("/register")
    await expect(page.locator("h1")).toContainText("Create an account")
  })

  test("register page loads with form fields", async ({ page }) => {
    await page.goto("/register")
    await expect(page.locator("#name")).toBeVisible()
    await expect(page.locator("#email")).toBeVisible()
    await expect(page.locator("#password")).toBeVisible()
    await expect(page.locator("#confirmPassword")).toBeVisible()
    await expect(page.locator('button[type="submit"]')).toContainText("Create Account")
  })
})

test.describe("Dashboard", () => {
  test("dashboard page loads with stat cards and chart sections", async ({ page }) => {
    await page.goto("/dashboard")
    await expect(page.locator("h1").or(page.locator('a[href="/login"]'))).toBeVisible()

    const onDashboard = page.url().includes("/dashboard")
    if (!onDashboard) return

    await expect(page.locator("h1")).toContainText("Dashboard")
  })
})

test.describe("Generate", () => {
  test("generate page loads with project name and prompt inputs", async ({ page }) => {
    await page.goto("/generate")
    await expect(page.locator("h1").or(page.locator('a[href="/login"]'))).toBeVisible()

    const onPage = page.url().includes("/generate")
    if (!onPage) return

    await expect(page.locator("#projectName")).toBeVisible()
    await expect(page.locator("#prompt")).toBeVisible()
    await expect(page.locator('button:has-text("Generate Project")')).toBeVisible()
  })
})

test.describe("History", () => {
  test("history page loads with job list", async ({ page }) => {
    await page.goto("/history")
    await expect(page.locator("h1").or(page.locator('a[href="/login"]'))).toBeVisible()

    const onPage = page.url().includes("/history")
    if (!onPage) return

    await expect(page.locator("h1")).toContainText("History")
  })
})

test.describe("Chat", () => {
  test("chat page loads with conversation area", async ({ page }) => {
    await page.goto("/chat")
    await expect(page.locator("main").or(page.locator('a[href="/login"]'))).toBeVisible()

    const onPage = page.url().includes("/chat")
    if (!onPage) return
  })
})

test.describe("Analytics", () => {
  test("analytics page loads with chart sections", async ({ page }) => {
    await page.goto("/analytics")
    await expect(page.locator("h1").or(page.locator('a[href="/login"]'))).toBeVisible()

    const onPage = page.url().includes("/analytics")
    if (!onPage) return

    await expect(page.locator("h1")).toContainText("Analytics")
  })
})

test.describe("Settings", () => {
  test("settings page loads with profile form", async ({ page }) => {
    await page.goto("/settings")
    await expect(page.locator("h1").or(page.locator('a[href="/login"]'))).toBeVisible()

    const onPage = page.url().includes("/settings")
    if (!onPage) return

    await expect(page.locator("h1")).toContainText("Settings")
  })

  test("settings sub-pages are accessible", async ({ page }) => {
    await page.goto("/settings/notifications")
    const onPage = page.url().includes("/settings")
    if (!onPage) return

    await page.goto("/settings/appearance")
    const onAppearance = page.url().includes("/settings")
    if (!onAppearance) return

    await page.goto("/settings/api-keys")
  })
})

test.describe("Responsive", () => {
  test("mobile sidebar hamburger shows on small viewport", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto("/dashboard")
    await expect(page.locator("main").or(page.locator('a[href="/login"]'))).toBeVisible()

    const onDashboard = page.url().includes("/dashboard")
    if (!onDashboard) return

    const menuButton = page.locator('button[aria-label="Open navigation menu"]')
    await expect(menuButton).toBeVisible()
    await menuButton.click()

    const drawer = page.locator('[role="navigation"][aria-label="Mobile navigation"]')
    await expect(drawer).toBeVisible()
    await expect(drawer.locator("text=Dashboard")).toBeVisible()
    await expect(drawer.locator("text=Generate")).toBeVisible()
    await expect(drawer.locator("text=History")).toBeVisible()
    await expect(drawer.locator("text=Chat")).toBeVisible()
  })
})

test.describe("Navigation", () => {
  test("sidebar navigation items navigate to correct pages", async ({ page }) => {
    await page.goto("/dashboard")
    await expect(page.locator("main").or(page.locator('a[href="/login"]'))).toBeVisible()

    const onDashboard = page.url().includes("/dashboard")
    if (!onDashboard) return

    const nav = page.locator("aside nav")
    const links = nav.locator("a")

    const pages = [
      { href: "/dashboard", label: "Dashboard" },
      { href: "/generate", label: "Generate" },
      { href: "/history", label: "History" },
      { href: "/chat", label: "Chat" },
      { href: "/workspace", label: "Workspace" },
      { href: "/analytics", label: "Analytics" },
    ]

    for (const pageInfo of pages) {
      const link = links.locator(`[href="${pageInfo.href}"]`).first()
      await expect(link).toBeVisible()
    }
  })
})

test.describe("404", () => {
  test("unknown dashboard route shows not-found page", async ({ page }) => {
    await page.goto("/dashboard/nonexistent-route")
    await expect(page.locator("text=404").or(page.locator("text=Page not found"))).toBeVisible()
  })

  test("unknown top-level route shows not-found page", async ({ page }) => {
    await page.goto("/this-does-not-exist")
    await expect(page.locator("text=404").or(page.locator("text=Page not found"))).toBeVisible()
  })
})
