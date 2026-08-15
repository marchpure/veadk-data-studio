from __future__ import annotations

from server.collaboration.contracts import ChannelResult, ChannelResultStatus


class PlainTextChannelRenderer:
    """Minimal renderer used by Phase 1 before CardKit Streaming is enabled."""

    @staticmethod
    def started() -> ChannelResult:
        return ChannelResult(
            run_id="pending",
            status=ChannelResultStatus.RUNNING,
            summary="正在分析，我会在当前会话里回复结果。",
            progress_steps=["queued"],
        )

    @staticmethod
    def completed(run_id: str, summary: str) -> ChannelResult:
        return ChannelResult(run_id=run_id, status=ChannelResultStatus.COMPLETED, summary=summary)

    @staticmethod
    def failed(run_id: str, message: str) -> ChannelResult:
        return ChannelResult(
            run_id=run_id,
            status=ChannelResultStatus.FAILED,
            summary=message,
            error_user_message=message,
        )
