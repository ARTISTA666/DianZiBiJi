# Frontend — Next.js & TypeScript

The user interface for the Electronic Lab Notebook (ELN) system, built with Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS, and Zustand.

## Tech Stack

- **Framework**: Next.js 16 (App Router), React 19
- **State Management**: Zustand 5
- **UI & Components**: Tailwind CSS 3.4, Shadcn UI / Radix UI primitives, Lucide React icons
- **Visualization**: D3.js, `react-force-graph-2d` (Knowledge Graph & Blueprint rendering)
- **API Contract**: Strongly typed from OpenAPI 3.1 schema generated from the Rust backend
- **Notifications**: Sonner

## Development

```bash
cd frontend
npm install

# Start development server
npm run dev

# Code quality checks
npm run lint
npm run typecheck
npm run build
```

## API Contract Generation

Whenever the backend OpenAPI schema (`backend/openapi.json`) changes:

```bash
npm run generate:api
```

This updates `src/lib/api-schema.d.ts`. Any schema diffs must be committed together with backend changes.

## Directory Structure

| Path | Description |
| :--- | :--- |
| `src/app/` | App Router pages, dashboard layouts, route guards |
| `src/components/` | Knowledge graph visualizer, blueprint schemas, project alerts |
| `src/components/shared/` | TopNav, MainNav, AgentAssistant, AuditTable |
| `src/components/ui/` | Reusable Radix / Tailwind UI primitives |
| `src/lib/` | API client, contract guards, citation parser, utility functions |
| `src/stores/` | Zustand state slices (projects, notes, files, AI, authentication) |
| `e2e/` | Playwright end-to-end integration tests |
