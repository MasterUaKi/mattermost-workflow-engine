# Author: Oleh Riabtsev
# File: app/workflow_engine.py
# Created: 2026-11-23
# Version: 1.1.0

"""
Core Document Approval Workflow Engine (FSM).
Manages workflow lifecycle transitions, sequential and parallel approval stages,
Mattermost card updates, and initiator notifications.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import WorkflowsConfig, WorkflowStepConfig
from app.i18n import Translator
from app.mattermost_client import MattermostClient
from app.models import (
    ApprovalTask,
    AuditLog,
    DocumentAttachment,
    TaskStatus,
    WorkflowInstance,
    WorkflowStatus,
)

logger = logging.getLogger("workflow_engine.core")


class WorkflowEngineError(Exception):
    """Base domain exception raised by the workflow engine."""

    def __init__(self, message_key: str, status_code: int = 400, **kwargs: Any) -> None:
        self.message_key = message_key
        self.status_code = status_code
        self.kwargs = kwargs
        super().__init__(message_key)


class WorkflowEngine:
    """Finite State Machine (FSM) orchestrating document approval workflows."""

    def __init__(
        self,
        workflows_config: WorkflowsConfig,
        mm_client: MattermostClient,
        translator: Translator,
    ) -> None:
        self.workflows_config = workflows_config
        self.mm_client = mm_client
        self.translator = translator

    async def start_workflow(
        self,
        db: AsyncSession,
        *,
        workflow_type: str,
        title: str,
        description: str | None,
        document_data: dict[str, Any],
        initiator_id: str,
        lang: str | None,
        saved_files: list[dict[str, Any]],
    ) -> WorkflowInstance:
        """
        Creates a new workflow instance, persists attachment metadata,
        and dispatches the initial workflow stage.
        """
        wf_def = self.workflows_config.workflows.get(workflow_type)
        if not wf_def:
            raise WorkflowEngineError(
                "api.err_unknown_workflow_type", status_code=404, workflow_type=workflow_type
            )

        effective_lang = self.translator.normalize_lang(
            lang or wf_def.default_lang or self.workflows_config.default_lang
        )

        instance = WorkflowInstance(
            workflow_type=workflow_type,
            title=title,
            description=description,
            document_data=document_data,
            initiator_id=initiator_id,
            lang=effective_lang,
            status=WorkflowStatus.IN_PROGRESS,
            current_step_index=0,
        )
        db.add(instance)
        await db.flush()  # Obtain generated instance.id

        # Register uploaded file metadata
        for file_meta in saved_files:
            attachment = DocumentAttachment(
                workflow_id=instance.id,
                filename=file_meta["filename"],
                content_type=file_meta["content_type"],
                storage_path=file_meta["storage_path"],
                file_size=file_meta["file_size"],
            )
            db.add(attachment)

        initiator_username = await self.mm_client.get_username(initiator_id)
        db.add(
            AuditLog(
                workflow_id=instance.id,
                actor_id=initiator_id,
                actor_username=initiator_username,
                action="WORKFLOW_STARTED",
                details=f"Workflow '{workflow_type}' started with language '{effective_lang}'.",
            )
        )
        await db.flush()

        # Dispatch the first step (index 0)
        await self._dispatch_step(db, instance, step_index=0, initiator_username=initiator_username)
        await db.commit()

        logger.info(
            self.translator.t_log(
                "workflow_started",
                workflow_id=instance.id,
                workflow_type=workflow_type,
                workflow_lang=effective_lang,
                initiator_id=initiator_id,
            )
        )
        return await self.get_workflow_details(db, instance.id)

    async def get_workflow_details(self, db: AsyncSession, workflow_id: str) -> WorkflowInstance:
        """Loads complete workflow state including tasks, attachments, and audit history."""
        stmt = (
            select(WorkflowInstance)
            .where(WorkflowInstance.id == workflow_id)
            .options(
                selectinload(WorkflowInstance.tasks),
                selectinload(WorkflowInstance.attachments),
                selectinload(WorkflowInstance.audit_logs),
            )
        )
        result = await db.execute(stmt)
        instance = result.scalar_one_or_none()
        if not instance:
            raise WorkflowEngineError(
                "api.err_workflow_not_found", status_code=404, workflow_id=workflow_id
            )
        return instance

    async def _dispatch_step(
        self,
        db: AsyncSession,
        instance: WorkflowInstance,
        step_index: int,
        initiator_username: str | None = None,
    ) -> None:
        """
        Dispatches approval cards to stage participants.
        Sends to the first approver for sequential steps, or to all approvers for parallel steps.
        """
        wf_def = self.workflows_config.workflows[instance.workflow_type]
        step_cfg: WorkflowStepConfig = wf_def.steps[step_index]
        lang = instance.lang

        if not initiator_username:
            initiator_username = await self.mm_client.get_username(instance.initiator_id)

        workflow_name = self.translator.get_localized_dict_value(wf_def.name, lang)
        step_name = self.translator.get_localized_dict_value(step_cfg.name, lang)

        # Load workflow attachments for upload into each approver's DM channel
        att_result = await db.execute(
            select(DocumentAttachment).where(DocumentAttachment.workflow_id == instance.id)
        )
        attachments = list(att_result.scalars().all())

        target_approvers = (
            [step_cfg.approvers[0]]
            if step_cfg.type.value == "sequential"
            else list(step_cfg.approvers)
        )

        for approver_id in target_approvers:
            await self._create_and_send_task(
                db=db,
                instance=instance,
                step_index=step_index,
                step_cfg=step_cfg,
                approver_id=approver_id,
                workflow_name=workflow_name,
                step_name=step_name,
                initiator_username=initiator_username,
                attachments=attachments,
            )

        db.add(
            AuditLog(
                workflow_id=instance.id,
                actor_id="system",
                action="STEP_DISPATCHED",
                details=f"Step '{step_cfg.id}' (index {step_index}, mode={step_cfg.type.value}) dispatched.",
            )
        )

        logger.info(
            self.translator.t_log(
                "step_dispatched",
                step_id=step_cfg.id,
                step_index=step_index,
                workflow_id=instance.id,
                count=len(target_approvers),
            )
        )

    async def _create_and_send_task(
        self,
        *,
        db: AsyncSession,
        instance: WorkflowInstance,
        step_index: int,
        step_cfg: WorkflowStepConfig,
        approver_id: str,
        workflow_name: str,
        step_name: str,
        initiator_username: str,
        attachments: list[DocumentAttachment],
    ) -> ApprovalTask:
        """Creates a task record in the database and posts an interactive card to Mattermost DM."""
        task = ApprovalTask(
            workflow_id=instance.id,
            step_index=step_index,
            step_id=step_cfg.id,
            approver_id=approver_id,
            status=TaskStatus.PENDING,
        )
        db.add(task)
        await db.flush()

        dm_channel_id = await self.mm_client.get_or_create_direct_channel(approver_id)

        # Upload attached files into the approver's Direct Message channel
        mm_file_ids: list[str] = []
        for att in attachments:
            file_path = Path(att.storage_path)
            if file_path.exists():
                file_bytes = file_path.read_bytes()
                mm_file_id = await self.mm_client.upload_file(
                    channel_id=dm_channel_id,
                    filename=att.filename,
                    content=file_bytes,
                    content_type=att.content_type,
                )
                mm_file_ids.append(mm_file_id)

        card_attachment = self.mm_client.build_approval_attachment(
            workflow_id=instance.id,
            task_id=task.id,
            workflow_name=workflow_name,
            step_name=step_name,
            title=instance.title,
            description=instance.description,
            initiator_username=initiator_username,
            document_data=instance.document_data,
            lang=instance.lang,
            include_buttons=True,
        )

        post_id = await self.mm_client.send_approval_card(
            channel_id=dm_channel_id,
            attachment=card_attachment,
            file_ids=mm_file_ids,
        )

        task.dm_channel_id = dm_channel_id
        task.post_id = post_id
        return task

    async def handle_approve_button(
        self,
        db: AsyncSession,
        *,
        task_id: str,
        actor_user_id: str,
        actor_username: str,
    ) -> str | None:
        """
        Handles clicking the 'Approve' button.
        Returns an ephemeral warning message on authorization/state mismatch, or None on success.
        """
        task = await self._load_task_with_workflow(db, task_id)
        if not task:
            return self.translator.t("ephemeral.workflow_not_active")

        workflow = task.workflow
        lang = workflow.lang

        if task.approver_id != actor_user_id:
            return self.translator.t("ephemeral.not_authorized", lang)

        if workflow.status != WorkflowStatus.IN_PROGRESS:
            return self.translator.t("ephemeral.workflow_not_active", lang)

        if task.status != TaskStatus.PENDING:
            return self.translator.t("ephemeral.already_processed", lang, status=task.status.value)

        now = datetime.now(timezone.utc)
        task.status = TaskStatus.APPROVED
        task.decided_at = now

        db.add(
            AuditLog(
                workflow_id=workflow.id,
                task_id=task.id,
                actor_id=actor_user_id,
                actor_username=actor_username,
                action="TASK_APPROVED",
                details=f"Approved step '{task.step_id}' (index {task.step_index}).",
            )
        )

        # Update the original Mattermost post: remove action buttons and display approval status
        wf_def = self.workflows_config.workflows[workflow.workflow_type]
        step_cfg = wf_def.steps[task.step_index]
        initiator_username = await self.mm_client.get_username(workflow.initiator_id)
        timestamp_str = now.strftime("%Y-%m-%d %H:%M")

        status_line = self.translator.t(
            "card.status_approved",
            lang,
            username=actor_username,
            timestamp=timestamp_str,
        )
        if task.post_id:
            updated_card = self.mm_client.build_approval_attachment(
                workflow_id=workflow.id,
                task_id=task.id,
                workflow_name=self.translator.get_localized_dict_value(wf_def.name, lang),
                step_name=self.translator.get_localized_dict_value(step_cfg.name, lang),
                title=workflow.title,
                description=workflow.description,
                initiator_username=initiator_username,
                document_data=workflow.document_data,
                lang=lang,
                include_buttons=False,
                final_status_line=status_line,
                color="#28A745",
            )
            await self.mm_client.update_post_card(task.post_id, updated_card)

        logger.info(
            self.translator.t_log(
                "task_approved",
                task_id=task.id,
                workflow_id=workflow.id,
                actor_id=actor_user_id,
            )
        )

        # Advance to the next approver in a sequential stage or to the next workflow step
        await self._advance_after_approval(db, workflow, step_cfg, initiator_username)
        await db.commit()
        return None

    async def _advance_after_approval(
        self,
        db: AsyncSession,
        workflow: WorkflowInstance,
        step_cfg: WorkflowStepConfig,
        initiator_username: str,
    ) -> None:
        """Evaluates the next FSM transition after a task approval."""
        wf_def = self.workflows_config.workflows[workflow.workflow_type]
        step_index = workflow.current_step_index

        step_tasks_res = await db.execute(
            select(ApprovalTask).where(
                ApprovalTask.workflow_id == workflow.id,
                ApprovalTask.step_index == step_index,
            )
        )
        step_tasks = list(step_tasks_res.scalars().all())

        # If sequential stage has multiple ordered approvers, dispatch the next approver in line
        if step_cfg.type.value == "sequential":
            approved_approvers = {t.approver_id for t in step_tasks if t.status == TaskStatus.APPROVED}
            remaining_approvers = [a for a in step_cfg.approvers if a not in approved_approvers]
            if remaining_approvers:
                att_result = await db.execute(
                    select(DocumentAttachment).where(DocumentAttachment.workflow_id == workflow.id)
                )
                await self._create_and_send_task(
                    db=db,
                    instance=workflow,
                    step_index=step_index,
                    step_cfg=step_cfg,
                    approver_id=remaining_approvers[0],
                    workflow_name=self.translator.get_localized_dict_value(wf_def.name, workflow.lang),
                    step_name=self.translator.get_localized_dict_value(step_cfg.name, workflow.lang),
                    initiator_username=initiator_username,
                    attachments=list(att_result.scalars().all()),
                )
                return

        # For parallel stages, wait until ALL tasks in the current stage are APPROVED
        if not all(t.status == TaskStatus.APPROVED for t in step_tasks):
            return

        # All stage approvers have approved — check if another step follows
        next_step_index = step_index + 1
        if next_step_index < len(wf_def.steps):
            workflow.current_step_index = next_step_index
            await self._dispatch_step(
                db, workflow, step_index=next_step_index, initiator_username=initiator_username
            )
        else:
            # Final stage completed: mark workflow APPROVED and notify the initiator
            workflow.status = WorkflowStatus.APPROVED
            db.add(
                AuditLog(
                    workflow_id=workflow.id,
                    actor_id="system",
                    action="WORKFLOW_APPROVED",
                    details="All approval steps completed successfully.",
                )
            )
            subject = self.translator.t("dm.workflow_approved_subject", workflow.lang)
            body = self.translator.t(
                "dm.workflow_approved_body",
                workflow.lang,
                title=workflow.title,
                workflow_id=workflow.id,
                workflow_name=self.translator.get_localized_dict_value(wf_def.name, workflow.lang),
            )
            await self.mm_client.send_direct_notification(
                user_id=workflow.initiator_id,
                subject=subject,
                body=body,
                color="#28A745",
            )
            logger.info(
                self.translator.t_log(
                    "workflow_completed",
                    workflow_id=workflow.id,
                    status=WorkflowStatus.APPROVED.value,
                )
            )

    async def open_reject_modal(
        self,
        db: AsyncSession,
        *,
        task_id: str,
        actor_user_id: str,
        trigger_id: str,
    ) -> str | None:
        """Validates permissions and opens the rejection reason modal dialog in Mattermost."""
        task = await self._load_task_with_workflow(db, task_id)
        if not task:
            return self.translator.t("ephemeral.workflow_not_active")

        workflow = task.workflow
        lang = workflow.lang

        if task.approver_id != actor_user_id:
            return self.translator.t("ephemeral.not_authorized", lang)

        if workflow.status != WorkflowStatus.IN_PROGRESS:
            return self.translator.t("ephemeral.workflow_not_active", lang)

        if task.status != TaskStatus.PENDING:
            return self.translator.t("ephemeral.already_processed", lang, status=task.status.value)

        await self.mm_client.open_rejection_dialog(
            trigger_id=trigger_id,
            state_data={
                "task_id": task.id,
                "workflow_id": workflow.id,
            },
            lang=lang,
        )
        return None

    async def handle_reject_dialog_submission(
        self,
        db: AsyncSession,
        *,
        task_id: str,
        actor_user_id: str,
        actor_username: str,
        rejection_reason: str,
    ) -> None:
        """
        Records document rejection after dialog submission, updates Mattermost cards,
        cancels sibling parallel tasks, and notifies the initiator.
        """
        task = await self._load_task_with_workflow(db, task_id)
        if not task:
            return

        workflow = task.workflow
        if (
            task.approver_id != actor_user_id
            or workflow.status != WorkflowStatus.IN_PROGRESS
            or task.status != TaskStatus.PENDING
        ):
            return

        lang = workflow.lang
        now = datetime.now(timezone.utc)
        task.status = TaskStatus.REJECTED
        task.comment = rejection_reason
        task.decided_at = now
        workflow.status = WorkflowStatus.REJECTED

        wf_def = self.workflows_config.workflows[workflow.workflow_type]
        step_cfg = wf_def.steps[task.step_index]
        initiator_username = await self.mm_client.get_username(workflow.initiator_id)
        workflow_name = self.translator.get_localized_dict_value(wf_def.name, lang)
        step_name = self.translator.get_localized_dict_value(step_cfg.name, lang)
        timestamp_str = now.strftime("%Y-%m-%d %H:%M")

        # Update the rejecting approver's card with red status and rejection reason
        reject_status_line = (
            self.translator.t(
                "card.status_rejected",
                lang,
                username=actor_username,
                timestamp=timestamp_str,
            )
            + "\n"
            + self.translator.t("card.rejection_reason_label", lang, reason=rejection_reason)
        )
        if task.post_id:
            rejected_card = self.mm_client.build_approval_attachment(
                workflow_id=workflow.id,
                task_id=task.id,
                workflow_name=workflow_name,
                step_name=step_name,
                title=workflow.title,
                description=workflow.description,
                initiator_username=initiator_username,
                document_data=workflow.document_data,
                lang=lang,
                include_buttons=False,
                final_status_line=reject_status_line,
                color="#DC3545",
            )
            await self.mm_client.update_post_card(task.post_id, rejected_card)

        # Cancel any remaining open parallel tasks and remove their buttons
        other_pending_res = await db.execute(
            select(ApprovalTask).where(
                ApprovalTask.workflow_id == workflow.id,
                ApprovalTask.id != task.id,
                ApprovalTask.status == TaskStatus.PENDING,
            )
        )
        for other_task in other_pending_res.scalars().all():
            other_task.status = TaskStatus.CANCELLED
            other_task.decided_at = now
            if other_task.post_id:
                cancelled_card = self.mm_client.build_approval_attachment(
                    workflow_id=workflow.id,
                    task_id=other_task.id,
                    workflow_name=workflow_name,
                    step_name=step_name,
                    title=workflow.title,
                    description=workflow.description,
                    initiator_username=initiator_username,
                    document_data=workflow.document_data,
                    lang=lang,
                    include_buttons=False,
                    final_status_line=self.translator.t("card.status_cancelled", lang),
                    color="#6C757D",
                )
                await self.mm_client.update_post_card(other_task.post_id, cancelled_card)

        db.add(
            AuditLog(
                workflow_id=workflow.id,
                task_id=task.id,
                actor_id=actor_user_id,
                actor_username=actor_username,
                action="TASK_REJECTED",
                details=f"Rejected at step '{task.step_id}'. Reason: {rejection_reason}",
            )
        )
        db.add(
            AuditLog(
                workflow_id=workflow.id,
                actor_id="system",
                action="WORKFLOW_REJECTED",
                details="Workflow returned to initiator due to rejection.",
            )
        )

        # Notify the initiator via Direct Message with the rejection reason
        subject = self.translator.t("dm.workflow_rejected_subject", lang)
        body = self.translator.t(
            "dm.workflow_rejected_body",
            lang,
            title=workflow.title,
            workflow_id=workflow.id,
            workflow_name=workflow_name,
            step_name=step_name,
            username=actor_username,
            reason=rejection_reason,
        )
        await self.mm_client.send_direct_notification(
            user_id=workflow.initiator_id,
            subject=subject,
            body=body,
            color="#DC3545",
        )

        await db.commit()

        logger.info(
            self.translator.t_log(
                "task_rejected",
                task_id=task.id,
                workflow_id=workflow.id,
                actor_id=actor_user_id,
                reason=rejection_reason,
            )
        )

    @staticmethod
    async def _load_task_with_workflow(db: AsyncSession, task_id: str) -> ApprovalTask | None:
        """Loads an approval task together with its parent workflow instance."""
        stmt = (
            select(ApprovalTask)
            .where(ApprovalTask.id == task_id)
            .options(selectinload(ApprovalTask.workflow))
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
