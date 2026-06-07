import asyncio
import httpx
import time
import os

TARGET_URL = "http://127.0.0.1:8000" # 确保你的 FastAPI 处于启动状态

TEST_FILES = {
    "逻辑压测 (笑傲群戏)": "stress_files/logic_stress.txt",
    "边界压测 (巨型单行)": "stress_files/boundary_stress.txt",
    "格式压测 (符号流)": "stress_files/format_stress.txt"
}

async def run_single_stress(test_name: str, file_path: str):
    if not os.path.exists(file_path):
        print(f"❌ 未找到文件: {file_path}，请先准备好素材！")
        return

    raw_text = open(file_path, "r", encoding="utf-8").read()
    
    timeout_config = httpx.Timeout(timeout=600.0, read=None)  # 读不限时，防长 Pipeline 断开
    async with httpx.AsyncClient(timeout=timeout_config) as client:
        print(f"🚀 [{test_name}] 正在向后端注入 {len(raw_text)} 字的文本...")
        start_time = time.time()
        
        # 1. 测试 POST /api/convert 的毫秒级响应
        try:
            res = await client.post(f"{TARGET_URL}/api/convert", json={"text": raw_text})
            if res.status_code != 200:
                print(f"❌ [{test_name}] POST 失败: HTTP {res.status_code}")
                return
            task_id = res.json().get("task_id")
            print(f"✅ [{test_name}] 成功拿到 TaskID: {task_id} (耗时: {time.time() - start_time:.3f}s)")
        except Exception as e:
            print(f"❌ [{test_name}] 连接后端失败: {e}")
            return

        # 2. 测试 SSE 总线监听
        print(f"📡 [{test_name}] 接入 SSE 通知总线，开始监听进度条...")
        sse_start = time.time()
        try:
            async with client.stream("GET", f"{TARGET_URL}/api/convert/{task_id}/stream") as response:
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        print(f"🔄 [{test_name}] 状态同步 -> {line}")
                        if '"progress": 1.0' in line or '"stage": "done"' in line:
                            print(f"🎉 [{test_name}] 核心 Pipeline 100% 跑通！")
                            break
            print(f"🏁 [{test_name}] 流式生命周期结束，总耗时: {time.time() - sse_start:.2f}s")
        except Exception as e:
            print(f"❌ [{test_name}] SSE 链路异常断开: {e}")

async def main():
    print("🔥 Looploop v0.45 工业级异步架构联合压测启动！")
    # 同时并发跑三个地狱级测试
    tasks = [run_single_stress(name, path) for name, path in TEST_FILES.items()]
    await asyncio.gather(*tasks)
    print("\n✨ 压测结束。请检查后端控制台是否有报错日志。")

if __name__ == "__main__":
    asyncio.run(main())