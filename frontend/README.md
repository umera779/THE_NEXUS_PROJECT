# Legacy Portal Frontend (Next.js)

## Setup

1. Install dependencies:
   ```bash
   npm install
   ```

2. Configure environment:
   ```bash
   cp .env.example .env.local
   ```

3. Start development server:
   ```bash
   npm run dev
   ```

## API Base URL

- `NEXT_PUBLIC_API_BASE_URL` defaults to `http://localhost:8000`.
- The frontend uses cookie-based auth and sends requests with `credentials: include`.
