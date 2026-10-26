from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from psychohelp.constants.rbac import PermissionCode
from psychohelp.routes.controllers import articles as articles_controller
from psychohelp.schemas.articles import ArticleCreateRequest, ArticleUpdateRequest
import psychohelp.services.rbac.permissions as permissions_module


@pytest.mark.asyncio
async def test_get_articles_is_public(monkeypatch):
    article_id = uuid4()

    async def fake_get_articles(skip, take):
        assert skip == 0
        assert take == 100
        return [
            SimpleNamespace(
                id=article_id,
                title="Заголовок",
                text="Текст статьи",
            )
        ]

    monkeypatch.setattr(articles_controller.articles_service, "get_articles", fake_get_articles)

    result = await articles_controller.get_articles(skip=0, take=100)

    assert len(result) == 1
    assert result[0].id == article_id
    assert result[0].title == "Заголовок"
    assert result[0].text == "Текст статьи"


@pytest.mark.asyncio
async def test_create_article_allows_user_with_permission(monkeypatch):
    article_id = uuid4()
    current_user_id = uuid4()

    async def fake_has_permission(user_id, permission_code):
        assert user_id == current_user_id
        assert permission_code == PermissionCode.ARTICLES_CREATE
        return True

    async def fake_create_article(article_data):
        assert article_data == {
            "slug": "test-article", "title": "Заголовок", "text": "Текст статьи",
            "image": None, "date": None, "author": None, "description": None,
        }
        return SimpleNamespace(id=article_id, **article_data)

    monkeypatch.setattr(permissions_module, "user_has_permission", fake_has_permission)
    monkeypatch.setattr(articles_controller.articles_service, "create_article", fake_create_article)

    current_user = SimpleNamespace(
        id=current_user_id,
    )

    result = await articles_controller.create_article(
        ArticleCreateRequest(slug="test-article", title="Заголовок", text="Текст статьи"),
        current_user=current_user,
    )

    assert result.id == article_id
    assert result.title == "Заголовок"
    assert result.text == "Текст статьи"


@pytest.mark.asyncio
async def test_create_article_forbids_user_without_permission(monkeypatch):
    async def fake_has_permission(_user_id, permission_code):
        assert permission_code == PermissionCode.ARTICLES_CREATE
        return False

    async def fake_create_article(_):
        raise AssertionError("service should not be called")

    monkeypatch.setattr(permissions_module, "user_has_permission", fake_has_permission)
    monkeypatch.setattr(articles_controller.articles_service, "create_article", fake_create_article)

    current_user = SimpleNamespace(
        id=uuid4(),
    )

    with pytest.raises(HTTPException) as exc:
        await articles_controller.create_article(
            ArticleCreateRequest(slug="test-article", title="Заголовок", text="Текст статьи"),
            current_user=current_user,
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "Недостаточно прав: требуется articles.create"


@pytest.mark.asyncio
async def test_update_article_uses_edit_permission(monkeypatch):
    article_id = uuid4()
    current_user_id = uuid4()

    async def fake_has_permission(user_id, permission_code):
        assert user_id == current_user_id
        assert permission_code == PermissionCode.ARTICLES_EDIT
        return True

    async def fake_update_article(actual_article_id, article_data):
        assert actual_article_id == article_id
        assert article_data == {"title": "Новый заголовок", "text": "Новый текст"}
        return SimpleNamespace(id=article_id, **article_data)

    monkeypatch.setattr(permissions_module, "user_has_permission", fake_has_permission)
    monkeypatch.setattr(articles_controller.articles_service, "update_article", fake_update_article)

    result = await articles_controller.update_article(
        article_id,
        ArticleUpdateRequest(title="Новый заголовок", text="Новый текст"),
        current_user=SimpleNamespace(id=current_user_id),
    )

    assert result.id == article_id
    assert result.title == "Новый заголовок"
    assert result.text == "Новый текст"


@pytest.mark.asyncio
async def test_delete_article_uses_delete_permission(monkeypatch):
    article_id = uuid4()
    current_user_id = uuid4()

    async def fake_has_permission(user_id, permission_code):
        assert user_id == current_user_id
        assert permission_code == PermissionCode.ARTICLES_DELETE
        return True

    async def fake_delete_article(actual_article_id):
        assert actual_article_id == article_id
        return True

    monkeypatch.setattr(permissions_module, "user_has_permission", fake_has_permission)
    monkeypatch.setattr(articles_controller.articles_service, "delete_article", fake_delete_article)

    result = await articles_controller.delete_article(
        article_id,
        current_user=SimpleNamespace(id=current_user_id),
    )

    assert result == {"message": "Статья успешно удалена"}
