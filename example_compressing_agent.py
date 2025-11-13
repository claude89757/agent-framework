#!/usr/bin/env python3
"""
智能压缩Agent的使用示例

展示如何使用 CompressingChatMessageStore 创建具有自动上下文压缩能力的Agent。
"""

import asyncio
import os

from agent_framework import ChatAgent, ChatMessage
from agent_framework.anthropic import AnthropicChatClient

from compressing_message_store import CompressingChatMessageStore


async def basic_example():
    """基础示例：使用压缩存储创建Agent"""
    print("=== 基础示例 ===\n")

    # 1. 创建LLM客户端
    main_client = AnthropicChatClient(
        model="claude-3-5-sonnet-20241022",
        api_key=os.environ.get("ANTHROPIC_API_KEY")
    )

    # 2. 创建用于总结的快速模型客户端
    summarizer_client = AnthropicChatClient(
        model="claude-3-5-haiku-20241022",  # 使用更快速的模型做总结
        api_key=os.environ.get("ANTHROPIC_API_KEY")
    )

    # 3. 创建压缩存储工厂
    def create_compressing_store():
        return CompressingChatMessageStore(
            max_messages=20,           # 20条消息后触发压缩
            compress_to=5,             # 压缩后保留5条最近消息
            summarizer_client=summarizer_client,
            summary_max_tokens=800,
            enable_compression=True,
        )

    # 4. 创建Agent
    agent = ChatAgent(
        chat_client=main_client,
        name="智能助手",
        instructions="你是一个有帮助的AI助手，能够记住之前的对话内容。",
        chat_message_store_factory=create_compressing_store
    )

    # 5. 创建线程并开始对话
    thread = await agent.get_new_thread()

    # 模拟长对话
    topics = [
        "我叫张三，是一名软件工程师",
        "我正在学习AI和机器学习",
        "我最喜欢的编程语言是Python",
        "我最近在做一个智能体项目",
        "这个项目需要处理长对话",
        "我需要实现上下文压缩功能",
    ]

    for i, topic in enumerate(topics, 1):
        print(f"[轮次 {i}] 用户: {topic}")
        response = await agent.run(topic, thread=thread)
        print(f"[轮次 {i}] 助手: {response.data}\n")

    # 6. 查看压缩统计
    if hasattr(thread.message_store, 'get_stats'):
        stats = thread.message_store.get_stats()
        print("📊 压缩统计:")
        print(f"  - 当前消息数: {stats['current_messages']}")
        print(f"  - 压缩次数: {stats['compression_count']}")
        print(f"  - 总计压缩消息数: {stats['total_compressed_messages']}")
        print(f"  - 是否有摘要: {stats['has_summary']}")

    # 7. 测试记忆：询问早期信息
    print("\n--- 测试记忆 ---")
    memory_test = "我叫什么名字？我是做什么工作的？"
    print(f"用户: {memory_test}")
    response = await agent.run(memory_test, thread=thread)
    print(f"助手: {response.data}")


async def serialization_example():
    """序列化示例：保存和恢复对话状态"""
    print("\n\n=== 序列化示例 ===\n")

    # 创建Agent和存储
    client = AnthropicChatClient(
        model="claude-3-5-sonnet-20241022",
        api_key=os.environ.get("ANTHROPIC_API_KEY")
    )

    def create_store():
        return CompressingChatMessageStore(
            max_messages=10,
            compress_to=3,
            summarizer_client=AnthropicChatClient(
                model="claude-3-5-haiku-20241022",
                api_key=os.environ.get("ANTHROPIC_API_KEY")
            )
        )

    agent = ChatAgent(
        chat_client=client,
        name="助手",
        chat_message_store_factory=create_store
    )

    # 1. 创建对话
    thread = await agent.get_new_thread()
    await agent.run("我喜欢蓝色", thread=thread)
    await agent.run("我的生日是5月1日", thread=thread)

    print("✅ 已创建对话并添加信息")

    # 2. 序列化状态
    serialized = await thread.serialize()
    print(f"✅ 已序列化状态 (大小: {len(str(serialized))} 字符)")

    # 3. 创建新Agent并恢复状态
    agent2 = ChatAgent(
        chat_client=client,
        name="助手2",
        chat_message_store_factory=create_store
    )

    thread2 = await agent2.deserialize_thread(serialized)
    print("✅ 已恢复对话状态")

    # 4. 测试恢复的记忆
    response = await agent2.run("我喜欢什么颜色？", thread=thread2)
    print(f"用户: 我喜欢什么颜色？")
    print(f"助手: {response.data}")


async def stress_test():
    """压力测试：大量消息的压缩性能"""
    print("\n\n=== 压力测试 ===\n")

    client = AnthropicChatClient(
        model="claude-3-5-sonnet-20241022",
        api_key=os.environ.get("ANTHROPIC_API_KEY")
    )

    def create_store():
        return CompressingChatMessageStore(
            max_messages=15,
            compress_to=5,
            summarizer_client=AnthropicChatClient(
                model="claude-3-5-haiku-20241022",
                api_key=os.environ.get("ANTHROPIC_API_KEY")
            )
        )

    agent = ChatAgent(
        chat_client=client,
        name="助手",
        chat_message_store_factory=create_store
    )

    thread = await agent.get_new_thread()

    # 发送大量消息
    num_messages = 50
    print(f"正在发送 {num_messages} 条消息...")

    for i in range(num_messages):
        await agent.run(f"这是第 {i+1} 条消息", thread=thread)
        if (i + 1) % 10 == 0:
            print(f"  已处理 {i+1} 条消息")

    # 查看最终统计
    stats = thread.message_store.get_stats()
    print("\n📊 最终统计:")
    print(f"  - 发送消息总数: {num_messages}")
    print(f"  - 存储中的消息数: {stats['current_messages']}")
    print(f"  - 压缩次数: {stats['compression_count']}")
    print(f"  - 压缩掉的消息数: {stats['total_compressed_messages']}")
    print(f"  - 压缩率: {stats['total_compressed_messages']/num_messages*100:.1f}%")

    # 测试最终记忆
    print("\n--- 测试最终记忆 ---")
    response = await agent.run("请回忆一下我们讨论了什么？", thread=thread)
    print(f"助手: {response.data}")


async def compare_with_without_compression():
    """对比示例：有无压缩的区别"""
    print("\n\n=== 对比示例 ===\n")

    client = AnthropicChatClient(
        model="claude-3-5-sonnet-20241022",
        api_key=os.environ.get("ANTHROPIC_API_KEY")
    )

    # 1. 无压缩的Agent
    from agent_framework import ChatMessageStore

    agent_no_compress = ChatAgent(
        chat_client=client,
        name="无压缩助手",
        chat_message_store_factory=ChatMessageStore
    )

    # 2. 有压缩的Agent
    def create_store():
        return CompressingChatMessageStore(
            max_messages=10,
            compress_to=3,
            summarizer_client=AnthropicChatClient(
                model="claude-3-5-haiku-20241022",
                api_key=os.environ.get("ANTHROPIC_API_KEY")
            )
        )

    agent_with_compress = ChatAgent(
        chat_client=client,
        name="压缩助手",
        chat_message_store_factory=create_store
    )

    # 发送相同的消息
    messages = [f"消息 {i}" for i in range(20)]

    thread_no_compress = await agent_no_compress.get_new_thread()
    thread_with_compress = await agent_with_compress.get_new_thread()

    for msg in messages:
        await agent_no_compress.run(msg, thread=thread_no_compress)
        await agent_with_compress.run(msg, thread=thread_with_compress)

    # 对比结果
    msgs_no_compress = await thread_no_compress.message_store.list_messages()
    msgs_with_compress = await thread_with_compress.message_store.list_messages()

    print("📊 对比结果:")
    print(f"  无压缩存储的消息数: {len(msgs_no_compress)}")
    print(f"  有压缩存储的消息数: {len(msgs_with_compress)}")
    print(f"  节省的消息数: {len(msgs_no_compress) - len(msgs_with_compress)}")

    stats = thread_with_compress.message_store.get_stats()
    print(f"\n  压缩统计:")
    print(f"    - 压缩次数: {stats['compression_count']}")
    print(f"    - 总计压缩: {stats['total_compressed_messages']} 条消息")


async def main():
    """运行所有示例"""
    print("🚀 智能压缩Agent示例程序\n")
    print("=" * 60)

    # 检查API密钥
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("❌ 错误: 请设置 ANTHROPIC_API_KEY 环境变量")
        return

    try:
        # 运行基础示例
        await basic_example()

        # 运行序列化示例
        await serialization_example()

        # 运行压力测试（可选，会发送较多请求）
        # await stress_test()

        # 运行对比示例
        # await compare_with_without_compression()

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("✅ 示例运行完成")


if __name__ == "__main__":
    asyncio.run(main())
