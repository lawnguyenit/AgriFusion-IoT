"""Feature selection and alignment gates before model fitting."""

from .contracts import PretrainAuditConfig, PretrainAuditResult
from .pipeline import run_pretrain_audit

__all__ = ["PretrainAuditConfig", "PretrainAuditResult", "run_pretrain_audit"]
