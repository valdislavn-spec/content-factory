"""Внешние интеграции контент-завода (Dify workflow-приложения)."""

from .dify_workflow import DifyWorkflowClient, DifyWorkflowError

__all__ = ["DifyWorkflowClient", "DifyWorkflowError"]
