import json
import time
import uuid
import logging
import httpx
from typing import Dict, Any, AsyncGenerator
from fastapi import HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from loguru import logger

from app.core.config import settings
from app.providers.base_provider import BaseProvider
from app.services.browser_service import BrowserService
from app.utils.sse_utils import create_sse_data, create_chat_completion_chunk, DONE_CHUNK

class PerplexityProvider(BaseProvider):
    def __init__(self):
        self.solver = BrowserService()

    async def chat_completion(self, request_data: Dict[str, Any]) -> StreamingResponse:
        messages = request_data.get("messages", [])
        if not messages:
            raise HTTPException(status_code=400, detail="Messages cannot be empty")
        
        last_msg = next((m for m in reversed(messages) if m["role"] == "user"), None)
        if not last_msg:
            raise HTTPException(status_code=400, detail="No user message found")
        
        query = last_msg["content"]
        model = request_data.get("model", settings.DEFAULT_MODEL)
        request_id = f"req-{uuid.uuid4().hex[:8]}"

        await self.solver.refresh_context()

        payload = {
            "params": {
                "attachments": [],
                "language": "zh-CN",
                "timezone": "Asia/Shanghai",
                "search_focus": "internet",
                "sources": ["edgar", "social", "web", "scholar"],
                "frontend_uuid": str(uuid.uuid4()),
                "mode": "copilot",
                "model_preference": model,
                "is_related_query": False,
                "is_sponsored": False,
                "prompt_source": "user",
                "query_source": "home",
                "is_incognito": False,
                "time_from_first_type": 1344.2,
                "local_search_enabled": False,
                "use_schematized_api": True,
                "send_back_text_in_streaming_api": False,
                "supported_block_use_cases": [
                  "answer_modes", "media_items", "knowledge_cards", "inline_entity_cards", 
                  "place_widgets", "finance_widgets", "prediction_market_widgets", "sports_widgets", 
                  "flight_status_widgets", "news_widgets", "shopping_widgets", "jobs_widgets", 
                  "search_result_widgets", "clarification_responses", "inline_images", "inline_assets", 
                  "placeholder_cards", "diff_blocks", "inline_knowledge_cards", "entity_group_v2", 
                  "refinement_filters", "canvas_mode", "maps_preview", "answer_tabs", 
                  "price_comparison_widgets", "preserve_latex"
                ],
                "client_coordinates": None,
                "mentions": [],
                "skip_search_enabled": True,
                "is_nav_suggestions_disabled": False,
                "always_search_override": False,
                "override_no_search": False,
                "should_ask_for_mcp_tool_confirmation": True,
                "supported_features": ["browser_agent_permission_banner"],
                "version": "2.18"
            },
            "query_str": query
        }

        headers = self.solver.get_headers()
        headers["x-request-id"] = request_id
        cookies = self.solver.get_cookies()

        logger.info(f"=== 发送请求 [{request_id}] ===")

        async def stream_generator() -> AsyncGenerator[bytes, None]:
            client = httpx.AsyncClient(timeout=300, http2=True)
            try:
                async with client.stream(
                    "POST", 
                    settings.API_URL, 
                    json=payload, 
                    headers=headers, 
                    cookies=cookies
                ) as response:
                    
                    if response.status_code != 200:
                        error_text = await response.aread()
                        logger.error(f"上游错误 {response.status_code}: {error_text.decode('utf-8', errors='ignore')}")
                        if response.status_code == 403:
                            await self.solver.refresh_context(force=True)
                        yield create_sse_data(create_chat_completion_chunk(request_id, model, f"[Error: Upstream {response.status_code}]", "stop"))
                        yield DONE_CHUNK
                        return

                    last_full_text = ""
                    has_content = False
                    
                    async for line in response.aiter_lines():
                        line_str = line.strip()
                        if not line_str or not line_str.startswith("data: "): 
                            continue
                        
                        json_str = line_str[6:].strip()
                        if json_str == "[DONE]": continue
                        
                        try:
                            data = json.loads(json_str)
                            
                            # --- 核心解析逻辑 ---
                            current_full_text = ""

                            # 1. 尝试从 answer 字段获取 (可能是嵌套 JSON)
                            if "answer" in data:
                                raw_answer = data["answer"]
                                try:
                                    # 检查是否是 JSON 数组字符串 (如你日志所示)
                                    if isinstance(raw_answer, str) and raw_answer.strip().startswith("["):
                                        steps = json.loads(raw_answer)
                                        for step in steps:
                                            step_type = step.get("step_type")
                                            content = step.get("content", {})
                                            
                                            if step_type == "SEARCH_WEB":
                                                queries = content.get("queries", [])
                                                q_str = ", ".join([q["query"] for q in queries])
                                                current_full_text += f"> 🔍 正在搜索: {q_str}\n\n"
                                            
                                            elif step_type == "SEARCH_RESULTS":
                                                results = content.get("web_results", [])
                                                if results:
                                                    current_full_text += f"> 📚 找到 {len(results)} 个来源\n\n"

                                            elif step_type == "FINAL":
                                                # FINAL 里的 answer 可能又是 JSON 字符串
                                                final_answer_raw = content.get("answer")
                                                if isinstance(final_answer_raw, str):
                                                    try:
                                                        final_obj = json.loads(final_answer_raw)
                                                        if "answer" in final_obj:
                                                            current_full_text += final_obj["answer"]
                                                    except:
                                                        current_full_text += final_answer_raw
                                                else:
                                                    current_full_text += str(final_answer_raw)

                                    # 检查是否是普通 JSON 对象字符串
                                    elif isinstance(raw_answer, str) and raw_answer.strip().startswith("{"):
                                        inner_data = json.loads(raw_answer)
                                        if "answer" in inner_data:
                                            current_full_text = inner_data["answer"]
                                    else:
                                        current_full_text = raw_answer
                                except Exception as e:
                                    # 解析失败，回退到原始值
                                    current_full_text = raw_answer

                            # 2. 尝试从 text 字段获取 (逻辑同上)
                            elif "text" in data:
                                raw_text = data["text"]
                                try:
                                    if isinstance(raw_text, str) and raw_text.strip().startswith("["):
                                        # 处理数组情况 (同上)
                                        steps = json.loads(raw_text)
                                        for step in steps:
                                            step_type = step.get("step_type")
                                            content = step.get("content", {})
                                            if step_type == "FINAL":
                                                final_answer_raw = content.get("answer")
                                                if isinstance(final_answer_raw, str):
                                                    try:
                                                        final_obj = json.loads(final_answer_raw)
                                                        if "answer" in final_obj:
                                                            current_full_text += final_obj["answer"]
                                                    except:
                                                        current_full_text += final_answer_raw
                                    elif isinstance(raw_text, str) and raw_text.strip().startswith("{"):
                                        inner_data = json.loads(raw_text)
                                        if "answer" in inner_data:
                                            current_full_text = inner_data["answer"]
                                        elif "chunks" in inner_data:
                                            current_full_text = "".join(inner_data["chunks"])
                                    else:
                                        current_full_text = raw_text
                                except:
                                    current_full_text = raw_text

                            # --- 增量发送 ---
                            if current_full_text:
                                # 只有当新文本比旧文本长时才发送增量
                                # 注意：Perplexity 有时会重写前面的文本，这里简化处理，只追加
                                if len(current_full_text) > len(last_full_text):
                                    delta_text = current_full_text[len(last_full_text):]
                                    last_full_text = current_full_text
                                    has_content = True
                                    
                                    chunk = create_chat_completion_chunk(request_id, model, delta_text)
                                    yield create_sse_data(chunk)

                        except Exception as e:
                            logger.warning(f"解析失败: {e}")
                            pass
                    
                    if not has_content:
                        yield create_sse_data(create_chat_completion_chunk(request_id, model, "[Warning: No content returned]", "stop"))

                    yield create_sse_data(create_chat_completion_chunk(request_id, model, "", "stop"))
                    yield DONE_CHUNK

            except Exception as e:
                logger.error(f"流式请求异常: {e}")
                yield create_sse_data(create_chat_completion_chunk(request_id, model, f"[Error: {str(e)}]", "stop"))
                yield DONE_CHUNK
            finally:
                await client.aclose()

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    async def get_models(self) -> JSONResponse:
        return JSONResponse(content={
            "object": "list",
            "data": [{"id": m, "object": "model", "created": int(time.time()), "owned_by": "perplexity"} for m in settings.MODELS]
        })