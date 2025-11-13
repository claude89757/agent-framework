# Copyright (c) Microsoft. All rights reserved.
"""
智能压缩的消息存储实现

这个模块提供了一个自动压缩历史对话的 ChatMessageStore 实现。
当消息数量超过阈值时，会自动使用LLM总结早期对话，保留最近的消息。
"""

from collections.abc import Sequence
from typing import Any, MutableMapping

from agent_framework import ChatMessage, ChatMessageStore
from agent_framework._clients import ChatClientProtocol
from agent_framework._types import ChatOptions


class CompressingChatMessageStore(ChatMessageStore):
    """自动压缩历史对话的消息存储

    当消息数量超过 max_messages 时，自动总结早期消息并压缩历史记录。

    特性：
    - 自动检测何时需要压缩
    - 使用LLM生成高质量摘要
    - 保留最近的详细消息
    - 支持序列化和反序列化
    - 可配置压缩策略

    示例：
        ```python
        from agent_framework import ChatAgent
        from agent_framework.anthropic import AnthropicChatClient

        client = AnthropicChatClient(model="claude-3-5-sonnet-20241022")

        # 使用压缩存储创建Agent
        agent = ChatAgent(
            chat_client=client,
            name="assistant",
            chat_message_store_factory=lambda: CompressingChatMessageStore(
                max_messages=50,
                compress_to=10,
                summarizer_client=AnthropicChatClient(model="claude-3-5-haiku-20241022")
            )
        )

        # 正常使用，自动压缩
        thread = await agent.get_new_thread()
        for i in range(100):  # 即使100轮对话，也会自动压缩
            response = await agent.run(f"消息 {i}", thread=thread)
        ```
    """

    def __init__(
        self,
        messages: Sequence[ChatMessage] | None = None,
        *,
        max_messages: int = 50,
        compress_to: int = 10,
        summarizer_client: ChatClientProtocol | None = None,
        summary_max_tokens: int = 1000,
        enable_compression: bool = True,
    ):
        """初始化压缩消息存储

        Args:
            messages: 初始消息列表
            max_messages: 触发压缩的最大消息数量（默认50）
            compress_to: 压缩后保留的最近消息数量（默认10）
            summarizer_client: 用于生成摘要的LLM客户端（如果为None，需要后续设置）
            summary_max_tokens: 摘要的最大token数（默认1000）
            enable_compression: 是否启用自动压缩（默认True）
        """
        super().__init__(messages)
        self.max_messages = max_messages
        self.compress_to = compress_to
        self.summarizer_client = summarizer_client
        self.summary_max_tokens = summary_max_tokens
        self.enable_compression = enable_compression

        # 存储历史压缩的摘要
        self.compression_summary: str | None = None

        # 统计信息
        self.compression_count = 0
        self.total_compressed_messages = 0

    async def add_messages(self, messages: Sequence[ChatMessage]) -> None:
        """添加消息，如果超过阈值则自动压缩

        Args:
            messages: 要添加的消息序列
        """
        await super().add_messages(messages)

        # 检查是否需要压缩
        if self.enable_compression and len(self.messages) > self.max_messages:
            await self._compress_history()

    async def list_messages(self) -> list[ChatMessage]:
        """获取消息列表，如果有压缩摘要则包含在首位

        Returns:
            消息列表，可能包含压缩摘要作为系统消息
        """
        messages = await super().list_messages()

        # 如果有压缩摘要，将其作为系统消息插入
        if self.compression_summary:
            summary_message = ChatMessage(
                role="system",
                content=self._format_summary(self.compression_summary)
            )
            return [summary_message] + messages

        return messages

    async def _compress_history(self) -> None:
        """压缩历史对话

        该方法会：
        1. 分离要压缩的消息和要保留的消息
        2. 使用LLM生成压缩消息的摘要
        3. 如果已有历史摘要，将新旧摘要合并
        4. 更新消息列表，只保留最近的消息
        """
        if not self.summarizer_client:
            # 如果没有总结客户端，只做简单截断
            messages_to_remove = len(self.messages) - self.compress_to
            self.messages = self.messages[-self.compress_to:]
            self.total_compressed_messages += messages_to_remove
            self.compression_count += 1
            return

        # 1. 分离消息
        messages_to_compress = self.messages[:-self.compress_to]
        messages_to_keep = self.messages[-self.compress_to:]

        if not messages_to_compress:
            return

        # 2. 生成新摘要
        summary_prompt = self._build_summary_prompt(messages_to_compress)
        try:
            response = await self.summarizer_client.get_response(
                messages=[ChatMessage(role="user", content=summary_prompt)],
                chat_options=ChatOptions(max_tokens=self.summary_max_tokens),
            )
            new_summary = self._extract_content(response.messages[0])
        except Exception as e:
            # 如果总结失败，记录错误并只做截断
            print(f"警告：压缩失败 ({e})，使用简单截断")
            self.messages = messages_to_keep
            return

        # 3. 合并历史摘要（如果有）
        if self.compression_summary:
            try:
                merged_summary = await self._merge_summaries(
                    self.compression_summary,
                    new_summary
                )
                self.compression_summary = merged_summary
            except Exception as e:
                print(f"警告：摘要合并失败 ({e})，使用新摘要")
                self.compression_summary = new_summary
        else:
            self.compression_summary = new_summary

        # 4. 更新消息列表
        self.messages = messages_to_keep

        # 5. 更新统计
        self.total_compressed_messages += len(messages_to_compress)
        self.compression_count += 1

    def _build_summary_prompt(self, messages: Sequence[ChatMessage]) -> str:
        """构建总结提示词

        Args:
            messages: 要总结的消息列表

        Returns:
            总结提示词
        """
        # 过滤并格式化消息
        conversation_parts = []
        for msg in messages:
            content = self._extract_content(msg)
            if content:
                role_name = self._get_role_display_name(msg.role)
                conversation_parts.append(f"{role_name}: {content}")

        conversation_text = "\n\n".join(conversation_parts)

        return f"""请总结以下对话的关键信息。你的摘要应该：

1. **保留重要事实和数据** - 包括具体的数字、日期、名称等
2. **记录关键决策** - 用户做出的选择和偏好
3. **提取核心话题** - 主要讨论的主题和问题
4. **标注未解决的问题** - 任何悬而未决的事项

请用简洁但信息完整的方式输出摘要，使用要点列表格式。

<对话内容>
{conversation_text}
</对话内容>

请输出结构化摘要："""

    async def _merge_summaries(self, old_summary: str, new_summary: str) -> str:
        """合并新旧摘要

        Args:
            old_summary: 旧的摘要
            new_summary: 新生成的摘要

        Returns:
            合并后的摘要
        """
        if not self.summarizer_client:
            return f"{old_summary}\n\n---\n\n{new_summary}"

        merge_prompt = f"""请合并以下两段对话摘要，生成一个连贯统一的总结。

要求：
- 去除重复信息
- 保持时间顺序
- 突出重点和变化
- 保持简洁（不超过原有长度）

<早期摘要>
{old_summary}
</早期摘要>

<新增内容摘要>
{new_summary}
</新增内容摘要>

请输出合并后的摘要："""

        response = await self.summarizer_client.get_response(
            messages=[ChatMessage(role="user", content=merge_prompt)],
            chat_options=ChatOptions(max_tokens=self.summary_max_tokens + 500),
        )

        return self._extract_content(response.messages[0])

    def _format_summary(self, summary: str) -> str:
        """格式化摘要内容

        Args:
            summary: 原始摘要文本

        Returns:
            格式化后的摘要
        """
        header = "## 📝 对话历史摘要"
        footer = "\n\n---\n*以下是最近的详细对话记录*\n"

        return f"{header}\n\n{summary}{footer}"

    def _extract_content(self, message: ChatMessage) -> str:
        """提取消息的文本内容

        Args:
            message: 聊天消息

        Returns:
            消息的文本内容
        """
        if isinstance(message.content, str):
            return message.content
        elif isinstance(message.content, list):
            # 处理多模态内容
            text_parts = []
            for item in message.content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    text_parts.append(item)
            return " ".join(text_parts)
        return str(message.content)

    def _get_role_display_name(self, role: str) -> str:
        """获取角色的显示名称

        Args:
            role: 角色标识

        Returns:
            显示名称
        """
        role_names = {
            "user": "用户",
            "assistant": "助手",
            "system": "系统",
            "tool": "工具",
        }
        return role_names.get(role, role.capitalize())

    async def serialize(self, **kwargs: Any) -> dict[str, Any]:
        """序列化存储状态

        Returns:
            序列化的状态字典
        """
        state = await super().serialize(**kwargs)
        state.update({
            "compression_summary": self.compression_summary,
            "compression_count": self.compression_count,
            "total_compressed_messages": self.total_compressed_messages,
            "max_messages": self.max_messages,
            "compress_to": self.compress_to,
        })
        return state

    @classmethod
    async def deserialize(
        cls,
        serialized_store_state: MutableMapping[str, Any],
        **kwargs: Any
    ) -> "CompressingChatMessageStore":
        """从序列化状态恢复存储

        Args:
            serialized_store_state: 序列化的状态数据

        Returns:
            恢复的存储实例
        """
        # 调用父类方法恢复消息
        store = await super().deserialize(serialized_store_state, **kwargs)

        # 恢复压缩相关状态
        store.compression_summary = serialized_store_state.get("compression_summary")
        store.compression_count = serialized_store_state.get("compression_count", 0)
        store.total_compressed_messages = serialized_store_state.get("total_compressed_messages", 0)
        store.max_messages = serialized_store_state.get("max_messages", 50)
        store.compress_to = serialized_store_state.get("compress_to", 10)

        return store

    def get_stats(self) -> dict[str, Any]:
        """获取压缩统计信息

        Returns:
            统计信息字典
        """
        return {
            "current_messages": len(self.messages),
            "compression_count": self.compression_count,
            "total_compressed_messages": self.total_compressed_messages,
            "has_summary": self.compression_summary is not None,
            "summary_length": len(self.compression_summary) if self.compression_summary else 0,
        }
