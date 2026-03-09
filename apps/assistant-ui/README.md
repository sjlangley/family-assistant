# Family Assistant UI

Frontend for the Family Assistant application. Implements Google OAuth authentication with the backend API.

## Technology Stack

- **Vite** - Build tool and dev server
- **React 18** - UI framework
- **TypeScript** - Type safety
- **Tailwind CSS** - Styling
- **Vitest** - Testing framework
- **ESLint** - Linting
- **Prettier** - Code formatting
- **Google Identity Services** - Authentication

## Prerequisites

- Node.js 22+
- npm 10+
- Backend API running (see `apps/assistant-backend`)
- Google OAuth 2.0 Client ID

## Setup

1. **Install dependencies:**

```bash
npm install
```

2. **Configure environment variables:**

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```
VITE_API_BASE_URL=http://localhost:8000
VITE_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
```

## Development

Start the development server:

```bash
npm run dev
```

The app will be available at `http://localhost:5173`

## Testing

Run tests:

```bash
npm run test
```

Run tests with coverage:

```bash
npm run test:coverage
```

Watch mode for development:

```bash
npm run test:watch
```

Coverage requirements: >80%

## Code Quality

Lint code:

```bash
npm run lint
```

Format code:

```bash
npm run format
```

Check formatting without modifying files:

```bash
npm run format:check
```

Type checking:

```bash
npm run typecheck
```

## Build

Build for production:

```bash
npm run build
```

Preview production build:

```bash
npm run preview
```

## Authentication Flow

### Startup

1. App displays loading state
2. Calls `GET /user/current` to check auth status
3. If authenticated (200): shows user info
4. If not authenticated (401): shows login button

### Login

1. User clicks Google Sign-In button
2. Google Identity Services obtains ID token
3. Frontend sends token to `POST /auth/login` with `Authorization: Bearer <token>`
4. Backend verifies token and creates session
5. Backend sets session cookie
6. Frontend calls `GET /user/current` to get user data
7. Frontend updates state to authenticated

### Session Management

- All API requests include `credentials: 'include'` to send session cookie
- Backend is source of truth for authentication
- If any request returns 401, frontend clears auth state

### Logout

1. User clicks logout button
2. Frontend calls `POST /auth/logout`
3. Backend clears session
4. Frontend updates state to unauthenticated

## File Structure

```
src/
├── lib/
│   ├── api.ts            # Backend API client
│   └── auth.tsx          # Auth state management (React Context)
├── components/
│   └── GoogleSignInButton.tsx  # Google Sign-In button
├── types/
│   ├── api.ts            # API type definitions
│   └── google.d.ts       # Google Identity Services types
├── App.tsx               # Main app component
├── App.test.tsx          # App tests
├── main.tsx              # Entry point
└── index.css             # Global styles
```

## UI States

### Loading

Displayed while checking authentication status on app startup.

### Logged Out

- Title: "Family Assistant"
- Google Sign-In button

### Logged In

- Title: "Family Assistant"
- User information (email, name, user ID)
- Logout button

## Docker

**Important:** Vite environment variables (`VITE_*`) are baked into the bundle at **build time**, not runtime. You must pass configuration values when building the image, not when running the container.

Build with configuration:

```bash
docker build \
  --build-arg VITE_API_BASE_URL=http://localhost:8000 \
  --build-arg VITE_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com \
  -t assistant-ui .
```

Run:

```bash
docker run --rm -p 3000:3000 assistant-ui
```

**Note:** The values are compiled into the static bundle during `docker build`. If you need different configuration, you must rebuild the image with new `--build-arg` values.

## Notes

- Frontend does NOT read or parse session cookies
- Frontend does NOT use localStorage for auth
- Backend handles all authentication verification
- Google ID token (credential) is used, not OAuth access tokens
