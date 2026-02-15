# Mission Control UI Style & Design Guide

This document defines the visual identity, component standards, and interaction patterns for the Mission Control Web UI. It serves as the binding reference for all frontend implementation — deviations require explicit justification.

---

## Design Philosophy

Mission Control is a **work environment**, not a marketing site. People spend hours in it. The UI must be:

- **Calm.** Neutral backgrounds, restrained color, low visual noise. The content (projects, tasks, messages) is the focus, not the interface.
- **Dense but readable.** Information density matters — users manage many projects and tasks. But density must not come at the cost of legibility or scannability.
- **Predictable.** Every interaction follows the same patterns. No surprises, no cleverness. Users should never wonder "how do I do X" — the answer is always the same mechanism.
- **Accessible first.** Color is never the sole indicator. All interactions are keyboard-reachable. Minimum contrast ratios are enforced.

---

## Color System

The palette is intentionally quiet — warm off-whites and grays for surfaces, with color reserved for meaning (status, priority, actions). Inspired by Claude.ai's calm, paper-like aesthetic.

### Surface Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `--surface-primary` | `#F5F0E8` | Page background. The dominant color of the app — warm, paper-like off-white. |
| `--surface-secondary` | `#EBE5DB` | Sidebar background, card hover state, subtle section dividers. |
| `--surface-elevated` | `#FFFFFF` | Cards, modals, dropdowns, popovers. White surfaces "float" above the warm background. |
| `--surface-sunken` | `#E5DFD5` | Input field backgrounds, code blocks, inset areas. |
| `--surface-overlay` | `rgba(0, 0, 0, 0.4)` | Modal backdrop, drawer backdrop. |

### Text Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `--text-primary` | `#1A1A1A` | Headings, primary content, task titles. High contrast on all surfaces. |
| `--text-secondary` | `#6B6560` | Metadata, timestamps, labels, secondary descriptions. |
| `--text-tertiary` | `#9B9590` | Placeholders, disabled text, subtle hints. |
| `--text-inverse` | `#FFFFFF` | Text on dark/colored backgrounds (action buttons, badges). |

### Border Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `--border-default` | `#D9D3C9` | Card borders, input borders, dividers. |
| `--border-subtle` | `#E8E2D8` | Very light separation lines (between list items, table rows). |
| `--border-focus` | `#C47830` | Focus ring on interactive elements. Visible and distinct. |

### Status Colors

Used exclusively for project lifecycle stages and task statuses. Never used decoratively.

| Token | Hex | Usage |
|-------|-----|-------|
| `--status-backlog` | `#9B9590` | Tasks in Backlog. Muted — not yet active. |
| `--status-active` | `#3D7FCA` | In-Progress tasks, Development/POC/Testing projects. The "working" state. |
| `--status-review` | `#C47830` | In-Review tasks, Adoption projects. Amber — awaiting action. |
| `--status-complete` | `#5A9E6F` | Complete tasks, Maintenance projects. Green — done. |
| `--status-archived` | `#B5AFA5` | End-of-life projects, archived items. Faded. |

### Priority Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `--priority-critical` | `#C0392B` | Critical priority. Red — demands attention. |
| `--priority-high` | `#D4742C` | High priority. Warm orange. |
| `--priority-medium` | `#C4A83D` | Medium priority. Muted gold. |
| `--priority-low` | `#7B9E89` | Low priority. Sage green — calm. |

### Action Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `--action-primary` | `#C47830` | Primary action buttons (create, save, confirm). Warm amber-brown — distinctive without being aggressive. |
| `--action-primary-hover` | `#A8622A` | Primary button hover state. |
| `--action-destructive` | `#C0392B` | Destructive actions (delete, revoke, remove). Always requires confirmation. |
| `--action-destructive-hover` | `#A33025` | Destructive button hover state. |

### Agent Badge

| Token | Hex | Usage |
|-------|-----|-------|
| `--agent-badge-bg` | `#E8DFF0` | Background for agent badges and avatars. Soft lavender — visually distinct from human users. |
| `--agent-badge-text` | `#6B4E8A` | Text on agent badges. |

### CSS Custom Properties

All colors are defined as CSS custom properties on `:root` for consistency and future theming:

```css
:root {
  /* Surfaces */
  --surface-primary: #F5F0E8;
  --surface-secondary: #EBE5DB;
  --surface-elevated: #FFFFFF;
  --surface-sunken: #E5DFD5;
  --surface-overlay: rgba(0, 0, 0, 0.4);

  /* Text */
  --text-primary: #1A1A1A;
  --text-secondary: #6B6560;
  --text-tertiary: #9B9590;
  --text-inverse: #FFFFFF;

  /* Borders */
  --border-default: #D9D3C9;
  --border-subtle: #E8E2D8;
  --border-focus: #C47830;

  /* Status */
  --status-backlog: #9B9590;
  --status-active: #3D7FCA;
  --status-review: #C47830;
  --status-complete: #5A9E6F;
  --status-archived: #B5AFA5;

  /* Priority */
  --priority-critical: #C0392B;
  --priority-high: #D4742C;
  --priority-medium: #C4A83D;
  --priority-low: #7B9E89;

  /* Actions */
  --action-primary: #C47830;
  --action-primary-hover: #A8622A;
  --action-destructive: #C0392B;
  --action-destructive-hover: #A33025;

  /* Agent */
  --agent-badge-bg: #E8DFF0;
  --agent-badge-text: #6B4E8A;
}
```

### Dark Mode

Deferred to post-v1. The color system is structured to support a dark mode theme by swapping CSS variable values. No color is hardcoded in components — everything references tokens.

---

## Typography

### Font Stack

**Primary: Roboto** — clean, highly legible at small sizes, extensive weight range. Used for all body text, labels, metadata, and form inputs.

**Monospace: Roboto Mono** — consistent with the primary font's geometry. Used for code blocks, command output, IDs, and technical values.

**Display: Roboto Slab** — adds visual distinction for page headings and empty states without introducing a completely separate typeface. Used sparingly.

```css
:root {
  --font-primary: 'Roboto', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: 'Roboto Mono', 'Fira Code', monospace;
  --font-display: 'Roboto Slab', 'Roboto', serif;
}
```

Fonts are loaded from Google Fonts with `display=swap` to prevent invisible text during loading:

```html
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&family=Roboto+Mono:wght@400;500&family=Roboto+Slab:wght@500;700&display=swap" rel="stylesheet">
```

### Type Scale

A constrained scale with clear roles. Sizes are in `rem` for accessibility (respects user font size preferences).

| Token | Size | Weight | Line Height | Usage |
|-------|------|--------|-------------|-------|
| `--text-page-title` | 1.5rem (24px) | 500 (Roboto Slab) | 1.3 | Page headings: "Project Board", "Event Log" |
| `--text-section-title` | 1.125rem (18px) | 500 | 1.4 | Section headings within a page, Kanban column titles |
| `--text-card-title` | 0.9375rem (15px) | 500 | 1.4 | Project/task card titles, channel names |
| `--text-body` | 0.875rem (14px) | 400 | 1.5 | Default body text, descriptions, chat messages |
| `--text-meta` | 0.8125rem (13px) | 400 | 1.4 | Timestamps, metadata labels, user badges |
| `--text-small` | 0.75rem (12px) | 400 | 1.4 | Tertiary info, badge text, tooltip text |
| `--text-code` | 0.8125rem (13px) | 400 (Roboto Mono) | 1.5 | Code blocks, command output, IDs |

### Rules

- **Never use font sizes below 12px.** Anything smaller is unreadable at standard DPI.
- **Bold (`700`) is reserved for emphasis within body text.** Do not use bold for headings — use medium weight (`500`) instead. This keeps the overall tone calm.
- **All-caps is used only for small badges and labels** (e.g., "AGENT", "CRITICAL"), never for headings or body text. When used, apply `letter-spacing: 0.05em` for legibility.

---

## Component Library

### Framework: Vuetify 3

Vuetify provides the base component set, configured with the Mission Control theme. It covers inputs, buttons, dialogs, menus, navigation, chips, and layout primitives.

**Why Vuetify:**

- Comprehensive component library that eliminates the need to build common UI primitives.
- Built-in Material Design accessibility (ARIA attributes, keyboard navigation, focus management).
- Deep Vue 3 integration with Composition API support.
- Theme customization via SASS variables aligns with the color token system.
- Active maintenance and large community.

**Vuetify theme configuration:**

```typescript
// plugins/vuetify.ts

import { createVuetify } from 'vuetify'

export default createVuetify({
  theme: {
    defaultTheme: 'missionControl',
    themes: {
      missionControl: {
        dark: false,
        colors: {
          background: '#F5F0E8',
          surface: '#FFFFFF',
          primary: '#C47830',
          secondary: '#6B6560',
          error: '#C0392B',
          info: '#3D7FCA',
          success: '#5A9E6F',
          warning: '#D4742C',
        },
      },
    },
  },
  defaults: {
    VBtn: {
      variant: 'flat',
      rounded: 'lg',
    },
    VCard: {
      rounded: 'lg',
      elevation: 0,
      border: true,
    },
    VTextField: {
      variant: 'outlined',
      density: 'comfortable',
      rounded: 'lg',
    },
    VDialog: {
      maxWidth: 560,
      scrim: 'rgba(0, 0, 0, 0.4)',
    },
  },
})
```

### Data Tables: AG Grid (Community Edition)

Vuetify's built-in table component is adequate for simple lists, but the task list, user management table, and event log require features that justify a dedicated grid library:

- Column sorting, filtering, and resizing.
- Virtual scrolling for large datasets (thousands of events).
- Cell-level rendering customization (status badges, action buttons, user avatars).
- Column pinning (keep task title visible while scrolling horizontally).

**Where AG Grid is used:**

| View | Rationale |
|------|-----------|
| Task Board (list mode) | Alternate view to the Kanban board — sortable, filterable table of all tasks. |
| Event Log | High-volume, time-series data with multi-column filtering. |
| User Management | Admin table with inline actions (role change, key rotation). |
| Search Results (expanded) | Tabular view of search results when the user wants to compare across many results. |

**Where AG Grid is NOT used:** Kanban boards, chat, settings forms, or any view where a structured table layout is not the right paradigm. Do not force data into a grid when a card layout or form is more appropriate.

**AG Grid theme:** Styled to match the Mission Control palette using AG Grid's CSS variable theming:

```css
.ag-theme-mission-control {
  --ag-background-color: var(--surface-elevated);
  --ag-header-background-color: var(--surface-secondary);
  --ag-odd-row-background-color: var(--surface-primary);
  --ag-row-hover-color: var(--surface-secondary);
  --ag-border-color: var(--border-subtle);
  --ag-font-family: var(--font-primary);
  --ag-font-size: 14px;
  --ag-header-font-weight: 500;
  --ag-selected-row-background-color: #C4783015;
  --ag-range-selection-border-color: var(--action-primary);
}
```

### Kanban Boards: vuedraggable (SortableJS)

As specified in the frontend architecture. AG Grid is not used for Kanban boards — cards in columns is a fundamentally different paradigm from rows in a table.

---

## Interaction Patterns

### Core Principle: Click-to-Act, Never Hover-to-Reveal

**Hover states are banned as interaction triggers.** Hover is unreliable (touch devices, accessibility tools, motor impairments) and creates hidden functionality. Every action must be reachable by a visible, clickable element or a keyboard shortcut.

**Hover is permitted only for:**

- Visual feedback on interactive elements (button background color change, card border highlight). These are cosmetic — they communicate "this is clickable" but never reveal new functionality.
- Tooltips that provide **supplementary information only** — never actions. Tooltips must also be accessible via focus (keyboard users see the same tooltip when tabbing to the element).

### Action Hierarchy

Every action falls into one of three tiers. The tier determines how the action is presented.

**Tier 1 — Primary actions (create, save, confirm):**
- Always visible as a button in the view's primary action area.
- Uses `--action-primary` color.
- One primary action per view context. If a view has multiple primary actions, re-evaluate the design.

**Tier 2 — Contextual actions (edit, transition, assign):**
- Visible on the resource card or row as icon buttons or text links.
- Always visible — never hidden behind a hover or three-dot menu.
- For Kanban cards: action buttons are visible at the bottom of every card at all times.
- For table rows: action column with icon buttons always visible (no row-hover reveal).

**Tier 3 — Infrequent actions (delete, export, revoke):**
- Grouped in an "actions menu" triggered by a clearly labeled button (not a cryptic icon).
- The menu trigger is a visible button labeled "Actions" or a kebab icon (⋮) with an `aria-label`.
- The menu itself is a click-activated dropdown, never hover-activated.

```
Card example (all actions visible):

┌─────────────────────────────────────────┐
│  Implement SSE endpoint         HIGH 🔴 │
│  @agent-01 · Project B                  │
│  ─────────────────────────────────────  │
│  [Move to →]  [Edit]  [⋮ Actions]      │
└─────────────────────────────────────────┘

Table row example (actions column always shown):

│ Task Title         │ Status    │ Assignee  │ Actions           │
│ Implement SSE      │ Backlog   │ agent-01  │ [Edit] [⋮]       │
```

### Dialogs

Dialogs are used for actions that require confirmation, input, or a focused decision. They are never used for displaying information that could live inline.

**When to use a dialog:**
- Confirming a destructive action (delete, revoke, remove).
- Creating a new resource (project, task, user) — the creation form lives in a dialog.
- Submitting evidence on task completion.
- Org switching confirmation (if unsaved changes exist).

**When NOT to use a dialog:**
- Viewing resource details — use navigation or a slide-over panel instead.
- Displaying help text — use inline expandable sections.
- Showing errors — use inline error messages or toast notifications.
- Selecting from a simple list — use a dropdown menu.

**Dialog rules:**
- Maximum width: 560px. Dialogs should feel contained, not page-like.
- Always have a visible close button (X in top-right) AND a Cancel button.
- Primary action button is right-aligned. Destructive actions use `--action-destructive`.
- Focus is trapped within the dialog. Escape key closes the dialog.
- Background scroll is locked when a dialog is open.
- No nested dialogs. If a flow requires sequential decisions, use a stepped form within a single dialog.

```
┌──────────────────────────────────────────────┐
│  Create Task                            [X]  │
├──────────────────────────────────────────────┤
│                                              │
│  Title                                       │
│  ┌────────────────────────────────────────┐  │
│  │                                        │  │
│  └────────────────────────────────────────┘  │
│                                              │
│  Type            Priority                    │
│  [Feature ▾]     [Medium ▾]                  │
│                                              │
│  Project                                     │
│  [Select project(s) ▾]                       │
│                                              │
│  Assign to                                   │
│  [Select user(s) ▾]                          │
│                                              │
│  Evidence required on completion?            │
│  ( ) No  (•) Yes → [PR Link ▾]              │
│                                              │
├──────────────────────────────────────────────┤
│                    [Cancel]  [Create Task]   │
└──────────────────────────────────────────────┘
```

### Confirmation Dialogs

Destructive and irreversible actions require a two-step confirmation:

```
┌──────────────────────────────────────────────┐
│  Delete Project                         [X]  │
├──────────────────────────────────────────────┤
│                                              │
│  Are you sure you want to end-of-life        │
│  "Mission Control API"?                      │
│                                              │
│  This will archive all associated tasks      │
│  and channels. This action cannot be undone. │
│                                              │
│  Type the project name to confirm:           │
│  ┌────────────────────────────────────────┐  │
│  │                                        │  │
│  └────────────────────────────────────────┘  │
│                                              │
├──────────────────────────────────────────────┤
│                    [Cancel]  [Delete Project] │
└──────────────────────────────────────────────┘
```

The confirm button is disabled until the user types the resource name. This prevents accidental clicks and forces conscious acknowledgment.

### Menus and Dropdowns

- **Click-activated only.** Never open on hover.
- **Single-level.** No nested submenus. If a menu needs subcategories, redesign the information architecture.
- **Keyboard navigable.** Arrow keys move between items. Enter selects. Escape closes.
- **Positioned below the trigger** by default. If insufficient space, flip above. Never overlay the trigger itself.
- **Max 8 items.** If a menu has more than 8 items, use a dialog with a searchable list instead.
- **Destructive items at the bottom**, visually separated by a divider, in `--action-destructive` color.

```
┌──────────────────┐
│  Edit             │
│  Assign users     │
│  Add dependency   │
│  ───────────────  │
│  Archive task     │
└──────────────────┘
```

### Toast Notifications

- Appear in the **bottom-right corner**, stacked vertically.
- Auto-dismiss after **5 seconds** for informational toasts. Error toasts persist until dismissed.
- Maximum **3 visible toasts** at once. Additional toasts queue and appear as earlier ones dismiss.
- Each toast has a dismiss (X) button.
- Toasts are purely informational — they never contain actions or links.

| Type | Color | Icon | Usage |
|------|-------|------|-------|
| Success | `--status-complete` bg tint | ✓ checkmark | Resource created, transition confirmed |
| Error | `--action-destructive` bg tint | ✕ cross | API error, validation failure |
| Warning | `--status-review` bg tint | ⚠ triangle | Connection degraded, approaching limits |
| Info | `--status-active` bg tint | ℹ circle | Notification, system update available |

### Slide-Over Panels

Used for viewing resource details without losing the context of the parent view (e.g., clicking a task on the board opens its detail in a slide-over panel, keeping the board visible underneath).

- Slides in from the **right edge** of the viewport.
- Width: **480px** (fixed). Does not adapt to content.
- Has a visible close button and closes on Escape.
- Background is dimmed but **not scroll-locked** — the user can still see the parent view.
- Contains view-only information and tier-2 actions. Does not contain forms — editing opens a dialog.

### Empty States

When a view has no content (no projects, no tasks, no messages), show an empty state with:

- A brief message explaining what would appear here.
- A primary action to create the first resource (if the user has permission).
- No decorative illustrations — text only.

```
┌──────────────────────────────────────────────┐
│                                              │
│        No tasks yet                          │
│                                              │
│        Tasks appear here when created.       │
│        Create your first task to get         │
│        started.                              │
│                                              │
│              [Create Task]                   │
│                                              │
└──────────────────────────────────────────────┘
```

---

## Spacing and Layout

### Spacing Scale

A 4px base unit, used consistently across all spacing decisions.

| Token | Value | Usage |
|-------|-------|-------|
| `--space-1` | 4px | Tightest spacing: between icon and label, between badge elements |
| `--space-2` | 8px | Compact spacing: between list items, padding inside badges |
| `--space-3` | 12px | Default spacing: padding inside cards, gap between form fields |
| `--space-4` | 16px | Comfortable spacing: padding inside dialogs, gap between cards |
| `--space-5` | 20px | Section spacing: between major UI sections within a view |
| `--space-6` | 24px | Page padding: outer margins of the main content area |
| `--space-8` | 32px | Large spacing: between page title and content, between major sections |

### Border Radius

| Token | Value | Usage |
|-------|-------|-------|
| `--radius-sm` | 4px | Badges, small chips, inline code |
| `--radius-md` | 8px | Cards, inputs, buttons, dropdowns |
| `--radius-lg` | 12px | Dialogs, slide-over panels, large containers |
| `--radius-full` | 9999px | Avatars, round icon buttons |

### Shadows

Shadows are minimal — just enough to indicate elevation, not to create visual drama.

| Token | Value | Usage |
|-------|-------|-------|
| `--shadow-sm` | `0 1px 2px rgba(0, 0, 0, 0.06)` | Cards at rest, input focus |
| `--shadow-md` | `0 2px 8px rgba(0, 0, 0, 0.08)` | Dropdown menus, popovers |
| `--shadow-lg` | `0 4px 16px rgba(0, 0, 0, 0.1)` | Dialogs, slide-over panels |

---

## Iconography

### Icon Set: Material Design Icons (mdi)

Bundled with Vuetify. Consistent style across the entire app. Custom icons are not used unless no suitable mdi icon exists.

### Icon Rules

- Icons are **always paired with a text label** for primary and secondary actions. Icon-only buttons are allowed only in constrained spaces (table action columns, card footers) and must have an `aria-label`.
- Icon size: 20px for inline icons, 24px for standalone icon buttons.
- Icon color follows text color conventions (`--text-primary` for active, `--text-secondary` for metadata, `--text-tertiary` for disabled).

---

## Component Patterns

### Kanban Cards

```
┌─────────────────────────────────────────┐
│  Mission Control API            ┌─────┐ │
│                                 │ SW  │ │  ← type badge (Software)
│  Owner: Jane                    └─────┘ │
│  Tasks: ████████░░ 7/10                  │
│  ─────────────────────────────────────  │
│  [Move to →]  [View]  [⋮]              │
└─────────────────────────────────────────┘

Background: --surface-elevated
Border: --border-default
Border-left: 3px solid [lifecycle stage color]
```

The left border color indicates the lifecycle stage. Since the card is already in a stage column on the Kanban board, this is redundant on the board view — but it provides context when cards appear outside the board (e.g., in search results or notifications).

### Status Badges

Small, rounded pills showing status or type:

```
[In Progress]   bg: --status-active (10% opacity), text: --status-active
[Complete]      bg: --status-complete (10% opacity), text: --status-complete
[Agent]         bg: --agent-badge-bg, text: --agent-badge-text
[Feature]       bg: --surface-secondary, text: --text-secondary
```

All badges use the `--text-small` type scale, uppercase, with `letter-spacing: 0.05em`.

### Avatars

- **Humans:** Circular, 32px, showing initials on a generated background color (derived from a hash of the user ID, using a predefined palette of soft colors).
- **Agents:** Circular, 32px, showing initials on `--agent-badge-bg`. A small robot icon overlay in the bottom-right corner distinguishes agents from humans at a glance.
- **No profile photos in v1.** Initials-based avatars keep the design consistent and avoid image loading latency.

### Form Inputs

All form inputs use Vuetify's outlined variant with the Mission Control theme:

- Background: `--surface-sunken`
- Border: `--border-default`, transitions to `--border-focus` on focus
- Labels: Above the input (floating label pattern), `--text-secondary` color
- Error state: Border becomes `--action-destructive`, error text below in `--action-destructive`
- Disabled state: Background lightens, text becomes `--text-tertiary`, cursor `not-allowed`

### Loading States

- **Page-level loading:** Centered spinner with "Loading..." text. Spinner uses `--action-primary` color.
- **Inline loading:** Button text replaced with a small spinner when an action is in progress. Button is disabled during loading.
- **Skeleton screens:** Used for initial page loads only. Gray rectangular placeholders matching the layout of the expected content. Subtle pulse animation (`opacity` oscillation, not shimmer).
- **No full-page loading overlays.** Loading state is always scoped to the component that is loading.

---

## Motion

### Principles

Motion is functional, not decorative. Every animation serves one of:

- **Feedback:** Confirming an action happened (toast appearing, card moving between columns).
- **Orientation:** Helping the user understand spatial relationships (slide-over entering from the right, dialog scaling up from center).
- **Continuity:** Smoothing transitions between states (status badge color change, progress bar advancing).

### Duration Scale

| Token | Duration | Usage |
|-------|----------|-------|
| `--duration-instant` | 100ms | Badge color changes, hover states |
| `--duration-fast` | 150ms | Dropdown open/close, tooltip appear |
| `--duration-normal` | 250ms | Dialog open/close, card movement on Kanban board |
| `--duration-slow` | 350ms | Slide-over panel enter/exit, page transitions |

### Easing

All animations use `cubic-bezier(0.4, 0, 0.2, 1)` (Material Design standard easing). No bouncing, no elastic effects, no spring physics.

### Reduced Motion

All animations respect `prefers-reduced-motion: reduce`. When active, durations are set to `0ms` (instant state changes, no animation). Functionality is never affected.

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## Accessibility Checklist

Every component and view must meet these requirements before merge:

| Requirement | Standard | Verification |
|-------------|----------|--------------|
| Color contrast (text) | WCAG AA: 4.5:1 minimum | Automated check in CI via axe-core |
| Color contrast (large text) | WCAG AA: 3:1 minimum | Automated |
| Color not sole indicator | Status/priority uses color + icon or text | Manual review |
| Keyboard navigation | All interactions reachable via Tab, Enter, Escape, Arrow keys | Manual testing |
| Focus visible | Focus ring (`--border-focus`, 2px offset) on all interactive elements | Visual inspection |
| Screen reader labels | All icon-only buttons have `aria-label`, all images have `alt` | Automated (axe-core) |
| Dialog focus trap | Focus stays within open dialog, returns to trigger on close | Manual testing |
| Live regions | New chat messages and notifications use `aria-live="polite"` | Manual testing |
| Form labels | All inputs have associated `<label>` elements | Automated |
| Error identification | Form errors are associated with inputs via `aria-describedby` | Automated |

### Automated Accessibility Testing

axe-core is integrated into the E2E test suite. Every Playwright test includes an accessibility scan:

```typescript
import AxeBuilder from '@axe-core/playwright'

test('project board is accessible', async ({ page }) => {
  await page.goto('/orgs/test-org/projects')
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations).toEqual([])
})
```

CI fails if any accessibility violation is detected.

---

## Do / Don't Reference

| Do | Don't |
|----|-------|
| Show all actions on cards and rows at all times | Hide actions behind hover states |
| Use dialogs for focused decisions and confirmations | Use dialogs to display read-only information |
| Use slide-over panels for detail views | Use full-page navigation for viewing a single resource's details |
| Use color + icon + text for status indicators | Use color alone to convey meaning |
| Keep menus to 8 items or fewer | Create deeply nested submenus |
| Use one primary action per view context | Show multiple competing primary buttons |
| Use toast notifications for transient feedback | Use toasts for actions or important errors that need acknowledgment |
| Show empty states with a clear action | Show a blank page with no guidance |
| Use outlined inputs with visible labels | Use placeholder text as the only label |
| Respect `prefers-reduced-motion` | Force animations on all users |
| Use `--surface-elevated` (white) for floating elements | Use colored backgrounds for cards and dialogs |
| Use Roboto at 14px (`--text-body`) as the default | Use text smaller than 12px anywhere |
