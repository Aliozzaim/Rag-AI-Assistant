# AI Frontend

Vue 3 frontend for the AI Assistant chat interface with HDS (Hades Design System) UI toolkit support.

## Setup

1. **Install dependencies:**

```bash
cd frontend
yarn install
# or
npm install
```

2. **Registry Configuration:**

The project uses a dual-registry setup:

- **Public packages** (vue, axios, vite) → `https://registry.npmjs.org/`

This is configured in `.npmrc` file. If you need to authenticate with Artifactory:

```bash
# Add to .npmrc:
# //artifactory.internalsecure.com/artifactory/api/npm/npm/:_authToken=YOUR_TOKEN
# //artifactory.internalsecure.com/artifactory/api/npm/npm/:always-auth=true
```

3. **Create environment file:**

```bash
cp .env.example .env
```

4. **Update `.env` with your API configuration:**

```
VITE_API_URL=http://localhost:8000
VITE_API_KEY=replace-with-your-api-key
```

## Development

Run the development server:

```bash
yarn dev
# or
npm run dev
```

The app will be available at `http://localhost:3000`

## Build

Build for production:

```bash
yarn build
# or
npm run build
```

The built files will be in the `dist` directory.

## Features

- ✅ Vue 3 Composition API with `<script setup>`
- ✅ Hades Design System components integrated
- ✅ Real-time chat interface
- ✅ Conversation memory support (automatic conversation_id)
- ✅ Source citations display
- ✅ Loading states with HDS spinner
- ✅ Error handling with HDS components
- ✅ Responsive design
- ✅ Auto-resizing textarea
- ✅ Keyboard shortcuts (Enter to send, Shift+Enter for new line)

## Troubleshooting

### Installation Issues

**If yarn/npm install fails:**

1. Check your network connection
2. Verify Artifactory authentication (if required)
3. Try clearing cache: `yarn cache clean` or `npm cache clean --force`
4. Delete `node_modules` and `yarn.lock`/`package-lock.json` and retry

**If Artifactory authentication fails:**

- Get your auth token from Artifactory
- Add it to `.npmrc` as shown above
- Or use `yarn config set` commands

## Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   └── ChatMessage.vue    # Chat message component
│   ├── services/
│   │   └── api.js             # API service layer
│   ├── App.vue                # Main app component
│   ├── main.js                # App entry point (Hades setup)
│   └── style.css              # Global styles
├── .npmrc                     # Registry configuration
├── index.html                 # HTML template
├── package.json               # Dependencies
├── vite.config.js             # Vite configuration
└── README.md                  # This file
```
