"""Tests for linkedin_client module."""

import os
from unittest.mock import MagicMock, patch

import pytest
import requests

from linkedin_client import LinkedInClient
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
        client = LinkedInClient(
            access_token="tok", person_urn="urn:li:person:x"
        )
        headers = client._default_headers()
        assert headers["Authorization"] == "Bearer tok"
        assert headers["X-Restli-Protocol-Version"] == "2.0.0"
        assert "LinkedIn-Version" not in headers


class TestGetProfile:
    def _make_client(self):
        return LinkedInClient(
            access_token="tok", person_urn="urn:li:person:me"
        )

    @patch.object(requests.Session, "get")
    def test_get_profile_success(self, mock_get):
        mock_get.return_value = make_mock_response(
            json_data={"name": "Martin Eve", "sub": "abc123"}
        )
        client = self._make_client()
        profile = client.get_profile()
        assert profile["name"] == "Martin Eve"

    @patch.object(requests.Session, "get")
    def test_get_profile_error_raises(self, mock_get):
        mock_get.return_value = make_mock_response(status_code=401)
        client = self._make_client()
        with pytest.raises(requests.exceptions.HTTPError):
            client.get_profile()


class TestCreatePost:
    def _make_client(self):
        return LinkedInClient(
            access_token="tok", person_urn="urn:li:person:me"
        )

    @patch.object(requests.Session, "post")
    def test_text_only_post(self, mock_post):
        mock_post.return_value = make_mock_response(
            status_code=201,
            headers={"x-restli-id": "urn:li:ugcPost:111"},
        )
        client = self._make_client()
        urn = client.create_post(text="Hello LinkedIn!")
        assert urn == "urn:li:ugcPost:111"

        called_json = mock_post.call_args[1]["json"]
        assert called_json["author"] == "urn:li:person:me"
        share = called_json["specificContent"]["com.linkedin.ugc.ShareContent"]
        assert share["shareCommentary"]["text"] == "Hello LinkedIn!"
        assert share["shareMediaCategory"] == "NONE"
        assert "media" not in share

    @patch.object(requests.Session, "post")
    def test_post_with_image(self, mock_post):
        mock_post.return_value = make_mock_response(
            status_code=201,
            headers={"x-restli-id": "urn:li:ugcPost:222"},
        )
        client = self._make_client()
        urn = client.create_post(
            text="Image post",
            image_urn="urn:li:digitalmediaAsset:abc",
            image_alt_text="A nice photo",
        )
        assert urn == "urn:li:ugcPost:222"
        called_json = mock_post.call_args[1]["json"]
        share = called_json["specificContent"]["com.linkedin.ugc.ShareContent"]
        assert share["shareMediaCategory"] == "IMAGE"
        assert share["media"][0]["media"] == "urn:li:digitalmediaAsset:abc"
        assert share["media"][0]["title"]["text"] == "A nice photo"

    @patch.object(requests.Session, "post")
    def test_post_with_article(self, mock_post):
        mock_post.return_value = make_mock_response(
            status_code=201,
            headers={"x-restli-id": "urn:li:ugcPost:333"},
        )
        client = self._make_client()
        client.create_post(
            text="Article post",
            article_url="https://eve.gd/post/",
            article_title="My Article",
            article_description="About things",
        )
        called_json = mock_post.call_args[1]["json"]
        share = called_json["specificContent"]["com.linkedin.ugc.ShareContent"]
        assert share["shareMediaCategory"] == "ARTICLE"
        assert share["media"][0]["originalUrl"] == "https://eve.gd/post/"
        assert share["media"][0]["title"]["text"] == "My Article"
        assert share["media"][0]["description"]["text"] == "About things"

    @patch.object(requests.Session, "post")
    def test_image_takes_precedence_over_article(self, mock_post):
        mock_post.return_value = make_mock_response(
            status_code=201,
            headers={"x-restli-id": "urn:li:ugcPost:444"},
        )
        client = self._make_client()
        client.create_post(
            text="Both",
            image_urn="urn:li:digitalmediaAsset:img",
            article_url="https://eve.gd/",
        )
        called_json = mock_post.call_args[1]["json"]
        share = called_json["specificContent"]["com.linkedin.ugc.ShareContent"]
        assert share["shareMediaCategory"] == "IMAGE"
        assert share["media"][0]["media"] == "urn:li:digitalmediaAsset:img"

    @patch.object(requests.Session, "post")
    def test_default_alt_text(self, mock_post):
        mock_post.return_value = make_mock_response(
            status_code=201,
            headers={"x-restli-id": "urn:x"},
        )
        client = self._make_client()
        client.create_post(text="x", image_urn="urn:li:digitalmediaAsset:x")
        called_json = mock_post.call_args[1]["json"]
        share = called_json["specificContent"]["com.linkedin.ugc.ShareContent"]
        assert share["media"][0]["title"]["text"] == "Blog post image"

    @patch.object(requests.Session, "post")
    def test_api_error_raises(self, mock_post):
        mock_post.return_value = make_mock_response(status_code=401)
        client = self._make_client()
        with pytest.raises(requests.exceptions.HTTPError):
            client.create_post(text="Should fail")


class TestUploadImage:
    def _make_client(self):
        return LinkedInClient(
            access_token="tok", person_urn="urn:li:person:me"
        )

    @patch("linkedin_client.requests.put")
    @patch.object(requests.Session, "post")
    def test_upload_local_file(self, mock_session_post, mock_put, tmp_path):
        img_file = tmp_path / "test.jpg"
        img_file.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-data")

        mock_session_post.return_value = make_mock_response(
            json_data={
                "value": {
                    "uploadMechanism": {
                        "com.linkedin.digitalmedia.uploading"
                        ".MediaUploadHttpRequest": {
                            "uploadUrl": ("https://linkedin.com/upload/xyz"),
                        }
                    },
                    "asset": "urn:li:digitalmediaAsset:abc123",
                }
            }
        )
        mock_put.return_value = make_mock_response(status_code=201)

        client = self._make_client()
        urn = client.upload_image(image_path=str(img_file))

        assert urn == "urn:li:digitalmediaAsset:abc123"
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
        download_resp = MagicMock()
        download_resp.status_code = 200
        download_resp.headers = {"Content-Type": "image/jpeg"}
        download_resp.iter_content.return_value = [b"fake-image-data"]
        download_resp.raise_for_status.return_value = None
        mock_get.return_value = download_resp

        mock_session_post.return_value = make_mock_response(
            json_data={
                "value": {
                    "uploadMechanism": {
                        "com.linkedin.digitalmedia.uploading"
                        ".MediaUploadHttpRequest": {
                            "uploadUrl": ("https://linkedin.com/upload/xyz"),
                        }
                    },
                    "asset": "urn:li:digitalmediaAsset:fromurl",
                }
            }
        )
        mock_put.return_value = make_mock_response(status_code=201)

        client = self._make_client()
        urn = client.upload_image(image_url="https://eve.gd/images/photo.jpg")

        assert urn == "urn:li:digitalmediaAsset:fromurl"
        mock_get.assert_called_once()

    @patch.object(requests.Session, "post")
    def test_upload_register_error_raises(self, mock_session_post, tmp_path):
        img_file = tmp_path / "test.jpg"
        img_file.write_bytes(b"data")
        mock_session_post.return_value = make_mock_response(status_code=403)
        client = self._make_client()
        with pytest.raises(requests.exceptions.HTTPError):
            client.upload_image(image_path=str(img_file))


class TestDownloadImage:
    def _make_client(self):
        return LinkedInClient(
            access_token="tok", person_urn="urn:li:person:me"
        )

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


class TestDiagnostics:
    def _make_client(self):
        return LinkedInClient(
            access_token="tok", person_urn="urn:li:person:me"
        )

    @patch.object(requests.Session, "post")
    def test_empty_403_includes_hints(self, mock_post):
        mock_post.return_value = make_mock_response(
            status_code=403,
            json_data={"message": "", "status": 403},
        )
        client = self._make_client()
        with pytest.raises(requests.exceptions.HTTPError):
            client.create_post(text="test")

    @patch.object(requests.Session, "post")
    def test_401_includes_hints(self, mock_post):
        mock_post.return_value = make_mock_response(
            status_code=401,
            json_data={"message": "Unauthorized"},
        )
        client = self._make_client()
        with pytest.raises(requests.exceptions.HTTPError):
            client.create_post(text="test")
