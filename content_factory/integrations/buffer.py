"""Buffer GraphQL API client (https://api.buffer.com).

Docs: developers.buffer.com. API key: Buffer → Settings → API
(sent as ``Authorization: Bearer <key>``).

Supported here: organizations/channels lookup and post creation
(``createPost`` with ``schedulingType: automatic``, ``mode: addToQueue`` or
``customScheduled``/``dueAt``). Buffer Free plan = 3 channels, so the queue
only targets the channels already connected to the account.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

ENDPOINT = "https://api.buffer.com"
ORG_ID = "68d276b0ab330eddbacc2da8"


class BufferError(RuntimeError):
    pass


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class BufferClient:
    token: str
    endpoint: str = ENDPOINT
    timeout: float = 30.0

    @classmethod
    def from_env(cls) -> "BufferClient":
        return cls(token=env("BUFFER_API_KEY"))

    def configured(self) -> bool:
        return bool(self.token)

    def gql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.token:
            raise BufferError("BUFFER_API_KEY is not set")
        body: Dict[str, Any] = {"query": query}
        if variables:
            body["variables"] = variables
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "content-factory-buffer/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as error:
            raise BufferError("HTTP %s: %s" % (error.code, error.read()[:300])) from error
        except Exception as error:  # noqa: BLE001
            raise BufferError("%s: %s" % (type(error).__name__, error)) from error
        errors = data.get("errors") or []
        if errors:
            raise BufferError("; ".join(str(item.get("message") or item) for item in errors)[:500])
        return data.get("data") or {}

    def organizations(self) -> List[Dict[str, Any]]:
        data = self.gql("query { account { organizations { id name } } }")
        return list(((data.get("account") or {}).get("organizations")) or [])

    def channels(self, organization_id: str = ORG_ID) -> List[Dict[str, Any]]:
        data = self.gql(
            "query GetChannels($organizationId: OrganizationId!) {"
            " channels(input: { organizationId: $organizationId }) { id name service } }",
            {"organizationId": organization_id},
        )
        return list(data.get("channels") or [])

    CREATE_POST = """
mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess { post { id text dueAt status } }
    ... on MutationError { message }
  }
}
"""

    DELETE_POST = """
mutation DeletePost($input: DeletePostInput!) {
  deletePost(input: $input) {
    ... on DeletePostSuccess { __typename }
    ... on VoidMutationError { message }
  }
}
"""

    def delete_post(self, post_id: str) -> None:
        """Remove a scheduled or sent post. Raises BufferError on failure."""
        data = self.gql(self.DELETE_POST, {"input": {"id": post_id}})
        result = data.get("deletePost") or {}
        if "message" in result:
            raise BufferError(str(result.get("message") or "deletePost failed"))

    def create_post(
        self,
        channel_id: str,
        text: str,
        mode: str = "addToQueue",
        due_at: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        assets: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "channelId": channel_id,
            "text": text,
            "schedulingType": "automatic",
            "mode": mode,
            "needsApproval": False,
            "source": "api",
        }
        if due_at:
            payload["dueAt"] = due_at
        if metadata:
            payload["metadata"] = metadata
        if assets:
            payload["assets"] = assets
        data = self.gql(self.CREATE_POST, {"input": payload})
        result = data.get("createPost") or {}
        if "post" not in result:
            raise BufferError(str(result.get("message") or "createPost failed"))
        return dict(result["post"])
