"""
Scaffolder for generating project templates.
Generates complete starter projects as files or patches.

Templates:
- nextjs: Next.js + TypeScript + Tailwind CSS
- fastapi: FastAPI + PostgreSQL + Alembic
- fullstack: Next.js frontend + FastAPI backend + Docker Compose

Security:
- No shell command execution
- Output size limits enforced
- No secrets in generated files
"""
import logging
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

MAX_FILES = 80
MAX_FILE_SIZE = 80 * 1024  # 80KB per file
MAX_TOTAL_SIZE = 1.5 * 1024 * 1024  # 1.5MB total

SUPPORTED_TEMPLATES = {"nextjs", "fastapi", "fullstack"}
SUPPORTED_FEATURES = {"auth_optional", "db_optional", "stripe_optional"}


@dataclass
class GeneratedFile:
    """A single generated file."""
    path: str
    content: str
    
    @property
    def size(self) -> int:
        return len(self.content.encode("utf-8"))


@dataclass
class ScaffoldResult:
    """Result of scaffold generation."""
    template: str
    project_name: str
    files: list[GeneratedFile]
    base_path: str
    total_files: int
    total_bytes: int
    error: Optional[str] = None


class ScaffoldError(Exception):
    """Error during scaffold generation."""
    pass


def validate_project_name(name: str) -> str:
    """Validate and sanitize project name."""
    import re
    # Allow alphanumeric, hyphens, underscores
    name = name.strip().lower()
    if not re.match(r"^[a-z][a-z0-9_-]*$", name):
        raise ScaffoldError(
            "Project name must start with a letter and contain only "
            "lowercase letters, numbers, hyphens, and underscores"
        )
    if len(name) > 64:
        raise ScaffoldError("Project name must be 64 characters or less")
    return name


def generate_scaffold(
    template: str,
    project_name: str,
    description: str = "",
    features: Optional[list[str]] = None,
    base_path: str = "",
) -> ScaffoldResult:
    """
    Generate a project scaffold.
    
    Args:
        template: Template name (nextjs, fastapi, fullstack)
        project_name: Name of the project
        description: Short project description
        features: Optional features to include
        base_path: Base path for generated files
        
    Returns:
        ScaffoldResult with generated files
    """
    # Validate inputs
    if template not in SUPPORTED_TEMPLATES:
        raise ScaffoldError(f"Unknown template: {template}. Supported: {', '.join(SUPPORTED_TEMPLATES)}")
    
    project_name = validate_project_name(project_name)
    features = features or []
    
    # Validate features
    invalid_features = set(features) - SUPPORTED_FEATURES
    if invalid_features:
        logger.warning(f"scaffold_unknown_features features={invalid_features}")
    
    # Normalize base path
    if base_path:
        base_path = base_path.strip("/")
        if base_path:
            base_path = f"{base_path}/"
    
    # Generate based on template
    if template == "nextjs":
        files = _generate_nextjs(project_name, description, features)
    elif template == "fastapi":
        files = _generate_fastapi(project_name, description, features)
    elif template == "fullstack":
        files = _generate_fullstack(project_name, description, features)
    else:
        raise ScaffoldError(f"Template {template} not implemented")
    
    # Apply base path
    if base_path:
        files = [GeneratedFile(path=f"{base_path}{f.path}", content=f.content) for f in files]
    
    # Validate limits
    if len(files) > MAX_FILES:
        raise ScaffoldError(f"Too many files generated ({len(files)} > {MAX_FILES})")
    
    total_bytes = sum(f.size for f in files)
    if total_bytes > MAX_TOTAL_SIZE:
        raise ScaffoldError(
            f"Total size exceeds limit ({total_bytes} > {MAX_TOTAL_SIZE} bytes)"
        )
    
    for f in files:
        if f.size > MAX_FILE_SIZE:
            raise ScaffoldError(
                f"File {f.path} exceeds size limit ({f.size} > {MAX_FILE_SIZE} bytes)"
            )
    
    logger.info(f"scaffold_generated template={template} files={len(files)} bytes={total_bytes}")
    
    return ScaffoldResult(
        template=template,
        project_name=project_name,
        files=files,
        base_path=base_path,
        total_files=len(files),
        total_bytes=total_bytes,
    )


# =============================================================================
# Next.js Template
# =============================================================================

def _generate_nextjs(name: str, description: str, features: list[str]) -> list[GeneratedFile]:
    """Generate Next.js + TypeScript + Tailwind project."""
    files = []
    year = datetime.now().year
    
    # package.json
    files.append(GeneratedFile(
        path="package.json",
        content=f'''{{"name": "{name}",
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
    "react": "^18",
    "react-dom": "^18"
  }},
  "devDependencies": {{
    "@types/node": "^20",
    "@types/react": "^18",
    "@types/react-dom": "^18",
    "autoprefixer": "^10.4.20",
    "eslint": "^8",
    "eslint-config-next": "14.2.0",
    "postcss": "^8.4.47",
    "tailwindcss": "^3.4.14",
    "typescript": "^5"
  }}
}}
'''
    ))
    
    # tsconfig.json
    files.append(GeneratedFile(
        path="tsconfig.json",
        content='''{
  "compilerOptions": {
    "target": "ES2017",
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
    "plugins": [{"name": "next"}],
    "paths": {"@/*": ["./src/*"]}
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
'''
    ))
    
    # next.config.mjs
    files.append(GeneratedFile(
        path="next.config.mjs",
        content='''/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
};

export default nextConfig;
'''
    ))
    
    # tailwind.config.ts
    files.append(GeneratedFile(
        path="tailwind.config.ts",
        content='''import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};

export default config;
'''
    ))
    
    # postcss.config.mjs
    files.append(GeneratedFile(
        path="postcss.config.mjs",
        content='''/** @type {import('postcss-load-config').Config} */
const config = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};

export default config;
'''
    ))
    
    # .env.example
    files.append(GeneratedFile(
        path=".env.example",
        content=f'''# {name} Environment Variables
# Copy to .env.local and fill in values

# App
NEXT_PUBLIC_APP_NAME={name}
NEXT_PUBLIC_APP_URL=http://localhost:3000

# API (if using external API)
# API_URL=http://localhost:8000
# API_KEY=your-api-key
'''
    ))
    
    # .gitignore
    files.append(GeneratedFile(
        path=".gitignore",
        content='''# Dependencies
node_modules/
.pnp
.pnp.js

# Build
.next/
out/
build/
dist/

# Testing
coverage/

# Environment
.env
.env.local
.env.development.local
.env.test.local
.env.production.local

# Debug
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# IDE
.idea/
.vscode/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# TypeScript
*.tsbuildinfo
next-env.d.ts
'''
    ))
    
    # README.md
    files.append(GeneratedFile(
        path="README.md",
        content=f'''# {name}

{description or "A Next.js application with TypeScript and Tailwind CSS."}

## Getting Started

### Prerequisites

- Node.js 18+ 
- npm or yarn

### Installation

```bash
# Install dependencies
npm install

# Copy environment variables
cp .env.example .env.local

# Start development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Project Structure

```
{name}/
├── src/
│   ├── app/           # App router pages
│   │   ├── layout.tsx # Root layout
│   │   ├── page.tsx   # Home page
│   │   └── api/       # API routes
│   └── components/    # React components
├── public/            # Static assets
├── tailwind.config.ts # Tailwind configuration
└── package.json
```

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start development server |
| `npm run build` | Build for production |
| `npm run start` | Start production server |
| `npm run lint` | Run ESLint |

## Next Steps

1. Customize `src/app/page.tsx` with your content
2. Add components in `src/components/`
3. Create API routes in `src/app/api/`
4. Update `tailwind.config.ts` with your theme

## License

MIT © {year}
'''
    ))
    
    # src/app/layout.tsx
    files.append(GeneratedFile(
        path="src/app/layout.tsx",
        content=f'''import type {{ Metadata }} from "next";
import "./globals.css";

export const metadata: Metadata = {{
  title: "{name}",
  description: "{description or 'A Next.js application'}",
}};

export default function RootLayout({{
  children,
}}: Readonly<{{
  children: React.ReactNode;
}}>) {{
  return (
    <html lang="en">
      <body className="antialiased">{{children}}</body>
    </html>
  );
}}
'''
    ))
    
    # src/app/globals.css
    files.append(GeneratedFile(
        path="src/app/globals.css",
        content='''@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --foreground: #171717;
  --background: #ffffff;
}

@media (prefers-color-scheme: dark) {
  :root {
    --foreground: #ededed;
    --background: #0a0a0a;
  }
}

body {
  color: var(--foreground);
  background: var(--background);
  font-family: system-ui, -apple-system, sans-serif;
}
'''
    ))
    
    # src/app/page.tsx
    files.append(GeneratedFile(
        path="src/app/page.tsx",
        content=f'''export default function Home() {{
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24">
      <div className="text-center">
        <h1 className="text-4xl font-bold mb-4">
          Welcome to {name}
        </h1>
        <p className="text-lg text-gray-600 dark:text-gray-400 mb-8">
          {description or "Get started by editing src/app/page.tsx"}
        </p>
        <div className="flex gap-4 justify-center">
          <a
            href="https://nextjs.org/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
          >
            Documentation
          </a>
          <a
            href="/api/health"
            className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition"
          >
            API Health
          </a>
        </div>
      </div>
    </main>
  );
}}
'''
    ))
    
    # src/app/api/health/route.ts
    files.append(GeneratedFile(
        path="src/app/api/health/route.ts",
        content='''import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    status: "ok",
    timestamp: new Date().toISOString(),
  });
}
'''
    ))
    
    # src/components/Button.tsx
    files.append(GeneratedFile(
        path="src/components/Button.tsx",
        content='''import React from "react";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "outline";
  size?: "sm" | "md" | "lg";
  children: React.ReactNode;
}

export function Button({
  variant = "primary",
  size = "md",
  children,
  className = "",
  ...props
}: ButtonProps) {
  const baseClasses = "font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2";
  
  const variants = {
    primary: "bg-blue-600 text-white hover:bg-blue-700 focus:ring-blue-500",
    secondary: "bg-gray-200 text-gray-900 hover:bg-gray-300 focus:ring-gray-500",
    outline: "border border-gray-300 text-gray-700 hover:bg-gray-50 focus:ring-gray-500",
  };
  
  const sizes = {
    sm: "px-3 py-1.5 text-sm",
    md: "px-4 py-2 text-base",
    lg: "px-6 py-3 text-lg",
  };
  
  return (
    <button
      className={`${baseClasses} ${variants[variant]} ${sizes[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
'''
    ))
    
    # public/.gitkeep
    files.append(GeneratedFile(
        path="public/.gitkeep",
        content="# Static assets go here\n"
    ))
    
    # next-env.d.ts
    files.append(GeneratedFile(
        path="next-env.d.ts",
        content='''/// <reference types="next" />
/// <reference types="next/image-types/global" />

// NOTE: This file should not be edited
// see https://nextjs.org/docs/basic-features/typescript for more information.
'''
    ))
    
    return files


# =============================================================================
# FastAPI Template
# =============================================================================

def _generate_fastapi(name: str, description: str, features: list[str]) -> list[GeneratedFile]:
    """Generate FastAPI + PostgreSQL + Alembic project."""
    files = []
    year = datetime.now().year
    
    # requirements.txt
    files.append(GeneratedFile(
        path="requirements.txt",
        content='''fastapi>=0.109.0
uvicorn[standard]>=0.27.0
sqlalchemy>=2.0.0
alembic>=1.13.0
psycopg2-binary>=2.9.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
python-dotenv>=1.0.0
httpx>=0.26.0
'''
    ))
    
    # requirements-dev.txt
    files.append(GeneratedFile(
        path="requirements-dev.txt",
        content='''-r requirements.txt
pytest>=8.0.0
pytest-asyncio>=0.23.0
httpx>=0.26.0
ruff>=0.2.0
mypy>=1.8.0
'''
    ))
    
    # pyproject.toml
    files.append(GeneratedFile(
        path="pyproject.toml",
        content=f'''[project]
name = "{name}"
version = "0.1.0"
description = "{description or 'A FastAPI application'}"
requires-python = ">=3.10"

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "W"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.mypy]
python_version = "3.10"
strict = true
'''
    ))
    
    # .env.example
    files.append(GeneratedFile(
        path=".env.example",
        content=f'''# {name} Environment Variables
# Copy to .env and fill in values

# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/{name.replace("-", "_")}

# App
APP_NAME={name}
DEBUG=true
SECRET_KEY=change-me-in-production

# Server
HOST=0.0.0.0
PORT=8000
'''
    ))
    
    # .gitignore
    files.append(GeneratedFile(
        path=".gitignore",
        content='''# Python
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
venv/
.venv/
ENV/

# Environment
.env
.env.local

# IDE
.idea/
.vscode/
*.swp
*.swo

# Testing
.pytest_cache/
.coverage
htmlcov/
.tox/
.nox/

# MyPy
.mypy_cache/

# Ruff
.ruff_cache/

# Database
*.db
*.sqlite3

# OS
.DS_Store
Thumbs.db
'''
    ))
    
    # docker-compose.yml
    files.append(GeneratedFile(
        path="docker-compose.yml",
        content=f'''version: "3.9"

services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/{name.replace("-", "_")}
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - .:/app

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: {name.replace("-", "_")}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
'''
    ))
    
    # Dockerfile
    files.append(GeneratedFile(
        path="Dockerfile",
        content='''FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
'''
    ))
    
    # README.md
    files.append(GeneratedFile(
        path="README.md",
        content=f'''# {name}

{description or "A FastAPI application with PostgreSQL and Alembic migrations."}

## Getting Started

### Prerequisites

- Python 3.10+
- PostgreSQL 14+
- Docker (optional)

### Installation

#### Option 1: Docker (Recommended)

```bash
# Start services
docker-compose up -d

# Run migrations
docker-compose exec app alembic upgrade head

# View logs
docker-compose logs -f app
```

#### Option 2: Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\\Scripts\\activate` on Windows

# Install dependencies
pip install -r requirements-dev.txt

# Copy environment variables
cp .env.example .env
# Edit .env with your database URL

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

## API Documentation

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## Project Structure

```
{name}/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI application
│   ├── config.py        # Configuration
│   ├── database.py      # Database setup
│   ├── models/          # SQLAlchemy models
│   ├── schemas/         # Pydantic schemas
│   └── api/             # API routes
├── alembic/             # Database migrations
├── tests/               # Test files
├── docker-compose.yml
└── requirements.txt
```

## Scripts

| Command | Description |
|---------|-------------|
| `uvicorn app.main:app --reload` | Start dev server |
| `alembic upgrade head` | Run migrations |
| `alembic revision --autogenerate -m "msg"` | Create migration |
| `pytest` | Run tests |
| `ruff check .` | Lint code |

## Next Steps

1. Add your models in `app/models/`
2. Create schemas in `app/schemas/`
3. Add routes in `app/api/`
4. Generate migrations with Alembic

## License

MIT © {year}
'''
    ))
    
    # app/__init__.py
    files.append(GeneratedFile(
        path="app/__init__.py",
        content='"""FastAPI application."""\n'
    ))
    
    # app/config.py
    files.append(GeneratedFile(
        path="app/config.py",
        content=f'''"""Application configuration."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings from environment variables."""
    
    app_name: str = "{name}"
    debug: bool = False
    secret_key: str = "change-me"
    
    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/{name.replace("-", "_")}"
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
'''
    ))
    
    # app/database.py
    files.append(GeneratedFile(
        path="app/database.py",
        content='''"""Database configuration and session management."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings

engine = create_engine(settings.database_url, echo=settings.debug)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""
    pass


def get_db():
    """Dependency for getting database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
'''
    ))
    
    # app/main.py
    files.append(GeneratedFile(
        path="app/main.py",
        content=f'''"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api import health, items

app = FastAPI(
    title=settings.app_name,
    description="{description or 'A FastAPI application'}",
    version="0.1.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["health"])
app.include_router(items.router, prefix="/api/v1", tags=["items"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {{"message": "Welcome to {name}", "docs": "/docs"}}
'''
    ))
    
    # app/models/__init__.py
    files.append(GeneratedFile(
        path="app/models/__init__.py",
        content='''"""SQLAlchemy models."""
from app.models.item import Item

__all__ = ["Item"]
'''
    ))
    
    # app/models/item.py
    files.append(GeneratedFile(
        path="app/models/item.py",
        content='''"""Item model."""
from datetime import datetime
from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Item(Base):
    """Item model for demonstration."""
    
    __tablename__ = "items"
    
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
'''
    ))
    
    # app/schemas/__init__.py
    files.append(GeneratedFile(
        path="app/schemas/__init__.py",
        content='''"""Pydantic schemas."""
from app.schemas.item import ItemCreate, ItemUpdate, ItemResponse

__all__ = ["ItemCreate", "ItemUpdate", "ItemResponse"]
'''
    ))
    
    # app/schemas/item.py
    files.append(GeneratedFile(
        path="app/schemas/item.py",
        content='''"""Item schemas."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ItemBase(BaseModel):
    """Base item schema."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class ItemCreate(ItemBase):
    """Schema for creating an item."""
    pass


class ItemUpdate(BaseModel):
    """Schema for updating an item."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None


class ItemResponse(ItemBase):
    """Schema for item response."""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
'''
    ))
    
    # app/api/__init__.py
    files.append(GeneratedFile(
        path="app/api/__init__.py",
        content='"""API routes."""\n'
    ))
    
    # app/api/health.py
    files.append(GeneratedFile(
        path="app/api/health.py",
        content='''"""Health check endpoints."""
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter()


@router.get("/health")
async def health_check():
    """Basic health check."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/health/db")
async def health_check_db(db: Session = Depends(get_db)):
    """Health check with database connectivity."""
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "database": db_status,
        "timestamp": datetime.utcnow().isoformat(),
    }
'''
    ))
    
    # app/api/items.py
    files.append(GeneratedFile(
        path="app/api/items.py",
        content='''"""Item CRUD endpoints."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.item import Item
from app.schemas.item import ItemCreate, ItemUpdate, ItemResponse

router = APIRouter()


@router.get("/items", response_model=List[ItemResponse])
async def list_items(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """List all items."""
    items = db.query(Item).offset(skip).limit(limit).all()
    return items


@router.post("/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(item: ItemCreate, db: Session = Depends(get_db)):
    """Create a new item."""
    db_item = Item(**item.model_dump())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@router.get("/items/{item_id}", response_model=ItemResponse)
async def get_item(item_id: int, db: Session = Depends(get_db)):
    """Get an item by ID."""
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.patch("/items/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: int,
    item_update: ItemUpdate,
    db: Session = Depends(get_db),
):
    """Update an item."""
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    update_data = item_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(item, field, value)
    
    db.commit()
    db.refresh(item)
    return item


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: int, db: Session = Depends(get_db)):
    """Delete an item."""
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    db.delete(item)
    db.commit()
    return None
'''
    ))
    
    # alembic.ini
    files.append(GeneratedFile(
        path="alembic.ini",
        content=f'''[alembic]
script_location = alembic
prepend_sys_path = .
version_path_separator = os

sqlalchemy.url = driver://user:pass@localhost/dbname

[post_write_hooks]

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
'''
    ))
    
    # alembic/env.py
    files.append(GeneratedFile(
        path="alembic/env.py",
        content='''"""Alembic migration environment."""
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

from app.config import settings
from app.database import Base
from app.models import Item  # noqa: F401 - Import models for autogenerate

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
'''
    ))
    
    # alembic/script.py.mako
    files.append(GeneratedFile(
        path="alembic/script.py.mako",
        content='''"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
'''
    ))
    
    # alembic/versions/.gitkeep
    files.append(GeneratedFile(
        path="alembic/versions/.gitkeep",
        content="# Migration files go here\n"
    ))
    
    # Sample migration
    files.append(GeneratedFile(
        path="alembic/versions/001_initial.py",
        content='''"""Initial migration - create items table.

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_items_id"), "items", ["id"], unique=False)
    op.create_index(op.f("ix_items_name"), "items", ["name"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_items_name"), table_name="items")
    op.drop_index(op.f("ix_items_id"), table_name="items")
    op.drop_table("items")
'''
    ))
    
    # tests/__init__.py
    files.append(GeneratedFile(
        path="tests/__init__.py",
        content='"""Tests."""\n'
    ))
    
    # tests/conftest.py
    files.append(GeneratedFile(
        path="tests/conftest.py",
        content='''"""Test configuration."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)
'''
    ))
    
    # tests/test_health.py
    files.append(GeneratedFile(
        path="tests/test_health.py",
        content='''"""Health endpoint tests."""


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


def test_root_endpoint(client):
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "docs" in data
'''
    ))
    
    return files


# =============================================================================
# Fullstack Template
# =============================================================================

def _generate_fullstack(name: str, description: str, features: list[str]) -> list[GeneratedFile]:
    """Generate fullstack project: Next.js + FastAPI + Docker Compose."""
    files = []
    year = datetime.now().year
    
    # Root docker-compose.yml
    files.append(GeneratedFile(
        path="docker-compose.yml",
        content=f'''version: "3.9"

services:
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
    depends_on:
      - backend
    volumes:
      - ./frontend:/app
      - /app/node_modules
      - /app/.next

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/{name.replace("-", "_")}
      - CORS_ORIGINS=http://localhost:3000
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./backend:/app

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: {name.replace("-", "_")}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
'''
    ))
    
    # Root README.md
    files.append(GeneratedFile(
        path="README.md",
        content=f'''# {name}

{description or "A fullstack application with Next.js frontend and FastAPI backend."}

## Architecture

```
{name}/
├── frontend/          # Next.js + TypeScript + Tailwind
├── backend/           # FastAPI + PostgreSQL + Alembic
└── docker-compose.yml # Development orchestration
```

## Quick Start

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Services

| Service | URL | Description |
|---------|-----|-------------|
| Frontend | http://localhost:3000 | Next.js application |
| Backend | http://localhost:8000 | FastAPI application |
| API Docs | http://localhost:8000/docs | Swagger UI |
| Database | localhost:5432 | PostgreSQL |

## Development

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Next Steps

1. Customize frontend pages in `frontend/src/app/`
2. Add backend routes in `backend/app/api/`
3. Create database models in `backend/app/models/`
4. Configure environment variables

## License

MIT © {year}
'''
    ))
    
    # Root .gitignore
    files.append(GeneratedFile(
        path=".gitignore",
        content='''# Environment
.env
.env.local

# IDE
.idea/
.vscode/

# OS
.DS_Store
Thumbs.db
'''
    ))
    
    # Generate frontend files (simplified Next.js)
    frontend_files = _generate_nextjs(name, f"{description} - Frontend", features)
    for f in frontend_files:
        files.append(GeneratedFile(path=f"frontend/{f.path}", content=f.content))
    
    # Add frontend Dockerfile
    files.append(GeneratedFile(
        path="frontend/Dockerfile",
        content='''FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
'''
    ))
    
    # Update frontend to use API
    files.append(GeneratedFile(
        path="frontend/src/lib/api.ts",
        content='''/**
 * API client for backend communication.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Item {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateItem {
  name: string;
  description?: string;
}

export async function fetchItems(): Promise<Item[]> {
  const res = await fetch(`${API_URL}/api/v1/items`);
  if (!res.ok) throw new Error("Failed to fetch items");
  return res.json();
}

export async function createItem(item: CreateItem): Promise<Item> {
  const res = await fetch(`${API_URL}/api/v1/items`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(item),
  });
  if (!res.ok) throw new Error("Failed to create item");
  return res.json();
}

export async function deleteItem(id: number): Promise<void> {
  const res = await fetch(`${API_URL}/api/v1/items/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete item");
}

export async function checkHealth(): Promise<{ status: string }> {
  const res = await fetch(`${API_URL}/health`);
  return res.json();
}
'''
    ))
    
    # Generate backend files (simplified FastAPI)
    backend_files = _generate_fastapi(name, f"{description} - Backend", features)
    for f in backend_files:
        files.append(GeneratedFile(path=f"backend/{f.path}", content=f.content))
    
    # Update backend CORS for frontend
    files.append(GeneratedFile(
        path="backend/app/config.py",
        content=f'''"""Application configuration."""
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings from environment variables."""
    
    app_name: str = "{name}"
    debug: bool = False
    secret_key: str = "change-me"
    
    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/{name.replace("-", "_")}"
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    
    # CORS
    cors_origins: List[str] = ["http://localhost:3000"]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
'''
    ))
    
    return files


def files_to_patches(files: list[GeneratedFile], base_path: str = "") -> list[dict]:
    """Convert generated files to unified diff patches (for new file creation)."""
    patches = []
    
    for f in files:
        # For new files, create a diff from empty to content
        lines = f.content.splitlines(keepends=True)
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        
        diff_lines = [
            f"--- /dev/null\n",
            f"+++ b/{f.path}\n",
            f"@@ -0,0 +1,{len(lines)} @@\n",
        ]
        diff_lines.extend(f"+{line}" if line.endswith("\n") else f"+{line}\n" for line in lines)
        
        patches.append({
            "path": f.path,
            "diff_type": "add",
            "unified_diff": "".join(diff_lines),
        })
    
    return patches
