# QDash Project Overview

## Project Purpose
QDash is a comprehensive web platform for managing and monitoring qubit calibration workflows. It provides a user-friendly interface to manage calibration processes, track observational data, and configure calibration parameters seamlessly.

## Tech Stack

### Frontend (UI)
- **Location**: `/ui/`
- **Technology**: React, Next.js 14.2.24, TypeScript 5.6.3
- **Package Manager**: Bun (>=1.0.0)
- **Styling**: Tailwind CSS 4.0.9, DaisyUI 5.0.0
- **State Management**: TanStack Query 5.59.20
- **Charts/Visualization**: Plotly.js, React Flow, Nivo
- **Code Generation**: OpenAPI TypeScript (orval)

### Backend (API)
- **Location**: `/src/qdash/api/`
- **Technology**: FastAPI 0.111.1, Python 3.10-3.13
- **Database**: MongoDB (via Bunnet ODM), PostgreSQL 14
- **Authentication**: JWT with python-jose, X-Username header (dev mode)
- **Web Server**: Uvicorn with Gunicorn (4 workers)

### Workflow Engine
- **Location**: `/src/qdash/workflow/`
- **Technology**: Prefect 2.20
- **Purpose**: Manages qubit calibration workflows
- **Integration**: Uses qubex library (v1.4.1b1) for quantum experiments

### Slack Agent (New Feature)
- **Location**: `/src/qdash/slack_agent/`
- **Technology**: Slack Bolt, OpenAI API
- **Purpose**: AI-powered Slack assistant for QDash operations

## Architecture
QDash follows a microservices architecture with Docker Compose orchestration:
- MongoDB for calibration data and configurations
- PostgreSQL for Prefect workflow metadata
- FastAPI backend with OpenAPI documentation
- Next.js frontend with auto-generated API client
- Prefect workflow engine for quantum experiments
- Slack agent for AI-assisted operations

## Development Environment
- **Container**: Docker & Docker Compose
- **Task Runner**: go-task v3.41.0 (Taskfile.yaml)
- **Python Dependency Manager**: uv
- **Node Package Manager**: Bun
- **Development Mode**: Hot reload for both frontend and backend