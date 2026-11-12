
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.api.dependencies import get_current_user
from app.api.v1.endpoints.prompts import get_prompt_service
from app.db.session import get_db
from app.services.prompt_service import PromptNotFoundError


def make_prompt(user_id):
    now = datetime.now(timezone.utc)

    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        name="Technical Interview Assistant",
        description="Interview preparation",
        current_version=1,
        created_at=now,
        updated_at=now,
    )


def make_version(prompt_id, version_number=1, content=None):
    return SimpleNamespace(
        id=uuid4(),
        prompt_id=prompt_id,
        version_number=version_number,
        content=content or "You are a technical interviewer.",
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def prompt_api_client(monkeypatch):
    user = SimpleNamespace(
        id=uuid4(),
        is_active=True,
    )

    mock_db = AsyncMock()

    mock_service = SimpleNamespace(
        create_prompt=AsyncMock(),
        list_prompts=AsyncMock(),
        count_prompts=AsyncMock(),
        get_prompt=AsyncMock(),
        update_prompt=AsyncMock(),
        list_versions=AsyncMock(),
        get_version=AsyncMock(),
    )

    mock_llm = SimpleNamespace(
        generate=AsyncMock(),
        stream=AsyncMock(),
        close=AsyncMock(),
    )

    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: object(),
    )

    monkeypatch.setattr(
        main,
        "LiteLLMClient",
        lambda settings: mock_llm,
    )

    async def override_current_user():
        return user

    original_overrides = main.app.dependency_overrides.copy()

    main.app.dependency_overrides[get_current_user] = (
        override_current_user
    )

    main.app.dependency_overrides[get_db] = (
        lambda: mock_db
    )

    main.app.dependency_overrides[get_prompt_service] = (
        lambda: mock_service
    )

    try:
        with TestClient(main.app) as client:
            yield client, mock_service, mock_db, user

    finally:
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(original_overrides)


# --------------------------------------------------
# Prompt creation tests
# --------------------------------------------------


def test_create_prompt_success(prompt_api_client):
    client, service, db, user = prompt_api_client

    prompt = make_prompt(user.id)
    version = make_version(prompt.id)

    service.create_prompt.return_value = (prompt, version)

    response = client.post(
        "/api/v1/prompts",
        json={
            "name": "Technical Interview Assistant",
            "description": "Interview preparation",
            "content": "You are a technical interviewer.",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"] == str(prompt.id)
    assert data["name"] == "Technical Interview Assistant"
    assert data["current_version"] == 1
    assert data["latest_version"]["version_number"] == 1

    service.create_prompt.assert_awaited_once_with(
        user_id=user.id,
        name="Technical Interview Assistant",
        description="Interview preparation",
        content="You are a technical interviewer.",
    )

    db.commit.assert_awaited_once()


def test_create_prompt_invalid_request(prompt_api_client):
    client, service, db, user = prompt_api_client

    response = client.post(
        "/api/v1/prompts",
        json={
            "name": "",
            "content": "",
        },
    )

    assert response.status_code == 422

    service.create_prompt.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_create_prompt_rolls_back_on_failure(prompt_api_client):
    client, service, db, user = prompt_api_client

    service.create_prompt.side_effect = RuntimeError(
        "Database failure"
    )

    with pytest.raises(RuntimeError):
        client.post(
            "/api/v1/prompts",
            json={
                "name": "Test Prompt",
                "content": "Test content",
            },
        )

    db.rollback.assert_awaited_once()


# --------------------------------------------------
# Prompt listing tests
# --------------------------------------------------


def test_list_prompts_success(prompt_api_client):
    client, service, db, user = prompt_api_client

    prompt = make_prompt(user.id)

    service.list_prompts.return_value = [prompt]
    service.count_prompts.return_value = 1

    response = client.get("/api/v1/prompts")

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == str(prompt.id)

    service.list_prompts.assert_awaited_once_with(
        user_id=user.id,
        limit=50,
        offset=0,
    )

    service.count_prompts.assert_awaited_once_with(
        user_id=user.id,
    )


def test_list_prompts_pagination(prompt_api_client):
    client, service, db, user = prompt_api_client

    service.list_prompts.return_value = []
    service.count_prompts.return_value = 25

    response = client.get(
        "/api/v1/prompts?limit=10&offset=10"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["limit"] == 10
    assert data["offset"] == 10
    assert data["total"] == 25

    service.list_prompts.assert_awaited_once_with(
        user_id=user.id,
        limit=10,
        offset=10,
    )


# --------------------------------------------------
# Prompt retrieval tests
# --------------------------------------------------


def test_get_prompt_success(prompt_api_client):
    client, service, db, user = prompt_api_client

    prompt = make_prompt(user.id)
    version = make_version(prompt.id)

    service.get_prompt.return_value = prompt
    service.get_version.return_value = version

    response = client.get(
        f"/api/v1/prompts/{prompt.id}"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == str(prompt.id)
    assert data["latest_version"]["content"] == (
        "You are a technical interviewer."
    )


def test_get_prompt_not_found(prompt_api_client):
    client, service, db, user = prompt_api_client

    service.get_prompt.side_effect = PromptNotFoundError(
        "Prompt not found."
    )

    response = client.get(
        f"/api/v1/prompts/{uuid4()}"
    )

    assert response.status_code == 404


# --------------------------------------------------
# Prompt update and versioning tests
# --------------------------------------------------


def test_update_prompt_creates_new_version(prompt_api_client):
    client, service, db, user = prompt_api_client

    prompt = make_prompt(user.id)
    prompt.current_version = 2

    version = make_version(
        prompt.id,
        version_number=2,
        content="You are a senior technical interviewer.",
    )

    service.update_prompt.return_value = (prompt, version)

    response = client.put(
        f"/api/v1/prompts/{prompt.id}",
        json={
            "name": "Senior Interview Assistant",
            "description": "Advanced interview preparation",
            "content": "You are a senior technical interviewer.",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["current_version"] == 2
    assert data["latest_version"]["version_number"] == 2
    assert data["latest_version"]["content"] == (
        "You are a senior technical interviewer."
    )

    service.update_prompt.assert_awaited_once_with(
        prompt_id=prompt.id,
        user_id=user.id,
        name="Senior Interview Assistant",
        description="Advanced interview preparation",
        content="You are a senior technical interviewer.",
    )

    db.commit.assert_awaited_once()


def test_update_prompt_not_found(prompt_api_client):
    client, service, db, user = prompt_api_client

    service.update_prompt.side_effect = PromptNotFoundError(
        "Prompt not found."
    )

    response = client.put(
        f"/api/v1/prompts/{uuid4()}",
        json={
            "name": "Updated Prompt",
            "description": None,
            "content": "Updated content",
        },
    )

    assert response.status_code == 404

    db.rollback.assert_awaited_once()


# --------------------------------------------------
# Prompt version history tests
# --------------------------------------------------


def test_list_prompt_versions(prompt_api_client):
    client, service, db, user = prompt_api_client

    prompt = make_prompt(user.id)

    versions = [
        make_version(
            prompt.id,
            version_number=2,
            content="Updated content",
        ),
        make_version(
            prompt.id,
            version_number=1,
            content="Original content",
        ),
    ]

    service.list_versions.return_value = versions

    response = client.get(
        f"/api/v1/prompts/{prompt.id}/versions"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 2
    assert data[0]["version_number"] == 2
    assert data[1]["version_number"] == 1
    assert data[1]["content"] == "Original content"


def test_get_specific_prompt_version(prompt_api_client):
    client, service, db, user = prompt_api_client

    prompt = make_prompt(user.id)

    original_version = make_version(
        prompt.id,
        version_number=1,
        content="Original content",
    )

    service.get_version.return_value = original_version

    response = client.get(
        f"/api/v1/prompts/{prompt.id}/versions/1"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["version_number"] == 1
    assert data["content"] == "Original content"


# --------------------------------------------------
# Ownership and authentication tests
# --------------------------------------------------


def test_user_cannot_access_another_users_prompt(
    prompt_api_client,
):
    client, service, db, user = prompt_api_client

    service.get_prompt.side_effect = PromptNotFoundError(
        "Prompt not found."
    )

    response = client.get(
        f"/api/v1/prompts/{uuid4()}"
    )

    assert response.status_code == 404


def test_unauthorized_user_cannot_create_prompt(
    prompt_api_client,
):
    client, service, db, user = prompt_api_client

    main.app.dependency_overrides.pop(
        get_current_user,
        None,
    )

    response = client.post(
        "/api/v1/prompts",
        json={
            "name": "Unauthorized Prompt",
            "content": "Test content",
        },
    )

    assert response.status_code == 401

    service.create_prompt.assert_not_awaited()
