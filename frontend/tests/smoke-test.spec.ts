import { test, expect } from '@playwright/test'

test.describe('Mission Control Smoke Test', () => {
  test.setTimeout(60000) // 60 second timeout

  test('full vertical slice - login, create project, create task, verify on kanban', async ({ page }) => {
    // Enable request/response logging for debugging
    page.on('response', response => {
      if (response.status() >= 400) {
        console.log(`[HTTP ${response.status()}] ${response.url()}`)
      }
    })

    // 1. Navigate to login page
    await page.goto('/login')
    await expect(page.locator('text=Mission Control Login')).toBeVisible()

    // 2. Login with credentials
    await page.locator('input[name="login"]').fill('johan@example.com')
    await page.locator('input[name="password"]').fill('devpass')
    
    // Get CSRF token from cookie if set, or wait for response
    const loginResponsePromise = page.waitForResponse(response => 
      response.url().includes('/auth/login') && response.status() === 200
    )
    await page.locator('button[type="submit"]').click()
    await loginResponsePromise

    // 3. Wait for redirect to org selection page
    await expect(page.locator('text=Select Organization')).toBeVisible({ timeout: 10000 })
    
    // 4. Navigate to Default Organization (created by bootstrap script)
    // Click on the list item containing "Default Organization"
    await page.locator('text=Default Organization').first().click()

    // 5. Should be redirected to projects page (/orgs/default/projects)
    await expect(page.locator('h2:has-text("Projects")')).toBeVisible({ timeout: 10000 })

    // 6. Create a new Project
    await page.locator('button:has-text("New Project")').click()
    await expect(page.locator('.v-card-title:has-text("Create Project")')).toBeVisible()
    
    // Fill in project name - first text input in the dialog
    const projectDialog = page.locator('.v-dialog .v-card')
    const projectNameInput = projectDialog.locator('input[type="text"]').first()
    await projectNameInput.fill('Automated Test Project')
    
    // Click Create button in the dialog
    const createButton = projectDialog.locator('button.v-btn').filter({ hasText: 'Create' })
    await createButton.click()
    
    // Wait for dialog to close and project to appear
    await expect(projectDialog).not.toBeVisible({ timeout: 10000 })
    await expect(page.locator('text=Automated Test Project').first()).toBeVisible({ timeout: 15000 })

    // 7. Navigate to Tasks page
    await page.goto('/orgs/default/tasks')
    await expect(page.locator('h2:has-text("Tasks")')).toBeVisible({ timeout: 10000 })

    // 8. Create a new Task
    await page.locator('button:has-text("New Task")').click()
    await expect(page.locator('.v-card-title:has-text("New Task")')).toBeVisible()
    
    const taskDialog = page.locator('.v-dialog .v-card')
    
    // Fill in task title - first input in the dialog
    const taskTitleInput = taskDialog.locator('input[type="text"]').first()
    await taskTitleInput.fill('Automated Test Task')
    
    // Select the project from the Projects dropdown
    // Open the dropdown by clicking on it
    await taskDialog.locator('.v-select').filter({ hasText: 'Projects' }).click()
    
    // Wait for dropdown menu and click on the project
    await page.locator('.v-list-item').filter({ hasText: 'Automated Test Project' }).click()
    
    // Click Create button
    await taskDialog.locator('button.v-btn').filter({ hasText: 'Create' }).click()

    // 9. Verify the Task appears on the Kanban board
    await expect(taskDialog).not.toBeVisible({ timeout: 10000 })
    
    // Wait for the task to appear in the backlog column
    await expect(page.locator('.kanban-column').filter({ hasText: /Backlog/i })).toBeVisible({ timeout: 10000 })
    
    // Verify the task card appears
    const taskCard = page.locator('.kanban-column').filter({ hasText: /Backlog/i }).locator('.v-card, .task-card').filter({ hasText: 'Automated Test Task' })
    await expect(taskCard).toBeVisible({ timeout: 15000 })
    
    // Take a screenshot for verification
    await page.screenshot({ path: 'test-results/smoke-test-kanban.png' })
  })
})
