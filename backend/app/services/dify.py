from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings


class DifyConfigError(RuntimeError):
    pass


class DifyRequestError(RuntimeError):
    pass


class DifyClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.dify_api_base_url.rstrip("/")
        self.dataset_api_key = settings.dify_dataset_api_key
        self.chat_app_api_key = settings.dify_chat_app_api_key
        self.indexing_technique = settings.dify_default_indexing_technique

    def _dataset_headers(self) -> dict[str, str]:
        if not self.dataset_api_key:
            raise DifyConfigError("DIFY_DATASET_API_KEY is not configured")
        return {"Authorization": f"Bearer {self.dataset_api_key}"}

    def _chat_headers(self) -> dict[str, str]:
        if not self.chat_app_api_key:
            raise DifyConfigError("DIFY_CHAT_APP_API_KEY is not configured")
        return {"Authorization": f"Bearer {self.chat_app_api_key}"}

    async def create_dataset(self, name: str) -> dict[str, Any]:
        payload = {
            "name": name,
            "permission": "only_me",
            "indexing_technique": self.indexing_technique,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/v1/datasets",
                headers=self._dataset_headers(),
                json=payload,
            )
        return self._json_or_error(response)

    async def upload_document_file(self, dataset_id: str, file_path: str, filename: str) -> dict[str, Any]:
        path = Path(file_path)
        if not path.exists():
            raise DifyRequestError("Stored file is missing")
        data = {
            "data": (
                '{"indexing_technique":"'
                + self.indexing_technique
                + '","process_rule":{"mode":"automatic"}}'
            )
        }
        async with httpx.AsyncClient(timeout=120) as client:
            with path.open("rb") as buffer:
                response = await client.post(
                    f"{self.base_url}/v1/datasets/{dataset_id}/document/create-by-file",
                    headers=self._dataset_headers(),
                    data=data,
                    files={"file": (filename, buffer)},
                )
        return self._json_or_error(response)

    async def chat(self, query: str, user_id: str, dataset_id: str, graph_context: str | None = None) -> dict[str, Any]:
        final_query = query
        if graph_context:
            final_query = (
                "请结合以下实验知识图谱上下文和项目资料库检索结果回答用户问题。"
                "如果图谱上下文与资料库内容冲突，请优先说明不确定性，并引用可追溯来源。\n\n"
                f"{graph_context}\n\n"
                f"用户问题：{query}"
            )
        payload = {
            "inputs": {"dataset_id": dataset_id, "graph_context": graph_context or ""},
            "query": final_query,
            "response_mode": "blocking",
            "user": user_id,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat-messages",
                headers=self._chat_headers(),
                json=payload,
            )
        return self._json_or_error(response)

    @staticmethod
    def _json_or_error(response: httpx.Response) -> dict[str, Any]:
        if response.is_success:
            return response.json()
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise DifyRequestError(f"Dify request failed: {response.status_code} {detail}")


def extract_dify_document_id(payload: dict[str, Any]) -> str | None:
    document = payload.get("document")
    if isinstance(document, dict) and document.get("id"):
        return str(document["id"])
    if payload.get("id"):
        return str(payload["id"])
    return None


def extract_dify_sources(payload: dict[str, Any]) -> list[dict[str, Any]]:
    sources = payload.get("metadata", {}).get("retriever_resources", [])
    return sources if isinstance(sources, list) else []
