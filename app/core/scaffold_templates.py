"""
Project scaffold templates.
Generates real, runnable project structures.

Templates:
- nextjs_web: Next.js + TypeScript + ESLint
- fastapi_api: FastAPI + pytest skeleton
- fullstack_nextjs_fastapi: Combined web/ and api/ folders

Security:
- No shell execution
- All content is static strings
- No secrets in templates
"""
from datetime import datetime

# =============================================================================
# Next.js Web Template
# =============================================================================

def generate_nextjs_web(project_name: str, use_docker: bool = False, include_ci: bool = False) -> dict[str, str]:
    """Generate Next.js + TypeScript + ESLint project."""
    year = datetime.now().year
    files = {}
    
    # package.json
    files["package.json"] = f'''{{
  "name": "{project_name}",
  "version": "0.1.0",
  "private": true,
  "scripts": {{
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint"
  }},
  "dependencies": {{
    "next": "14.2.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  }},
  "devDependencies": {{
    "@types/node": "^20",
    "@types/react": "^18",
    "@types/react-dom": "^18",
    "eslint": "^8",
    "eslint-config-next": "14.2.0",
    "typescript": "^5"
  }}
}}
'''
    
    # tsconfig.json
    files["tsconfig.json"] = '''{
  "compilerOptions": {
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [
      {
        "name": "next"
      }
    ],
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
'''
    
    # next.config.mjs
    files["next.config.mjs"] = '''/** @type {import(\'next\').NextConfig} */
const nextConfig = {};

export default nextConfig;
'''
    
    # .eslintrc.json
    files[".eslintrc.json"] = '''{
  "extends": "next/core-web-vitals"
}
'''
    
    # .gitignore
    files[".gitignore"] = '''# Dependencies
/node_modules
/.pnp
.pnp.js

# Testing
/coverage

# Next.js
/.next/
/out/

# Production
/build

# Misc
.DS_Store
*.pem

# Debug
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# Local env files
.env*.local

# Vercel
.vercel

# TypeScript
*.tsbuildinfo
next-env.d.ts
'''
    
    # next-env.d.ts
    files["next-env.d.ts"] = '''/// <reference types="next" />
/// <reference types="next/image-types/global" />

// NOTE: This file should not be edited
// see https://nextjs.org/docs/basic-features/typescript for more information.
'''
    
    # src/app/layout.tsx
    files["src/app/layout.tsx"] = f'''import type {{ Metadata }} from "next";
import "./globals.css";

export const metadata: Metadata = {{
  title: "{project_name}",
  description: "Generated with agent-service scaffold",
}};

export default function RootLayout({{
  children,
}}: Readonly<{{
  children: React.ReactNode;
}}>) {{
  return (
    <html lang="en">
      <body>{{children}}</body>
    </html>
  );
}}
'''
    
    # src/app/globals.css
    files["src/app/globals.css"] = '''* {
  box-sizing: border-box;
  padding: 0;
  margin: 0;
}

html,
body {
  max-width: 100vw;
  overflow-x: hidden;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

a {
  color: inherit;
  text-decoration: none;
}
'''
    
    # src/app/page.tsx
    files["src/app/page.tsx"] = f'''export default function Home() {{
  return (
    <main style={{{{ padding: "2rem" }}}}>
      <h1>Welcome to {project_name}</h1>
      <p>Get started by editing <code>src/app/page.tsx</code></p>
    </main>
  );
}}
'''
    
    # README.md
    files["README.md"] = f'''# {project_name}

A Next.js project generated with agent-service scaffold.

## Getting Started

```bash
# Install dependencies
npm install

# Run development server
npm run dev

# Build for production
npm run build

# Start production server
npm start
```

Open [http://localhost:3000](http://localhost:3000) to see your app.

## Project Structure

```
{project_name}/
├── src/
│   └── app/
│       ├── layout.tsx    # Root layout
│       ├── page.tsx      # Home page
│       └── globals.css   # Global styles
├── package.json
├── tsconfig.json
└── next.config.mjs
```

## Learn More

- [Next.js Documentation](https://nextjs.org/docs)
- [React Documentation](https://react.dev)

Generated on {datetime.now().strftime("%Y-%m-%d")} by agent-service.
'''
    
    # Optional: Docker
    if use_docker:
        files["Dockerfile"] = f'''FROM node:20-alpine AS base

# Install dependencies only when needed
FROM base AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

# Build the application
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# Production image
FROM base AS runner
WORKDIR /app
ENV NODE_ENV production

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
ENV PORT 3000

CMD ["node", "server.js"]
'''
        
        files[".dockerignore"] = '''node_modules
.next
.git
.gitignore
README.md
Dockerfile
.dockerignore
'''
    
    # Optional: GitHub Actions CI
    if include_ci:
        files[".github/workflows/ci.yml"] = f'''name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - name: Install dependencies
        run: npm ci

      - name: Lint
        run: npm run lint

      - name: Build
        run: npm run build
'''
    
    return files


# =============================================================================
# FastAPI API Template
# =============================================================================

def generate_fastapi_api(project_name: str, use_docker: bool = False, include_ci: bool = False) -> dict[str, str]:
    """Generate FastAPI + pytest project."""
    year = datetime.now().year
    # Convert project name to valid Python package name
    package_name = project_name.lower().replace("-", "_")
    files = {}
    
    # requirements.txt
    files["requirements.txt"] = '''fastapi>=0.109.0
uvicorn[standard]>=0.27.0
pydantic>=2.5.0
python-dotenv>=1.0.0
'''
    
    # requirements-dev.txt
    files["requirements-dev.txt"] = '''pytest>=8.0.0
pytest-asyncio>=0.23.0
httpx>=0.26.0
ruff>=0.2.0
'''
    
    # pyproject.toml
    files["pyproject.toml"] = f'''[project]
name = "{project_name}"
version = "0.1.0"
description = "FastAPI application generated with agent-service scaffold"
requires-python = ">=3.10"

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "W"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
'''
    
    # .gitignore
    files[".gitignore"] = '''# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
.env
.venv
env/
venv/
ENV/

# IDE
.idea/
.vscode/
*.swp
*.swo

# Testing
.coverage
htmlcov/
.tox/
.pytest_cache/

# mypy
.mypy_cache/
'''
    
    # Main application
    files["app/__init__.py"] = '''"""FastAPI application package."""
'''
    
    files["app/main.py"] = f'''"""
{project_name} - FastAPI Application
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router

app = FastAPI(
    title="{project_name}",
    description="FastAPI application generated with agent-service scaffold",
    version="0.1.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api")


@app.get("/health")
def health():
    """Health check endpoint."""
    return {{"status": "ok"}}


@app.get("/")
def root():
    """Root endpoint."""
    return {{"message": "Welcome to {project_name}"}}
'''
    
    # API routes
    files["app/api/__init__.py"] = '''"""API routes package."""
from fastapi import APIRouter

from app.api.items import router as items_router

router = APIRouter()
router.include_router(items_router, prefix="/items", tags=["items"])
'''
    
    files["app/api/items.py"] = '''"""Items API endpoints."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class Item(BaseModel):
    """Item model."""
    id: int
    name: str
    description: str | None = None


# In-memory storage for demo
items_db: dict[int, Item] = {}
_next_id = 1


@router.get("/")
def list_items() -> list[Item]:
    """List all items."""
    return list(items_db.values())


@router.get("/{item_id}")
def get_item(item_id: int) -> Item:
    """Get item by ID."""
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")
    return items_db[item_id]


@router.post("/", status_code=201)
def create_item(name: str, description: str | None = None) -> Item:
    """Create a new item."""
    global _next_id
    item = Item(id=_next_id, name=name, description=description)
    items_db[item.id] = item
    _next_id += 1
    return item


@router.delete("/{item_id}")
def delete_item(item_id: int) -> dict:
    """Delete an item."""
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")
    del items_db[item_id]
    return {"deleted": True}
'''
    
    # Tests
    files["tests/__init__.py"] = '''"""Test package."""
'''
    
    files["tests/test_api.py"] = '''"""API tests."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


def test_health(client):
    """Test health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root(client):
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()


def test_create_and_get_item(client):
    """Test creating and retrieving an item."""
    # Create
    response = client.post("/api/items/?name=TestItem&description=Test")
    assert response.status_code == 201
    item = response.json()
    assert item["name"] == "TestItem"
    
    # Get
    response = client.get(f"/api/items/{item['id']}")
    assert response.status_code == 200
    assert response.json()["name"] == "TestItem"


def test_list_items(client):
    """Test listing items."""
    response = client.get("/api/items/")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_item_not_found(client):
    """Test getting non-existent item."""
    response = client.get("/api/items/99999")
    assert response.status_code == 404
'''
    
    # README.md
    files["README.md"] = f'''# {project_name}

A FastAPI application generated with agent-service scaffold.

## Getting Started

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\\Scripts\\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt  # For development

# Run development server
uvicorn app.main:app --reload

# Run tests
pytest
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) to see the API documentation.

## Project Structure

```
{project_name}/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI application
│   └── api/
│       ├── __init__.py   # API router
│       └── items.py      # Items endpoints
├── tests/
│   ├── __init__.py
│   └── test_api.py       # API tests
├── requirements.txt
├── requirements-dev.txt
└── pyproject.toml
```

## API Endpoints

- `GET /` - Root endpoint
- `GET /health` - Health check
- `GET /api/items/` - List items
- `POST /api/items/` - Create item
- `GET /api/items/{{id}}` - Get item
- `DELETE /api/items/{{id}}` - Delete item

## Learn More

- [FastAPI Documentation](https://fastapi.tiangolo.com)
- [Pydantic Documentation](https://docs.pydantic.dev)

Generated on {datetime.now().strftime("%Y-%m-%d")} by agent-service.
'''
    
    # Optional: Docker
    if use_docker:
        files["Dockerfile"] = f'''FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/

# Create non-root user
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
'''
        
        files[".dockerignore"] = '''__pycache__
*.pyc
*.pyo
.git
.gitignore
README.md
Dockerfile
.dockerignore
venv/
.env
tests/
'''
    
    # Optional: GitHub Actions CI
    if include_ci:
        files[".github/workflows/ci.yml"] = f'''name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Lint with ruff
        run: ruff check .

      - name: Run tests
        run: pytest -v
'''
    
    return files


# =============================================================================
# Fullstack Template (Next.js + FastAPI)
# =============================================================================

def generate_fullstack(project_name: str, use_docker: bool = False, include_ci: bool = False) -> dict[str, str]:
    """Generate fullstack project with Next.js frontend and FastAPI backend."""
    files = {}
    
    # Generate web (Next.js) files with web/ prefix
    web_files = generate_nextjs_web(project_name, use_docker=False, include_ci=False)
    for path, content in web_files.items():
        files[f"web/{path}"] = content
    
    # Generate api (FastAPI) files with api/ prefix
    api_files = generate_fastapi_api(project_name, use_docker=False, include_ci=False)
    for path, content in api_files.items():
        files[f"api/{path}"] = content
    
    # Root README.md
    files["README.md"] = f'''# {project_name}

A fullstack application with Next.js frontend and FastAPI backend.

Generated with agent-service scaffold.

## Project Structure

```
{project_name}/
├── web/           # Next.js frontend
│   ├── src/
│   ├── package.json
│   └── ...
├── api/           # FastAPI backend
│   ├── app/
│   ├── tests/
│   ├── requirements.txt
│   └── ...
└── README.md
```

## Getting Started

### Backend (FastAPI)

```bash
cd api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend (Next.js)

```bash
cd web
npm install
npm run dev
```

## URLs

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

Generated on {datetime.now().strftime("%Y-%m-%d")} by agent-service.
'''
    
    # Optional: Docker Compose
    if use_docker:
        files["docker-compose.yml"] = f'''version: "3.8"

services:
  web:
    build: ./web
    ports:
      - "3000:3000"
    environment:
      - API_URL=http://api:8000
    depends_on:
      - api

  api:
    build: ./api
    ports:
      - "8000:8000"
    environment:
      - CORS_ORIGINS=http://localhost:3000
'''
        
        # Add Dockerfiles to each folder
        web_dockerfile = generate_nextjs_web(project_name, use_docker=True)
        if "Dockerfile" in web_dockerfile:
            files["web/Dockerfile"] = web_dockerfile["Dockerfile"]
        if ".dockerignore" in web_dockerfile:
            files["web/.dockerignore"] = web_dockerfile[".dockerignore"]
            
        api_dockerfile = generate_fastapi_api(project_name, use_docker=True)
        if "Dockerfile" in api_dockerfile:
            files["api/Dockerfile"] = api_dockerfile["Dockerfile"]
        if ".dockerignore" in api_dockerfile:
            files["api/.dockerignore"] = api_dockerfile[".dockerignore"]
    
    # Optional: GitHub Actions CI
    if include_ci:
        files[".github/workflows/ci.yml"] = f'''name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  api:
    name: Backend Tests
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: api

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run tests
        run: pytest -v

  web:
    name: Frontend Build
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web

    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: web/package-lock.json

      - name: Install dependencies
        run: npm ci

      - name: Lint
        run: npm run lint

      - name: Build
        run: npm run build
'''
    
    return files


# =============================================================================
# Template Registry
# =============================================================================

TEMPLATES = {
    "nextjs_web": generate_nextjs_web,
    "fastapi_api": generate_fastapi_api,
    "fullstack_nextjs_fastapi": generate_fullstack,
}


def generate_project(
    template: str,
    project_name: str,
    use_docker: bool = False,
    include_ci: bool = False,
) -> dict[str, str]:
    """
    Generate project files from template.
    
    Args:
        template: Template name
        project_name: Project name (validated)
        use_docker: Include Docker files
        include_ci: Include CI workflow
        
    Returns:
        Dict of file_path -> file_content
    """
    if template not in TEMPLATES:
        raise ValueError(f"Unknown template: {template}")
    
    generator = TEMPLATES[template]
    return generator(project_name, use_docker=use_docker, include_ci=include_ci)
