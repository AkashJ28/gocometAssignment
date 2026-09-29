"""Automated verification for Docker Compose packaging, Dockerfiles, and environment config (ARCH-01)."""

import os
import yaml
import pytest


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_docker_compose_valid_yaml():
    """Verify docker-compose.yml exists and has valid YAML structure and services."""
    compose_path = os.path.join(REPO_ROOT, "docker-compose.yml")
    assert os.path.exists(compose_path), "docker-compose.yml must exist in repository root"

    with open(compose_path, "r", encoding="utf-8") as f:
        compose_data = yaml.safe_load(f)

    assert "services" in compose_data, "docker-compose.yml must define 'services'"
    services = compose_data["services"]

    # Verify db, backend, and frontend services
    assert "db" in services, "Service 'db' (PostgreSQL) must be defined"
    assert "backend" in services, "Service 'backend' (FastAPI) must be defined"
    assert "frontend" in services, "Service 'frontend' (React/Nginx) must be defined"

    # Verify database healthcheck
    db_service = services["db"]
    assert "healthcheck" in db_service, "db service must have a healthcheck"
    assert "environment" in db_service

    # Verify backend dependencies and ports
    backend_service = services["backend"]
    assert "depends_on" in backend_service
    assert "db" in backend_service["depends_on"]
    assert "8000:8000" in backend_service.get("ports", [])

    # Verify frontend port 3000 mapping
    frontend_service = services["frontend"]
    assert "depends_on" in frontend_service
    assert "backend" in frontend_service["depends_on"]
    assert "3000:80" in frontend_service.get("ports", []) or "80:80" in frontend_service.get("ports", [])


def test_dockerfile_backend():
    """Verify Dockerfile.backend exists and contains necessary directives."""
    df_path = os.path.join(REPO_ROOT, "Dockerfile.backend")
    assert os.path.exists(df_path), "Dockerfile.backend must exist"

    content = open(df_path, "r", encoding="utf-8").read()
    assert "FROM python:" in content
    assert "COPY requirements.txt" in content
    assert "EXPOSE 8000" in content
    assert "uvicorn" in content


def test_dockerfile_frontend_and_nginx():
    """Verify Dockerfile.frontend and nginx.conf exist and configure reverse proxy."""
    df_path = os.path.join(REPO_ROOT, "Dockerfile.frontend")
    nginx_path = os.path.join(REPO_ROOT, "nginx.conf")

    assert os.path.exists(df_path), "Dockerfile.frontend must exist"
    assert os.path.exists(nginx_path), "nginx.conf must exist"

    df_content = open(df_path, "r", encoding="utf-8").read()
    assert "FROM node:" in df_content
    assert "FROM nginx:" in df_content

    nginx_content = open(nginx_path, "r", encoding="utf-8").read()
    assert "proxy_pass http://backend:8000/api/;" in nginx_content
    assert "try_files $uri $uri/ /index.html;" in nginx_content


def test_env_example():
    """Verify .env.example contains required template environment variables."""
    env_path = os.path.join(REPO_ROOT, ".env.example")
    assert os.path.exists(env_path), ".env.example must exist"

    content = open(env_path, "r", encoding="utf-8").read()
    assert "GEMINI_API_KEY=" in content
    assert "DATABASE_URL=" in content
    assert "EXTRACTOR_MODEL=" in content
    assert "LITE_MODEL=" in content
