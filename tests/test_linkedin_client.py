"""Tests for linkedin_client module."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest
import requests

from linkedin_client import LinkedInClient, LINKEDIN_API_BASE, LINKEDIN_VERSION
from tests.conftest import make_mock_response


class TestClientInit:
    def test_init_with_explicit_credentials(self):
        client = LinkedInClient(
            access_token="test-token",
            person_urn="urn:li:person:abc123",
        )
        assert client.access_token == "test-token"
        assert client.person_urn == "urn:li:person:abc123"

    def test_init_from_env(self, monkeypatch):
        monkeypatch.setenv("LINKEDIN_ACCESS_TOKEN", "env-token")
        monkeypatch.setenv("LINKEDIN_PERSON_URN", "urn:li:person:env123")
        client = LinkedInClient()
        assert client.access_token == "env-token"
        assert client.person_urn == "urn:li:person:env123"

    def test_missing_access_token_raises(self, monkeypatch):
        monkeypatch.delenv("LINKEDIN_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("LINKEDIN_PERSON_URN", raising=False)
        with pytest.raises(ValueError, match="access token"):
            LinkedInClient()

    def test_missing_person_urn_raises(self, monkeypatch):
        monkeypatch.delenv("LINKEDIN_PERSON_URN", raising=False)
        with pytest.raises(ValueError, match="person URN"):
            LinkedInClient(access_token="token")

    def test_default_headers(self):
        client = LinkedInClient(access_token="tok", person_urn="urn:li:person:x")
        headers = client._default_headers()
        assert headers["Authorization"] == "Bearer tok"
        assert headers["LinkedIn-Version"] == LINKEDIN_VERSION
        assert headers["X-Restli-Protocol-Version"] == "2.0.0"


class TestCreatePost:
    def _make_client(self):
        return LinkedInClient(access_token="tok", person_urn="urn:li:person:me")

    @patch.object(requests.Session, "post")
    def test_text_only_post(self, mock_post):
        mock_post.return_value = make_mock_response(
            status_code=201,
            headers={"x-restli-id": "urn:li:share:111"},
        )
        client = self._make_client()
        urn = client.create_post(text="Hello LinkedIn!")
        assert urn == "urn:li:share:111"

        called_json = mock_post.call_args[1]["json"]
        assert called_json["author"] == "urn:li:person:me"
        assert called_json["commentary"] == "Hello LinkedIn!"
        assert called_json["visibility"] == "PUBLIC"
        assert "content" not in called_json

    @patch.object(requests.Session, "post")
    def test_post_with_image(self, mock_post):
        mock_post.return_value = make_mock_response(
            status_code=201,
            headers={"x-restli-id": "urn:li:share:222"},
        )
        client = self._make_client()
        urn = client.create_post(
            text="Image post",
            image_urn="urn:li:image:abc",
            image_alt_text="A nice photo",
        )
        assert urn == "urn:li:share:222"
        called_json = mock_post.call_args[1]["json"]
        assert called_json["content"]["media"]["id"] == "urn:li:image:abc"
        assert called_json["content"]["media"]["altText"] == "A nice photo"

    @patch.object(requests.Session, "post")
    def test_post_with_article(self, mock_post):
        mock_post.return_value = make_mock_response(
            status_code=201,
            headers={"x-restli-id": "urn:li:share:333"},
        )
        client = self._make_client()
        urn = client.create_post(
            text="Article post",
            article_url="https://eve.gd/post/",
            article_title="My Article",
            article_description="About things",
        )
        called_json = mock_post.call_args[1]["json"]
        assert called_json["content"]["article"]["source"] == "https://eve.gd/post/"
        assert called_json["content"]["article"]["title"] == "My Article"

    @patch.object(requests.Session, "post")
    def test_image_takes_precedence_over_article(self, mock_post):
        mock_post.return_value = make_mock_response(
            status_code=201,
            headers={"x-restli-id": "urn:li:share:444"},
        )
        client = self._make_client()
        client.create_post(
            text="Both",
            image_urn="urn:li:image:img",
            article_url="https://eve.gd/",
        )
        called_json = mock_post.call_args[1]["json"]
        assert "media" in called_json["content"]
        assert "article" not in called_json["content"]

    @patch.object(requests.Session, "post")
    def test_default_alt_text(self, mock_post):
        mock_post.return_value = make_mock_response(
            status_code=201, headers={"x-restli-id": "urn:x"},
        )
        client = self._make_client()
        client.create_post(text="x", image_urn="urn:li:image:x")
        called_json = mock_post.call_args[1]["json"]
        assert called_json["content"]["media"]["altText"] == "Blog post image"

    @patch.object(requests.Session, "post")
    def test_api_error_raises(self, mock_post):
        mock_post.return_value = make_mock_response(status_code=401)
        client = self._make_client()
        with pytest.raises(requests.exceptions.HTTPError):
            client.create_post(text="Should fail")


class TestUploadImage:
    def _make_client(self):
        return LinkedInClient(access_token="tok", person_urn="urn:li:person:me")

    @patch("linkedin_client.requests.put")
    @patch.object(requests.Session, "post")
    def test_upload_local_file(self, mock_session_post, mock_put, tmp_path):
        # Create a dummy image file
        img_file = tmp_path / "test.jpg"
        img_file.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-data")

        mock_session_post.return_value = make_mock_response(
            json_data={
                "value": {
                    "uploadUrl": "https://linkedin.com/upload/xyz",
                    "image": "urn:li:image:abc123",
                }
            }
        )
        mock_put.return_value = make_mock_response(status_code=201)

        client = self._make_client()
        urn = client.upload_image(image_path=str(img_file))

        assert urn == "urn:li:image:abc123"
        mock_put.assert_called_once()
        assert mock_put.call_args[0][0] == "https://linkedin.com/upload/xyz"

    def test_upload_missing_file_raises(self):
        client = self._make_client()
        with pytest.raises(FileNotFoundError):
            client.upload_image(image_path="/nonexistent/image.jpg")

    @patch("linkedin_client.requests.get")
    @patch("linkedin_client.requests.put")
    @patch.object(requests.Session, "post")
    def test_upload_from_url(self, mock_session_post, mock_put, mock_get):
        # Mock the download
        download_resp = MagicMock()
        download_resp.status_code = 200
        download_resp.headers = {"Content-Type": "image/jpeg"}
        download_resp.iter_content.return_value = [b"fake-image-data"]
        download_resp.raise_for_status.return_value = None
        mock_get.return_value = download_resp

        # Mock the init upload
        mock_session_post.return_value = make_mock_response(
            json_data={
                "value": {
                    "uploadUrl": "https://linkedin.com/upload/xyz",
                    "image": "urn:li:image:fromurl",
                }
            }
        )
        mock_put.return_value = make_mock_response(status_code=201)

        client = self._make_client()
        urn = client.upload_image(image_url="https://eve.gd/images/photo.jpg")

        assert urn == "urn:li:image:fromurl"
        mock_get.assert_called_once()


class TestDownloadImage:
    def _make_client(self):
        return LinkedInClient(access_token="tok", person_urn="urn:li:person:me")

    @patch("linkedin_client.requests.get")
    def test_extension_from_url(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"Content-Type": "application/octet-stream"}
        resp.iter_content.return_value = [b"data"]
        resp.raise_for_status.return_value = None
        mock_get.return_value = resp

        client = self._make_client()
        path = client._download_image("https://example.com/photo.png")
        assert path.endswith(".png")
        os.unlink(path)

    @patch("linkedin_client.requests.get")
    def test_extension_from_content_type(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"Content-Type": "image/webp"}
        resp.iter_content.return_value = [b"data"]
        resp.raise_for_status.return_value = None
        mock_get.return_value = resp

        client = self._make_client()
        path = client._download_image("https://example.com/image")
        assert path.endswith(".webp")
        os.unlink(path)

    @patch("linkedin_client.requests.get")
    def test_defaults_to_jpg(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"Content-Type": "application/octet-stream"}
        resp.iter_content.return_value = [b"data"]
        resp.raise_for_status.return_value = None
        mock_get.return_value = resp

        client = self._make_client()
        path = client._download_image("https://example.com/file")
        assert path.endswith(".jpg")
        os.unlink(path)
