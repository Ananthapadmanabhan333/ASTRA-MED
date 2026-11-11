# ASTRA-MED dashboard

Next.js 16 (App Router, Cache Components), TypeScript, Tailwind CSS v4, shadcn/ui, Recharts,
TanStack Query and zustand. All data comes from the ASTRA-MED API and is simulated.

```bash
npm install
npm run dev        # http://localhost:3000, expects the API at NEXT_PUBLIC_API_URL (default http://localhost:8000)
npm test           # unit tests (vitest)
npm run typecheck
npm run gen:api    # regenerate src/lib/api/schema.d.ts from ../backend/openapi.json
```

See the [root README](../README.md) and [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).
