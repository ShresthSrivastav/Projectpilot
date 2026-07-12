# ProjectPilot Frontend Migration Plan

## Streamlit → React + Next.js 15

---

## 1. Tech Stack

| Layer | Choice |
|-------|--------|
| Framework | **Next.js 15** (App Router, React Server Components) |
| UI Library | **React 19** |
| Language | **TypeScript 5** (strict mode) |
| Styling | **Tailwind CSS 4** + `tailwindcss-animate` |
| Components | **shadcn/ui** (fully customized) |
| Icons | **Lucide React** |
| Animations | **Framer Motion** (only where it improves UX) |
| Server State | **TanStack Query v5** |
| Client State | **Zustand** (auth, UI preferences) |
| Forms | **React Hook Form + Zod** |
| Charts | **Recharts** (lightweight) |
| Code Editor | **Monaco Editor** (`@monaco-editor/react`) |
| Markdown | **react-markdown** + `react-syntax-highlighter` |
| Theme | **next-themes** (dark-primary, light-secondary) |
| Search | **cmdk** (command palette via `⌘K`) |
| Toasts | **sonner** |
| URL State | **nuqs** |
| Dates | **date-fns** |

---

## 2. Directory Structure

```
frontend/
├── app/
│   ├── (auth)/
│   │   ├── login/
│   │   │   └── page.tsx
│   │   └── register/
│   │       └── page.tsx
│   ├── (dashboard)/
│   │   ├── layout.tsx              # AppShell with sidebar + topnav
│   │   ├── page.tsx                # Redirect → /dashboard
│   │   ├── dashboard/
│   │   │   └── page.tsx
│   │   ├── generate/
│   │   │   ├── page.tsx            # New generation form
│   │   │   └── [jobId]/
│   │   │       ├── page.tsx        # Live generation stream
│   │   │       └── review/
│   │   │           └── page.tsx    # Validation + tests + review
│   │   ├── history/
│   │   │   ├── page.tsx            # Project list
│   │   │   └── [jobId]/
│   │   │       └── page.tsx        # Project detail + files
│   │   ├── chat/
│   │   │   ├── page.tsx            # New conversation
│   │   │   └── [conversationId]/
│   │   │       └── page.tsx        # Active conversation
│   │   ├── workspace/
│   │   │   ├── page.tsx            # Members + activity
│   │   │   ├── settings/
│   │   │   │   └── page.tsx
│   │   │   └── github/
│   │   │       └── page.tsx
│   │   ├── analytics/
│   │   │   └── page.tsx
│   │   ├── benchmarks/
│   │   │   ├── page.tsx
│   │   │   └── [runId]/
│   │   │       └── page.tsx
│   │   ├── evaluation/
│   │   │   └── page.tsx
│   │   ├── organization/
│   │   │   └── page.tsx
│   │   ├── ecosystem/
│   │   │   ├── page.tsx
│   │   │   ├── plugins/
│   │   │   │   └── page.tsx
│   │   │   ├── marketplace/
│   │   │   │   └── page.tsx
│   │   │   ├── agents/
│   │   │   │   └── page.tsx
│   │   │   └── workflows/
│   │   │       └── page.tsx
│   │   └── settings/
│   │       ├── page.tsx            # Profile
│   │       ├── appearance/
│   │       │   └── page.tsx
│   │       ├── api-keys/
│   │       │   └── page.tsx
│   │       └── notifications/
│   │           └── page.tsx
│   ├── layout.tsx                  # Root: providers, fonts, theme
│   └── globals.css                 # Tailwind + design tokens
│
├── components/
│   ├── ui/                         # shadcn/ui primitives (button, input, dialog, etc.)
│   ├── layout/
│   │   ├── app-shell.tsx           # Sidebar + topnav + main content
│   │   ├── sidebar.tsx             # Collapsible sidebar
│   │   ├── top-nav.tsx             # Breadcrumbs, search, notifications, user menu
│   │   ├── workspace-switcher.tsx
│   │   └── command-palette.tsx     # ⌘K search
│   ├── chat/
│   │   ├── chat-layout.tsx
│   │   ├── conversation-list.tsx
│   │   ├── message-bubble.tsx
│   │   ├── chat-input.tsx
│   │   ├── thinking-timeline.tsx   # Reasoning/realtime agent thought display
│   │   ├── streaming-text.tsx
│   │   ├── suggested-questions.tsx
│   │   └── typing-indicator.tsx
│   ├── projects/
│   │   ├── project-card.tsx
│   │   ├── status-pill.tsx
│   │   ├── agent-pipeline.tsx      # 8-agent live progress
│   │   ├── file-tree.tsx
│   │   ├── code-viewer.tsx         # Monaco wrapper
│   │   ├── test-result-bar.tsx
│   │   ├── validation-report.tsx
│   │   └── mermaid-diagram.tsx     # Interactive Mermaid renderer
│   ├── analytics/
│   │   ├── stat-card.tsx
│   │   ├── metric-chart.tsx
│   │   ├── leaderboard-table.tsx
│   │   └── comparison-table.tsx
│   ├── workspace/
│   │   ├── member-list.tsx
│   │   ├── invite-dialog.tsx
│   │   ├── activity-feed.tsx
│   │   ├── github-repo-list.tsx
│   │   └── github-file-explorer.tsx
│   ├── ecosystem/
│   │   ├── plugin-card.tsx
│   │   ├── marketplace-grid.tsx
│   │   ├── agent-card.tsx
│   │   └── workflow-builder.tsx
│   └── shared/
│       ├── loading-skeleton.tsx
│       ├── empty-state.tsx
│       ├── error-boundary.tsx
│       ├── page-header.tsx
│       ├── data-table.tsx
│       └── confirm-dialog.tsx
│
├── lib/
│   ├── api/
│   │   ├── client.ts              # Axios/fetch instance with JWT interceptor
│   │   ├── auth.ts                # Auth endpoints
│   │   ├── pipeline.ts            # Generate, status, iterate, etc.
│   │   ├── chat.ts
│   │   ├── workspace.ts
│   │   ├── github.ts
│   │   ├── analytics.ts
│   │   ├── benchmarks.ts
│   │   ├── evaluation.ts
│   │   ├── organization.ts
│   │   └── ecosystem.ts
│   ├── hooks/
│   │   ├── use-auth.ts
│   │   ├── use-workspace.ts
│   │   ├── use-job-polling.ts     # Polling hook for generation status
│   │   ├── use-chat.ts
│   │   ├── use-dashboard-stream.ts # WebSocket hook
│   │   ├── use-debounce.ts
│   │   ├── use-hotkeys.ts
│   │   └── use-media-query.ts
│   ├── stores/
│   │   ├── auth-store.ts          # Zustand: tokens, user, workspace
│   │   └── ui-store.ts            # Zustand: sidebar, theme, panels
│   └── utils/
│       ├── cn.ts                  # clsx + tailwind-merge
│       ├── formatters.ts          # dates, numbers, durations
│       ├── constants.ts           # API_URL, POLL_INTERVAL, etc.
│       └── validators.ts          # Zod schemas shared with forms
│
├── styles/
│   └── globals.css                # Tailwind directives, CSS variables, fonts
│
├── public/
│   ├── favicon.ico
│   └── logo.svg
│
├── next.config.ts
├── tailwind.config.ts
├── tsconfig.json
├── package.json
└── components.json                # shadcn/ui config
```

---

## 3. Design System

### 3.1 Color Palette

```css
/* Dark theme (primary) */
--background:       #0a0a0b
--foreground:       #fafafa
--card:             #121213
--card-hover:       #1a1a1d
--popover:          #121213
--muted:            #27272a
--muted-foreground: #a1a1aa
--border:           #27272a
--ring:             #3b82f6

/* Primary (blue) */
--primary:          #3b82f6
--primary-foreground: #ffffff
--primary-muted:    #1d4ed8

/* Accent (purple) */
--accent:           #8b5cf6
--accent-foreground: #ffffff
--accent-muted:     #6d28d9

/* Semantic */
--success:          #22c55e
--warning:          #f59e0b
--error:            #ef4444
--info:             #3b82f6

/* Chart colors */
--chart-1:          #3b82f6   /* blue */
--chart-2:          #8b5cf6   /* purple */
--chart-3:          #22c55e   /* green */
--chart-4:          #f59e0b   /* amber */
--chart-5:          #ef4444   /* red */
```

### 3.2 Typography

| Element | Family | Weight | Size |
|---------|--------|--------|------|
| Headings | Inter | 600-700 | text-3xl to text-6xl |
| Body | Inter | 400-500 | text-sm to text-base |
| Small | Inter | 400-500 | text-xs |
| Code | JetBrains Mono | 400 | text-sm |

### 3.3 Spacing & Radius

```
Spacing scale: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64
Border radius: sm=6px, md=8px, lg=12px, xl=16px, full=9999px
Section padding: p-6 (cards), p-8 (page sections)
```

### 3.4 Shadows (Dark Theme)

```css
shadow-sm:    0 1px 2px rgba(0,0,0,0.3)
shadow-md:    0 4px 6px rgba(0,0,0,0.4)
shadow-lg:    0 10px 25px rgba(0,0,0,0.5)
shadow-xl:    0 20px 50px rgba(0,0,0,0.6)
shadow-glow:  0 0 20px rgba(59,130,246,0.15)
shadow-accent: 0 0 20px rgba(139,92,246,0.15)
```

---

## 4. Layout Architecture

```
┌────────────────────────────────────────────────┐
│  Top Nav: [WS] Breadcrumbs | ⌘K | 🔔 | 👤    │
├──────────┬─────────────────────────────────────┤
│ Sidebar  │  Main Content (scrollable)          │
│          │                                     │
│ Logo     │  ┌─ Page Header ─────────────────┐  │
│ Dashboard│  │ [Title]              [Actions] │  │
│ Generate │  ├───────────────────────────────┤  │
│ History  │  │                               │  │
│ Chat     │  │   Content                     │  │
│ ───────  │  │                               │  │
│ Workspace│  │                               │  │
│ Analytics│  │                               │  │
│ Benchmarks│ └───────────────────────────────┘  │
│ Eval     │                                     │
│ Org      │                                     │
│ Ecosystem│                                     │
│ Settings │                                     │
│          │                                     │
└──────────┴─────────────────────────────────────┘
```

- **Sidebar**: Collapsible (icons-only / icon+label), sections with dividers
- **Top Nav**: Workspace switcher, breadcrumbs, global search, notifications, user menu
- **Command Palette (⌘K)**: Global search across projects, conversations, pages, actions

---

## 5. Page Summaries

### 5.1 Auth (`/login`, `/register`)
Centered card on gradient background. Email/password form with Zod validation. Toggle between login and register. Password strength indicator. Animated transition to dashboard.

### 5.2 Dashboard (`/dashboard`)
Stat cards (projects, active jobs, files, tokens, avg duration), recent activity feed, agent pipeline status sidebar, resource usage bars, recent benchmarks, quick action buttons. WebSocket for real-time updates.

### 5.3 Generate (`/generate`, `/generate/[jobId]`)
3-step wizard: Configure -> Generate -> Review.
- **Configure**: Project name, prompt, stack config (backend/frontend/DB/CSS/testing/ORM/auth/deploy), clarify button
- **Generate**: Agent pipeline progress (8 agents), live file tree, log viewer, cancel. Polls `/status/{jobId}`
- **Review**: Validation badges, test results bar, file browser with Monaco, AI review, iterate/download actions

### 5.4 Chat (`/chat`, `/chat/[id]`)
Left sidebar: conversation list grouped by date. Main: streaming messages, markdown + code blocks with syntax highlighting, copy button, thinking timeline (expandable agent reasoning). Suggested questions on empty. Multi-line input. Keyboard shortcuts.

### 5.5 History (`/history`, `/history/[jobId]`)
Searchable/filterable data table. Click to detail: file tree + Monaco viewer, changelog, download, delete, re-run.

### 5.6 Workspace (`/workspace/*`)
Members list with roles, invite dialog, activity feed (infinite scroll), GitHub integration (repo browser, branch mgmt, file editor, PR/issue management, AI PR review).

### 5.7 Analytics (`/analytics`)
Stat cards, timeline charts (projects, tokens, test results), per-project breakdown, date range picker.

### 5.8 Benchmarks (`/benchmarks/*`)
Run benchmarks, results table, leaderboard, trends chart, side-by-side comparison.

### 5.9 Evaluation (`/evaluation`)
Tabs: History, Trends, Regressions, Leaderboards, Comparisons. Filterable, chart-heavy.

### 5.10 Organization (`/organization`)
Multi-repo graph (Mermaid), repo health, impact analysis, cross-repo changes, validation.

### 5.11 Ecosystem (`/ecosystem/*`)
Plugins list, marketplace browser, custom agents, workflow builder, ecosystem health.

### 5.12 Settings (`/settings/*`)
Profile, appearance (theme, font size), API keys, notification preferences.

---

## 6. Auth Flow

1. Login/Register -> JWT access + refresh tokens
2. Tokens stored in Zustand + refresh token in localStorage
3. API client adds `Authorization: Bearer` header
4. On 401 -> attempt `/api/auth/refresh` -> retry or redirect to `/login`
5. On app load -> check localStorage -> attempt refresh -> restore or show login

---

## 7. Animation Philosophy (Framer Motion)

| Component | Animation | Duration |
|-----------|-----------|----------|
| Page transitions | fade + slide up | 150ms |
| Cards | scale on hover | 150ms |
| Modal/Dialog | scale + fade | 200ms |
| Sidebar | width slide | 200ms |
| Stat counters | number animation | 300ms |
| Skeletons | shimmer pulse | 1.5s loop |
| Streaming text | typewriter | per char |
| Toast | slide in from right | 200ms |

No bounce, no spring, no effects over 300ms. Professional and subtle.

---

## 8. Every Component Must Handle

- **Loading**: Skeleton shimmer
- **Empty**: Illustration + message + CTA
- **Error**: Error illustration + message + retry button
- **Success**: Normal data display

---

## 9. Implementation Phases

| Phase | Scope | Estimate |
|-------|-------|----------|
| **1** | Scaffold Next.js 15 + Tailwind 4 + shadcn/ui + design system + layout shell + auth pages + API client | 3-4 days |
| **2** | Dashboard + Generate wizard + History + Project detail + Code viewer + Agent pipeline | 4-5 days |
| **3** | AI Chat (full-page, streaming, conversations, thinking timeline) | 3-4 days |
| **4** | Workspace (members, GitHub) + Settings (profile, appearance, API keys) | 3-4 days |
| **5** | Analytics + Benchmarks + Evaluation + Organization | 3-4 days |
| **6** | Ecosystem (plugins, marketplace, agents, workflows) + Command palette | 2-3 days |
| **7** | Responsive QA, accessibility audit, performance tuning, dark/light finalization | 2-3 days |
| **Total** | | **20-27 days** |

---

## 10. Design Inspiration

- **Cursor**: Editor polish, agent visualization
- **Linear**: Sidebar design, keyboard shortcuts, command palette
- **Vercel**: Dark theme, typography, spacing
- **Claude**: Chat UI, thinking timeline, code blocks
- **GitHub Copilot**: Chat-in-editor integration
- **Raycast**: Command palette UX, search
- **Warp**: Terminal aesthetics, modern developer feel
- **Notion**: Content editing, block-based layout
