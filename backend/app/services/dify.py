from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings


import uuid


class DifyConfigError(RuntimeError):
    pass


class DifyRequestError(RuntimeError):
    pass


_MOCK_DATASET_ID: str | None = None
_MOCK_CHAT_ANSWERS: dict[str, str] = {
    "PCR": "根据项目资料和知识图谱，PCR 条件优化实验中使用的是 Taq DNA Polymerase 体系，包含 dNTP、MgCl2 和模板 DNA。退火温度梯度实验表明 58℃ 时条带最清晰，非特异性扩增最少。详细体系配置和循环条件可参考项目资料库中的 PCR 实验方案。",
    "退火温度": "退火温度优化依据来自项目资料库中的 PCR 体系配置说明。实验设置了 55℃-65℃ 梯度，结果显示 58℃ 时目标条带最清晰，非特异性条带最少。这一发现记录在'PCR 条件优化实验'笔记中。",
    "CCK-8": "CCK-8 检测步骤和读数要求主要依据项目资料库中的细胞活力检测参考文档。标准流程为：每孔加入 10μL CCK-8 试剂，37℃ 孵育 1-4 小时，用酶标仪在 450nm 处读取吸光度。",
    "细胞活力": "根据'细胞活力检测实验'笔记，处理组细胞活力较对照组下降约 18%，重复孔结果稳定。检测使用 CCK-8 法，在酶标仪上读取 450nm 吸光度。详细统计方法见项目资料库。",
    "Western": "Western Blot 实验使用 RIPA 裂解液提取蛋白，BCA 法定量。一抗孵育过夜后使用对应二抗，ECL 显影。结果显示目标蛋白在处理组表达降低，内参条带稳定。相关试剂和仪器信息已在知识图谱中记录。",
    "试剂": "根据实验知识图谱，项目中使用的主要试剂包括：Taq DNA Polymerase、dNTP、MgCl2、CCK-8、PBS、DMEM 培养基、RIPA 裂解液、BCA 试剂盒以及多种抗体。详细试剂信息可查看知识图谱中的试剂实体节点。",
    "仪器": "知识图谱显示项目中使用的主要仪器包括：PCR Thermal Cycler、酶标仪、CO2 培养箱、电泳仪、转膜仪和凝胶成像系统。这些仪器关联到对应的实验笔记。",
    "样本": "项目涉及多种实验样本：PCR 实验使用样本 A 和样本 B；细胞活力检测使用处理组和对照组细胞；Western Blot 使用蛋白样本 P1 和 P2。样本信息已在知识图谱中结构化记录。",
    "实验类型": "当前项目包含三种实验类型：PCR（聚合酶链式反应）、细胞培养实验和 Western Blot（蛋白免疫印迹）。每种实验类型都关联了对应的实验笔记、试剂和仪器信息。",
    "结果": "项目主要实验结果：1）PCR 退火温度 58℃ 时扩增效果最佳；2）处理组细胞活力下降约 18%；3）处理组目标蛋白表达降低。详细结果数据可在对应实验笔记中查看。",
}


def _is_mock() -> bool:
    settings = get_settings()
    dataset_key = (settings.dify_dataset_api_key or "").strip()
    chat_key = (settings.dify_chat_app_api_key or "").strip()
    if dataset_key and chat_key and dataset_key != "replace-with-dify-dataset-api-key" and chat_key != "replace-with-dify-chat-app-api-key":
        return False
    return True


def _mock_answer(query: str) -> str:
    """根据问题关键词返回模拟回答"""
    for keyword, answer in _MOCK_CHAT_ANSWERS.items():
        if keyword in query:
            return answer
    return (
        f"根据项目资料库和实验知识图谱，{query}的相关信息已在系统中记录。"
        f"您可以查看对应的实验笔记和知识图谱节点获取详细数据。系统已保存本次问答的图谱依据和资料来源。"
    )


class DifyClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.dify_api_base_url.rstrip("/")
        self.dataset_api_key = settings.dify_dataset_api_key
        self.chat_app_api_key = settings.dify_chat_app_api_key
        self.indexing_technique = settings.dify_default_indexing_technique
        self.mock = _is_mock()

    def _dataset_headers(self) -> dict[str, str]:
        if self.mock:
            return {}
        if not self.dataset_api_key:
            raise DifyConfigError("DIFY_DATASET_API_KEY is not configured")
        return {"Authorization": f"Bearer {self.dataset_api_key}"}

    def _chat_headers(self) -> dict[str, str]:
        if self.mock:
            return {}
        if not self.chat_app_api_key:
            raise DifyConfigError("DIFY_CHAT_APP_API_KEY is not configured")
        return {"Authorization": f"Bearer {self.chat_app_api_key}"}

    async def create_dataset(self, name: str) -> dict[str, Any]:
        if self.mock:
            global _MOCK_DATASET_ID
            _MOCK_DATASET_ID = f"mock-ds-{uuid.uuid4().hex[:12]}"
            return {"id": _MOCK_DATASET_ID, "name": name, "permission": "only_me"}
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
        if self.mock:
            return {
                "document": {"id": f"mock-doc-{uuid.uuid4().hex[:12]}"},
                "dataset_id": dataset_id,
            }
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
        if self.mock:
            answer = _mock_answer(query)
            return {
                "answer": answer,
                "conversation_id": f"mock-conv-{uuid.uuid4().hex[:12]}",
                "metadata": {
                    "retriever_resources": [
                        {
                            "document_id": f"mock-doc-{uuid.uuid4().hex[:12]}",
                            "document_name": "项目资料库参考文档",
                            "content": f"与「{query}」相关的资料片段。",
                        }
                    ]
                },
            }
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
