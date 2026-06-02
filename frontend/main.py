"""
frontend/main.py

NiceGUI 前端应用，通过 httpx 调用 FastAPI 后端。

Classes:
    ApiClient        — 封装所有后端 HTTP 调用
    ScreenExportApp  — 封装完整 UI 构建与事件处理
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import httpx
from nicegui import app as ni_app
from nicegui import ui

sys.path.insert(0, str(Path(__file__).parent.parent))
import config


# ──────────────────────────────────────────────────────────────────────────────
# API 客户端
# ──────────────────────────────────────────────────────────────────────────────

class ApiClient:
    """封装与 FastAPI 后端的所有 HTTP 交互。"""

    def __init__(self, base_url: str) -> None:
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=60.0)

    async def upload(self, file_bytes: bytes, filename: str) -> str:
        """上传视频，返回 job_id。"""
        resp = await self._client.post(
            f"{self._base}/jobs/upload",
            files={"file": (filename, file_bytes, "video/mp4")},
        )
        resp.raise_for_status()
        return resp.json()["job_id"]

    async def start_process(self, job_id: str, params: dict) -> None:
        """启动视频处理。"""
        resp = await self._client.post(
            f"{self._base}/jobs/{job_id}/process",
            json=params,
        )
        resp.raise_for_status()

    async def get_job(self, job_id: str) -> dict:
        """查询 job 状态。"""
        resp = await self._client.get(f"{self._base}/jobs/{job_id}")
        resp.raise_for_status()
        return resp.json()

    async def list_screenshots(self, job_id: str) -> list[str]:
        """返回截图文件名列表。"""
        resp = await self._client.get(f"{self._base}/jobs/{job_id}/screenshots")
        resp.raise_for_status()
        return resp.json()["screenshots"]

    def screenshot_url(self, job_id: str, filename: str) -> str:
        """返回截图图片的直接 URL（供 ui.image 使用）。"""
        return f"{self._base}/jobs/{job_id}/screenshots/{filename}"

    async def generate_docx(self, job_id: str) -> None:
        """启动 DOCX 生成。"""
        resp = await self._client.post(f"{self._base}/jobs/{job_id}/generate-docx")
        resp.raise_for_status()

    def download_url(self, job_id: str) -> str:
        """返回 DOCX 下载链接。"""
        return f"{self._base}/jobs/{job_id}/download"

    async def stream_progress(self, job_id: str):
        """异步生成 SSE 事件（每次 yield 一个 dict）。"""
        url = f"{self._base}/jobs/{job_id}/progress"
        async with self._client.stream("GET", url, timeout=None) as resp:
            async for line in resp.aiter_lines():
                line = line.strip()
                if line.startswith("data:"):
                    import json
                    payload = line[len("data:"):].strip()
                    if payload:
                        yield json.loads(payload)

    async def aclose(self) -> None:
        await self._client.aclose()


# ──────────────────────────────────────────────────────────────────────────────
# 主应用类
# ──────────────────────────────────────────────────────────────────────────────

class ScreenExportApp:
    """
    封装 NiceGUI 页面的构建与所有事件处理。

    生命周期：每个浏览器连接实例化一次，通过 @ui.page('/') 工厂函数创建。
    """

    def __init__(self, api: ApiClient) -> None:
        self._api = api

        # 状态
        self._job_id: str | None = None
        self._file_bytes: bytes | None = None
        self._filename: str = "video.mp4"

        # UI 组件引用（build 阶段赋值）
        self._upload_label: ui.label | None = None
        self._btn_start: ui.button | None = None
        self._btn_generate: ui.button | None = None
        self._btn_download: ui.button | None = None
        self._progress_bar: ui.linear_progress | None = None
        self._log: ui.log | None = None
        self._preview_grid: ui.grid | None = None
        self._status_label: ui.label | None = None

        # 参数绑定
        self._params: dict[str, Any] = {
            "sample_fps": 5,
            "change_threshold": 3.0,
            "stable_seconds": 2.0,
            "hash_threshold": 5,
        }

    # ── 页面构建 ──────────────────────────────────────

    def build(self) -> None:
        """构建完整 UI 页面。"""
        with ui.column().classes("w-full max-w-4xl mx-auto p-6 gap-6"):
            ui.label("视频截图提取工具").classes("text-3xl font-bold")
            self._build_upload_section()
            self._build_params_section()
            self._build_action_buttons()
            self._build_progress_section()
            self._build_preview_section()

    def _build_upload_section(self) -> None:
        with ui.card().classes("w-full"):
            ui.label("上传视频").classes("text-lg font-semibold mb-2")
            self._upload_label = ui.label("未选择文件").classes("text-gray-500 text-sm")

            def handle_upload(e):
                self._file_bytes = e.content.read()
                self._filename = e.name
                self._upload_label.set_text(f"已选择：{e.name}（{len(self._file_bytes) / 1024 / 1024:.1f} MB）")
                if self._btn_start:
                    self._btn_start.enable()

            ui.upload(
                label="选择视频文件",
                on_upload=handle_upload,
                auto_upload=True,
            ).props("accept=video/*").classes("w-full")

    def _build_params_section(self) -> None:
        with ui.card().classes("w-full"):
            ui.label("处理参数").classes("text-lg font-semibold mb-2")
            with ui.grid(columns=2).classes("w-full gap-4"):
                with ui.column():
                    ui.label("每秒采样帧数").classes("text-sm text-gray-600")
                    ui.number(
                        value=self._params["sample_fps"],
                        min=1, max=30, step=1,
                        on_change=lambda e: self._params.update(sample_fps=int(e.value)),
                    ).classes("w-full")

                with ui.column():
                    ui.label("帧差阈值").classes("text-sm text-gray-600")
                    ui.number(
                        value=self._params["change_threshold"],
                        min=0.1, max=50, step=0.5,
                        on_change=lambda e: self._params.update(change_threshold=float(e.value)),
                    ).classes("w-full")

                with ui.column():
                    ui.label("连续稳定秒数").classes("text-sm text-gray-600")
                    ui.number(
                        value=self._params["stable_seconds"],
                        min=0.5, max=10, step=0.5,
                        on_change=lambda e: self._params.update(stable_seconds=float(e.value)),
                    ).classes("w-full")

                with ui.column():
                    ui.label("哈希去重阈值").classes("text-sm text-gray-600")
                    ui.number(
                        value=self._params["hash_threshold"],
                        min=1, max=30, step=1,
                        on_change=lambda e: self._params.update(hash_threshold=int(e.value)),
                    ).classes("w-full")

    def _build_action_buttons(self) -> None:
        with ui.row().classes("w-full gap-4 items-center"):
            self._btn_start = ui.button(
                "开始处理",
                on_click=self._on_start,
            ).props("color=primary").classes("flex-1")
            self._btn_start.disable()

            self._btn_generate = ui.button(
                "生成 DOCX",
                on_click=self._on_generate,
            ).props("color=secondary").classes("flex-1")
            self._btn_generate.disable()

            self._btn_download = ui.button(
                "下载 DOCX",
                on_click=self._on_download,
            ).props("color=positive").classes("flex-1")
            self._btn_download.disable()

        self._status_label = ui.label("").classes("text-sm text-gray-500 w-full text-center")

    def _build_progress_section(self) -> None:
        with ui.card().classes("w-full"):
            ui.label("处理进度").classes("text-lg font-semibold mb-2")
            self._progress_bar = ui.linear_progress(value=0).classes("w-full mb-2")
            self._log = ui.log(max_lines=200).classes("w-full h-40 font-mono text-xs")

    def _build_preview_section(self) -> None:
        with ui.card().classes("w-full"):
            ui.label("截图预览").classes("text-lg font-semibold mb-2")
            self._preview_grid = ui.grid(columns=3).classes("w-full gap-2")

    # ── 事件处理 ──────────────────────────────────────

    async def _on_start(self) -> None:
        """上传视频并启动处理。"""
        if not self._file_bytes:
            ui.notify("请先上传视频文件", type="warning")
            return

        self._btn_start.disable()
        self._btn_generate.disable()
        self._btn_download.disable()
        self._log.clear()
        self._progress_bar.set_value(0)
        self._preview_grid.clear()
        self._set_status("正在上传视频…")

        try:
            self._job_id = await self._api.upload(self._file_bytes, self._filename)
            self._set_status("上传成功，启动处理…")
            await self._api.start_process(self._job_id, self._params)
            await self._listen_sse()
        except Exception as exc:
            ui.notify(f"错误：{exc}", type="negative")
            self._set_status(f"错误：{exc}")
            self._btn_start.enable()

    async def _listen_sse(self) -> None:
        """消费 SSE 进度流，更新进度条和日志。"""
        if not self._job_id:
            return

        self._set_status("处理中…")
        try:
            async for event in self._api.stream_progress(self._job_id):
                etype = event.get("type")

                if etype == "progress":
                    total = event.get("total", 0)
                    current = event.get("current", 0)
                    if total > 0:
                        self._progress_bar.set_value(current / total)
                    msg = event.get("message", "")
                    saved = event.get("saved", 0)
                    self._log.push(f"{msg}  [已保存 {saved} 张]")

                elif etype == "done":
                    self._progress_bar.set_value(1.0)
                    count = event.get("saved", 0)
                    self._log.push(f"✓ 处理完成，共提取 {count} 张截图")
                    self._set_status(f"处理完成，共 {count} 张截图")
                    self._btn_generate.enable()
                    await self._load_screenshots()
                    break

                elif etype == "error":
                    msg = event.get("message", "未知错误")
                    self._log.push(f"✗ 错误：{msg}")
                    self._set_status(f"处理失败：{msg}")
                    ui.notify(f"处理失败：{msg}", type="negative")
                    self._btn_start.enable()
                    break

                await asyncio.sleep(0)  # 让出事件循环，保持 UI 响应

        except Exception as exc:
            self._set_status(f"SSE 连接断开：{exc}")
            self._log.push(f"SSE 断开：{exc}")
            self._btn_start.enable()

    async def _load_screenshots(self) -> None:
        """处理完成后从后端加载截图列表并渲染预览。"""
        if not self._job_id:
            return
        try:
            filenames = await self._api.list_screenshots(self._job_id)
            self._preview_grid.clear()
            with self._preview_grid:
                for name in filenames:
                    url = self._api.screenshot_url(self._job_id, name)
                    with ui.card().tight():
                        ui.image(url).classes("w-full")
                        ui.label(name).classes("text-xs text-center text-gray-500 py-1")
        except Exception as exc:
            ui.notify(f"加载截图失败：{exc}", type="warning")

    async def _on_generate(self) -> None:
        """触发后端生成 DOCX。"""
        if not self._job_id:
            return
        self._btn_generate.disable()
        self._set_status("生成 DOCX 中…")
        try:
            await self._api.generate_docx(self._job_id)
            await self._poll_until_done()
        except Exception as exc:
            ui.notify(f"生成失败：{exc}", type="negative")
            self._set_status(f"生成失败：{exc}")
            self._btn_generate.enable()

    async def _poll_until_done(self) -> None:
        """轮询 job 状态直到 done 或 error。"""
        for _ in range(120):  # 最多等 2 分钟
            await asyncio.sleep(1)
            try:
                job = await self._api.get_job(self._job_id)
            except Exception:
                continue

            status = job.get("status")
            if status == "done":
                self._set_status("DOCX 已生成，点击下载")
                self._btn_download.enable()
                ui.notify("DOCX 生成完成！", type="positive")
                return
            elif status == "error":
                msg = job.get("error_message", "未知错误")
                self._set_status(f"生成失败：{msg}")
                ui.notify(f"生成失败：{msg}", type="negative")
                self._btn_generate.enable()
                return

        self._set_status("生成超时，请重试")
        self._btn_generate.enable()

    def _on_download(self) -> None:
        """打开 DOCX 下载链接（在新标签页中触发浏览器下载）。"""
        if not self._job_id:
            return
        url = self._api.download_url(self._job_id)
        ui.navigate.to(url, new_tab=True)

    def _set_status(self, text: str) -> None:
        if self._status_label:
            self._status_label.set_text(text)


# ──────────────────────────────────────────────────────────────────────────────
# 页面注册与启动入口
# ──────────────────────────────────────────────────────────────────────────────

_api_client = ApiClient(config.API_BASE_URL)


@ui.page("/")
def index() -> None:
    """每次浏览器连接时实例化新的 ScreenExportApp。"""
    app_instance = ScreenExportApp(_api_client)
    app_instance.build()


@ni_app.on_shutdown
async def shutdown() -> None:
    await _api_client.aclose()


if __name__ == "__main__":
    ui.run(
        host="0.0.0.0",
        port=config.FRONTEND_PORT,
        title="视频截图提取工具",
        favicon="🎬",
        root_path=config.FRONTEND_ROOT_PATH,
        reload=False,
    )
