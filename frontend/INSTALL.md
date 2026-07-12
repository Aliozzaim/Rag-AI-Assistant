# Installation Guide

## Prerequisites

- Node.js 18+ and npm/yarn
- FastAPI backend running on `http://localhost:8000`

## Setup Steps

1. **Install dependencies:**
```bash
cd frontend
yarn install
# or
npm install
```

2. **Create environment file:**
```bash
cp .env.example .env
```

3. **Update `.env` with your configuration:**
```
VITE_API_URL=http://localhost:8000
VITE_API_KEY=replace-with-your-api-key
```

4. **Start development server:**
```bash
yarn dev
# or
npm run dev
```

The app will be available at `http://localhost:3000`

## HDS Components Used

- `hds-textarea` - Chat input field
- `hds-button` - Send button
- `hds-spinner` - Loading indicator
- `hds-section-message` - Error messages
- `hds-card` - Message containers (in ChatMessage component)

## Build for Production

```bash
yarn build
# or
npm run build
```

Output will be in the `dist` directory.
