# Author: Oleh Riabtsev
# File: tests/test_workflow_integration.py
# Created: 2026-11-23
# Version: 1.2.1

"""
End-to-end integration tests for the Mattermost Document Approval Workflow Engine.
Covers:
1. Single-step sequential approval with file attachment, card updates, and disk cleanup.
2. Multi-approver ordered sequential stage progression.
3. Multi-step workflow combining sequential and parallel synchronization barriers,
   ensuring attachments remain available across all stages until final completion.
4. Rejection workflow with Interactive Dialog validation, sibling task cancellation,
   initiator DM notification, and temporary file cleanup.
5. Security token verification, approver authorization checks, and button idempotency.
6. REST API payload validation, 404 error handling, and orphaned file cleanup on failure.
7. Mattermost Bot WebSocket DM command ('хочу начать согласование' / 'start') generating
   a signed Studio session token and authenticating the user.
8. Visual Workflow Studio template ownership enforcement (only creator can edit/delete).
9. Conditional alternative routing on rejection (on_reject='goto_step', is_alternative=True)
   with escalation banner delivery and subsequent pipeline progression.
"""

import json
from pathlib import Path
import re
import httpx

from app.auth_tokens import create_studio_session_token
from app.bot_listener import BotWebSocketListener
from app.config import get_settings
from app.main import app
from tests.conftest import FakeMattermostServer


def _build_button_payload(
    *,
    user_id: str,
    user_name: str,
    channel_id: str,
    post_id: str,
    action: str,
    task_id: str,
    workflow_id: str,
    trigger_id: str = "trigger_xyz_123",
) -> dict:
    """Helper constructing a Mattermost Interactive Message Button callback payload."""
    return {
        "user_id": user_id,
        "user_name": user_name,
        "channel_id": channel_id,
        "post_id": post_id,
        "trigger_id": trigger_id,
        "type": "button",
        "context": {
            "action": action,
            "task_id": task_id,
            "workflow_id": workflow_id,
        },
    }


async def test_single_step_sequential_approval_with_attachment(
    api_client: httpx.AsyncClient,
    fake_mm_server: FakeMattermostServer,
    tmp_path: Path,
) -> None:
    """
    Verifies starting a workflow with a file attachment, approving it,
    notifying the initiator, and removing the temporary file from uploads.
    """
    upload_dir = tmp_path / "uploads"

    start_resp = await api_client.post(
        "/api/v1/workflows/start",
        data={
            "workflow_type": "single_step_seq",
            "title": "Travel Expense #101",
            "description": "Train ticket to Hannover conference",
            "initiator_id": "user_initiator",
            "lang": "en",
            "document_data": json.dumps({"amount": "142.50 EUR", "cost_center": "CC-2026"}),
        },
        files=[("files", ("receipt.pdf", b"%PDF-1.4 sample content", "application/pdf"))],
    )
    assert start_resp.status_code == 201
    start_data = start_resp.json()
    workflow_id = start_data["workflow_id"]
    assert start_data["status"] == "IN_PROGRESS"
    assert start_data["current_step_index"] == 0

    staged_files = list(upload_dir.glob("*receipt.pdf"))
    assert len(staged_files) == 1
    assert staged_files[0].is_file()

    assert len(fake_mm_server.uploaded_files) == 1
    assert fake_mm_server.uploaded_files[0]["channel_id"] == "dm_user_mgr_1"
    assert len(fake_mm_server.posts) == 1

    initial_post = fake_mm_server.posts["post_1"]
    assert initial_post["channel_id"] == "dm_user_mgr_1"
    assert initial_post["file_ids"] == ["mm_file_1"]
    attachment = initial_post["props"]["attachments"][0]
    assert len(attachment["actions"]) == 2
    task_id = attachment["actions"][0]["integration"]["context"]["task_id"]

    action_resp = await api_client.post(
        "/api/v1/mattermost/actions?token=test_secret_token",
        json=_build_button_payload(
            user_id="user_mgr_1",
            user_name="mgr_one",
            channel_id="dm_user_mgr_1",
            post_id="post_1",
            action="approve",
            task_id=task_id,
            workflow_id=workflow_id,
        ),
    )
    assert action_resp.status_code == 200
    assert action_resp.json() == {}

    assert list(upload_dir.iterdir()) == []

    assert len(fake_mm_server.updated_posts) == 1
    updated_attachment = fake_mm_server.updated_posts[0]["props"]["attachments"][0]
    assert "actions" not in updated_attachment
    assert "@mgr_one" in updated_attachment["text"]
    assert updated_attachment["color"] == "#28A745"

    assert len(fake_mm_server.posts) == 2
    completion_dm = fake_mm_server.posts["post_2"]
    assert completion_dm["channel_id"] == "dm_user_initiator"
    assert "Completed" in completion_dm["props"]["attachments"][0]["title"]

    status_resp = await api_client.get(f"/api/v1/workflows/{workflow_id}")
    assert status_resp.status_code == 200
    details = status_resp.json()
    assert details["status"] == "APPROVED"
    assert len(details["tasks"]) == 1
    assert details["tasks"][0]["status"] == "APPROVED"
    assert len(details["attachments"]) == 1
    assert details["attachments"][0]["filename"] == "receipt.pdf"
    assert [log["action"] for log in details["audit_logs"]] == [
        "WORKFLOW_STARTED",
        "STEP_DISPATCHED",
        "TASK_APPROVED",
        "WORKFLOW_APPROVED",
    ]


async def test_multi_approver_sequential_stage_order(
    api_client: httpx.AsyncClient,
    fake_mm_server: FakeMattermostServer,
) -> None:
    """Verifies that a sequential step with multiple approvers dispatches tasks strictly one by one."""
    start_resp = await api_client.post(
        "/api/v1/workflows/start",
        data={
            "workflow_type": "multi_approver_seq",
            "title": "Ordered Sequence Document",
            "initiator_id": "user_initiator",
            "lang": "en",
        },
    )
    assert start_resp.status_code == 201
    workflow_id = start_resp.json()["workflow_id"]

    assert len(fake_mm_server.posts) == 1
    assert fake_mm_server.posts["post_1"]["channel_id"] == "dm_user_seq_1"
    task_1_id = fake_mm_server.posts["post_1"]["props"]["attachments"][0]["actions"][0]["integration"][
        "context"
    ]["task_id"]

    resp_1 = await api_client.post(
        "/api/v1/mattermost/actions?token=test_secret_token",
        json=_build_button_payload(
            user_id="user_seq_1",
            user_name="seq_one",
            channel_id="dm_user_seq_1",
            post_id="post_1",
            action="approve",
            task_id=task_1_id,
            workflow_id=workflow_id,
        ),
    )
    assert resp_1.status_code == 200
    assert len(fake_mm_server.posts) == 2
    assert fake_mm_server.posts["post_2"]["channel_id"] == "dm_user_seq_2"

    mid_details = (await api_client.get(f"/api/v1/workflows/{workflow_id}")).json()
    assert mid_details["status"] == "IN_PROGRESS"

    task_2_id = fake_mm_server.posts["post_2"]["props"]["attachments"][0]["actions"][0]["integration"][
        "context"
    ]["task_id"]

    resp_2 = await api_client.post(
        "/api/v1/mattermost/actions?token=test_secret_token",
        json=_build_button_payload(
            user_id="user_seq_2",
            user_name="seq_two",
            channel_id="dm_user_seq_2",
            post_id="post_2",
            action="approve",
            task_id=task_2_id,
            workflow_id=workflow_id,
        ),
    )
    assert resp_2.status_code == 200

    final_details = (await api_client.get(f"/api/v1/workflows/{workflow_id}")).json()
    assert final_details["status"] == "APPROVED"
    assert len(final_details["tasks"]) == 2


async def test_multistep_sequential_and_parallel_synchronization(
    api_client: httpx.AsyncClient,
    fake_mm_server: FakeMattermostServer,
    tmp_path: Path,
) -> None:
    """
    Verifies a 3-stage workflow with a file attachment:
    Step 0 (sequential: user_dept) -> Step 1 (parallel: user_legal + user_finance) -> Step 2 (sequential: user_ceo).
    Ensures Step 2 is dispatched only after BOTH parallel approvers approve, and attachment cleanup
    occurs only after final CEO approval.
    """
    upload_dir = tmp_path / "uploads"

    start_resp = await api_client.post(
        "/api/v1/workflows/start",
        data={
            "workflow_type": "multistep_mixed",
            "title": "Enterprise Cloud Agreement",
            "initiator_id": "user_initiator",
            "lang": "de",
        },
        files=[("files", ("enterprise_contract.pdf", b"%PDF-1.4 contract", "application/pdf"))],
    )
    assert start_resp.status_code == 201
    workflow_id = start_resp.json()["workflow_id"]
    assert len(list(upload_dir.glob("*enterprise_contract.pdf"))) == 1

    step0_post = fake_mm_server.posts["post_1"]
    assert step0_post["channel_id"] == "dm_user_dept"
    step0_task_id = step0_post["props"]["attachments"][0]["actions"][0]["integration"]["context"]["task_id"]

    await api_client.post(
        "/api/v1/mattermost/actions?token=test_secret_token",
        json=_build_button_payload(
            user_id="user_dept",
            user_name="dept_head",
            channel_id="dm_user_dept",
            post_id="post_1",
            action="approve",
            task_id=step0_task_id,
            workflow_id=workflow_id,
        ),
    )

    assert len(list(upload_dir.glob("*enterprise_contract.pdf"))) == 1

    assert len(fake_mm_server.posts) == 3
    channels_step1 = {
        fake_mm_server.posts["post_2"]["channel_id"],
        fake_mm_server.posts["post_3"]["channel_id"],
    }
    assert channels_step1 == {"dm_user_legal", "dm_user_finance"}

    legal_task_id = fake_mm_server.posts["post_2"]["props"]["attachments"][0]["actions"][0]["integration"][
        "context"
    ]["task_id"]
    finance_task_id = fake_mm_server.posts["post_3"]["props"]["attachments"][0]["actions"][0]["integration"][
        "context"
    ]["task_id"]

    await api_client.post(
        "/api/v1/mattermost/actions?token=test_secret_token",
        json=_build_button_payload(
            user_id="user_legal",
            user_name="legal_reviewer",
            channel_id="dm_user_legal",
            post_id="post_2",
            action="approve",
            task_id=legal_task_id,
            workflow_id=workflow_id,
        ),
    )
    mid_state = (await api_client.get(f"/api/v1/workflows/{workflow_id}")).json()
    assert mid_state["status"] == "IN_PROGRESS"
    assert mid_state["current_step_index"] == 1
    assert len(fake_mm_server.posts) == 3
    assert len(list(upload_dir.glob("*enterprise_contract.pdf"))) == 1

    await api_client.post(
        "/api/v1/mattermost/actions?token=test_secret_token",
        json=_build_button_payload(
            user_id="user_finance",
            user_name="finance_reviewer",
            channel_id="dm_user_finance",
            post_id="post_3",
            action="approve",
            task_id=finance_task_id,
            workflow_id=workflow_id,
        ),
    )
    assert len(fake_mm_server.posts) == 4
    ceo_post = fake_mm_server.posts["post_4"]
    assert ceo_post["channel_id"] == "dm_user_ceo"
    assert len(fake_mm_server.uploaded_files) == 4
    assert len(list(upload_dir.glob("*enterprise_contract.pdf"))) == 1

    ceo_task_id = ceo_post["props"]["attachments"][0]["actions"][0]["integration"]["context"]["task_id"]

    await api_client.post(
        "/api/v1/mattermost/actions?token=test_secret_token",
        json=_build_button_payload(
            user_id="user_ceo",
            user_name="ceo_user",
            channel_id="dm_user_ceo",
            post_id="post_4",
            action="approve",
            task_id=ceo_task_id,
            workflow_id=workflow_id,
        ),
    )

    assert list(upload_dir.iterdir()) == []

    final_state = (await api_client.get(f"/api/v1/workflows/{workflow_id}")).json()
    assert final_state["status"] == "APPROVED"
    assert final_state["current_step_index"] == 2
    assert len(final_state["tasks"]) == 4


async def test_rejection_dialog_cancels_parallel_sibling_and_notifies_initiator(
    api_client: httpx.AsyncClient,
    fake_mm_server: FakeMattermostServer,
    tmp_path: Path,
) -> None:
    """
    Verifies the standard rejection flow during a parallel stage:
    1. Clicking Reject opens an Interactive Dialog.
    2. Submitting an empty reason returns a field-level validation error.
    3. Submitting a valid reason marks the task REJECTED, cancels the parallel peer's task,
       notifies the initiator, and cleans up temporary attachment files.
    """
    upload_dir = tmp_path / "uploads"

    start_resp = await api_client.post(
        "/api/v1/workflows/start",
        data={
            "workflow_type": "multistep_mixed",
            "title": "Vendor SLA Amendment",
            "initiator_id": "user_initiator",
            "lang": "en",
        },
        files=[("files", ("sla_amendment.pdf", b"%PDF-1.4 sla", "application/pdf"))],
    )
    workflow_id = start_resp.json()["workflow_id"]
    assert len(list(upload_dir.glob("*sla_amendment.pdf"))) == 1

    step0_task_id = fake_mm_server.posts["post_1"]["props"]["attachments"][0]["actions"][0]["integration"][
        "context"
    ]["task_id"]
    await api_client.post(
        "/api/v1/mattermost/actions?token=test_secret_token",
        json=_build_button_payload(
            user_id="user_dept",
            user_name="dept_head",
            channel_id="dm_user_dept",
            post_id="post_1",
            action="approve",
            task_id=step0_task_id,
            workflow_id=workflow_id,
        ),
    )

    legal_task_id = fake_mm_server.posts["post_2"]["props"]["attachments"][0]["actions"][0]["integration"][
        "context"
    ]["task_id"]

    reject_click_resp = await api_client.post(
        "/api/v1/mattermost/actions?token=test_secret_token",
        json=_build_button_payload(
            user_id="user_legal",
            user_name="legal_reviewer",
            channel_id="dm_user_legal",
            post_id="post_2",
            action="reject",
            task_id=legal_task_id,
            workflow_id=workflow_id,
            trigger_id="trig_reject_999",
        ),
    )
    assert reject_click_resp.status_code == 200
    assert len(fake_mm_server.opened_dialogs) == 1
    opened_dialog = fake_mm_server.opened_dialogs[0]
    assert opened_dialog["trigger_id"] == "trig_reject_999"
    dialog_state = opened_dialog["dialog"]["state"]

    empty_submit_resp = await api_client.post(
        "/api/v1/mattermost/dialogs/reject?token=test_secret_token",
        json={
            "type": "dialog_submission",
            "callback_id": "reject_document_dialog",
            "state": dialog_state,
            "user_id": "user_legal",
            "channel_id": "dm_user_legal",
            "submission": {"rejection_reason": "   "},
            "cancelled": False,
        },
    )
    assert empty_submit_resp.status_code == 200
    assert "rejection_reason" in empty_submit_resp.json()["errors"]
    assert len(list(upload_dir.glob("*sla_amendment.pdf"))) == 1

    rejection_text = "Liability cap clause violates corporate policy."
    valid_submit_resp = await api_client.post(
        "/api/v1/mattermost/dialogs/reject?token=test_secret_token",
        json={
            "type": "dialog_submission",
            "callback_id": "reject_document_dialog",
            "state": dialog_state,
            "user_id": "user_legal",
            "channel_id": "dm_user_legal",
            "submission": {"rejection_reason": rejection_text},
            "cancelled": False,
        },
    )
    assert valid_submit_resp.status_code == 200
    assert valid_submit_resp.json() == {}

    assert list(upload_dir.iterdir()) == []

    assert "actions" not in fake_mm_server.posts["post_2"]["props"]["attachments"][0]
    assert rejection_text in fake_mm_server.posts["post_2"]["props"]["attachments"][0]["text"]
    assert "actions" not in fake_mm_server.posts["post_3"]["props"]["attachments"][0]
    assert "Cancelled" in fake_mm_server.posts["post_3"]["props"]["attachments"][0]["text"]

    initiator_dm = fake_mm_server.posts["post_4"]
    assert initiator_dm["channel_id"] == "dm_user_initiator"
    assert rejection_text in initiator_dm["props"]["attachments"][0]["text"]

    final_details = (await api_client.get(f"/api/v1/workflows/{workflow_id}")).json()
    assert final_details["status"] == "REJECTED"
    assert len(final_details["attachments"]) == 1
    assert final_details["attachments"][0]["filename"] == "sla_amendment.pdf"
    tasks_by_approver = {t["approver_id"]: t for t in final_details["tasks"]}
    assert tasks_by_approver["user_legal"]["status"] == "REJECTED"
    assert tasks_by_approver["user_legal"]["comment"] == rejection_text
    assert tasks_by_approver["user_finance"]["status"] == "CANCELLED"


async def test_security_authorization_and_idempotency(
    api_client: httpx.AsyncClient,
    fake_mm_server: FakeMattermostServer,
) -> None:
    """Verifies webhook secret validation, wrong-user protection, and duplicate button click idempotency."""
    start_resp = await api_client.post(
        "/api/v1/workflows/start",
        data={
            "workflow_type": "single_step_seq",
            "title": "Security Check Doc",
            "initiator_id": "user_initiator",
            "lang": "en",
        },
    )
    workflow_id = start_resp.json()["workflow_id"]
    task_id = fake_mm_server.posts["post_1"]["props"]["attachments"][0]["actions"][0]["integration"][
        "context"
    ]["task_id"]

    bad_token_resp = await api_client.post(
        "/api/v1/mattermost/actions?token=wrong_secret",
        json=_build_button_payload(
            user_id="user_mgr_1",
            user_name="mgr_one",
            channel_id="dm_user_mgr_1",
            post_id="post_1",
            action="approve",
            task_id=task_id,
            workflow_id=workflow_id,
        ),
    )
    assert bad_token_resp.status_code == 401

    unauth_resp = await api_client.post(
        "/api/v1/mattermost/actions?token=test_secret_token",
        json=_build_button_payload(
            user_id="user_intruder",
            user_name="intruder",
            channel_id="dm_user_mgr_1",
            post_id="post_1",
            action="approve",
            task_id=task_id,
            workflow_id=workflow_id,
        ),
    )
    assert unauth_resp.status_code == 200
    assert "not authorized" in unauth_resp.json()["ephemeral_text"].lower()

    first_approve = await api_client.post(
        "/api/v1/mattermost/actions?token=test_secret_token",
        json=_build_button_payload(
            user_id="user_mgr_1",
            user_name="mgr_one",
            channel_id="dm_user_mgr_1",
            post_id="post_1",
            action="approve",
            task_id=task_id,
            workflow_id=workflow_id,
        ),
    )
    assert first_approve.status_code == 200
    assert first_approve.json() == {}

    second_approve = await api_client.post(
        "/api/v1/mattermost/actions?token=test_secret_token",
        json=_build_button_payload(
            user_id="user_mgr_1",
            user_name="mgr_one",
            channel_id="dm_user_mgr_1",
            post_id="post_1",
            action="approve",
            task_id=task_id,
            workflow_id=workflow_id,
        ),
    )
    assert second_approve.status_code == 200
    assert "no longer active" in second_approve.json()["ephemeral_text"].lower()
    assert len(fake_mm_server.posts) == 2


async def test_api_validation_and_not_found_errors(
    api_client: httpx.AsyncClient,
    tmp_path: Path,
) -> None:
    """
    Verifies HTTP error codes for invalid workflow types, unsupported languages,
    unknown IDs, and ensures uploaded files are cleaned up if workflow startup fails.
    """
    upload_dir = tmp_path / "uploads"

    bad_lang_resp = await api_client.post(
        "/api/v1/workflows/start",
        data={
            "workflow_type": "single_step_seq",
            "title": "Test",
            "initiator_id": "user_initiator",
            "lang": "fr",
        },
    )
    assert bad_lang_resp.status_code == 400

    bad_json_resp = await api_client.post(
        "/api/v1/workflows/start",
        data={
            "workflow_type": "single_step_seq",
            "title": "Test",
            "initiator_id": "user_initiator",
            "document_data": "{not-valid-json}",
        },
    )
    assert bad_json_resp.status_code == 400

    unknown_wf_resp = await api_client.post(
        "/api/v1/workflows/start",
        data={
            "workflow_type": "non_existent_route",
            "title": "Test",
            "initiator_id": "user_initiator",
        },
        files=[("files", ("orphaned.pdf", b"%PDF-1.4 orphaned", "application/pdf"))],
    )
    assert unknown_wf_resp.status_code == 404
    assert list(upload_dir.iterdir()) == []

    missing_id_resp = await api_client.get("/api/v1/workflows/00000000-0000-0000-0000-000000000000")
    assert missing_id_resp.status_code == 404


async def test_bot_dm_command_generates_valid_studio_session(
    api_client: httpx.AsyncClient,
    fake_mm_server: FakeMattermostServer,
) -> None:
    """
    Verifies that sending a trigger phrase (e.g. 'хочу начать согласование') as a Direct Message
    to the bot sends back a signed Studio magic link that authenticates the sender.
    """
    settings = get_settings()
    listener = BotWebSocketListener(
        settings=settings,
        mm_client=app.state.mm_client,
        translator=app.state.translator,
    )

    # 1. Messages from the bot itself or non-DM channels must be ignored
    bot_self_event = {
        "event": "posted",
        "data": {
            "channel_type": "D",
            "post": json.dumps({"user_id": fake_mm_server.bot_user_id, "message": "start"}),
        },
    }
    await listener._handle_event(json.dumps(bot_self_event), bot_id=fake_mm_server.bot_user_id)
    assert len(fake_mm_server.posts) == 0

    public_channel_event = {
        "event": "posted",
        "data": {
            "channel_type": "O",
            "post": json.dumps({"user_id": "user_alice", "message": "start"}),
        },
    }
    await listener._handle_event(json.dumps(public_channel_event), bot_id=fake_mm_server.bot_user_id)
    assert len(fake_mm_server.posts) == 0

    # 2. Direct Message with Russian trigger phrase from user_alice
    user_dm_event = {
        "event": "posted",
        "data": {
            "channel_type": "D",
            "post": json.dumps({"user_id": "user_alice", "message": "Хочу начать согласование"}),
        },
    }
    await listener._handle_event(json.dumps(user_dm_event), bot_id=fake_mm_server.bot_user_id)

    assert len(fake_mm_server.posts) == 1
    dm_post = fake_mm_server.posts["post_1"]
    assert dm_post["channel_id"] == "dm_user_alice"
    dm_text = dm_post["props"]["attachments"][0]["text"]

    match = re.search(r"http://studio\.test/studio\?token=([A-Za-z0-9_\-\.]+)", dm_text)
    assert match is not None
    studio_token = match.group(1)

    # 3. Verify Studio HTML page and session endpoint accept the generated token
    page_resp = await api_client.get(f"/studio?token={studio_token}")
    assert page_resp.status_code == 200
    assert "Visual Document Approval Studio" in page_resp.text

    session_resp = await api_client.get(
        "/api/v1/studio/session",
        headers={"X-Studio-Token": studio_token},
    )
    assert session_resp.status_code == 200
    assert session_resp.json() == {
        "user_id": "user_alice",
        "username": "username_user_alice",
    }

    # 4. Verify invalid tokens are rejected with HTTP 401
    bad_session_resp = await api_client.get(
        "/api/v1/studio/session",
        headers={"X-Studio-Token": "tampered.token.value"},
    )
    assert bad_session_resp.status_code == 401


async def test_template_ownership_permissions(api_client: httpx.AsyncClient) -> None:
    """
    Verifies that only the creator (owner_id) of a workflow template can modify or delete its stages,
    while other users can inspect it with can_edit=False.
    """
    settings = get_settings()
    alice_token = create_studio_session_token(settings, user_id="user_alice", username="alice")
    bob_token = create_studio_session_token(settings, user_id="user_bob", username="bob")

    create_payload = {
        "name": {"en": "Alice CapEx Route", "de": "Alice Investitionsroute"},
        "description": {"en": "Capital expenditure review"},
        "default_lang": "en",
        "steps": [
            {
                "id": "step_1",
                "name": {"en": "Finance Check", "de": "Finanzprüfung"},
                "type": "sequential",
                "approvers": ["user_bob"],
                "is_alternative": False,
                "on_reject": "return_to_initiator",
                "on_reject_step_id": None,
            }
        ],
        "default_fields": [
            {"name": "Budget Code", "type": "text", "default_value": "CAPEX-01", "required": True}
        ],
    }

    # 1. Alice creates the template -> can_edit is True
    create_resp = await api_client.post(
        "/api/v1/templates",
        headers={"X-Studio-Token": alice_token},
        json=create_payload,
    )
    assert create_resp.status_code == 201
    created_tpl = create_resp.json()
    template_id = created_tpl["id"]
    assert created_tpl["owner_id"] == "user_alice"
    assert created_tpl["can_edit"] is True

    # 2. Bob lists templates -> sees Alice's template with can_edit=False
    bob_list_resp = await api_client.get(
        "/api/v1/templates",
        headers={"X-Studio-Token": bob_token},
    )
    assert bob_list_resp.status_code == 200
    bob_view = next(item for item in bob_list_resp.json() if item["id"] == template_id)
    assert bob_view["can_edit"] is False

    # 3. Bob attempts to modify or delete Alice's template -> HTTP 403 Forbidden
    bob_update_resp = await api_client.put(
        f"/api/v1/templates/{template_id}",
        headers={"X-Studio-Token": bob_token},
        json=create_payload,
    )
    assert bob_update_resp.status_code == 403

    bob_delete_resp = await api_client.delete(
        f"/api/v1/templates/{template_id}",
        headers={"X-Studio-Token": bob_token},
    )
    assert bob_delete_resp.status_code == 403

    # 4. Alice updates her own template -> HTTP 200 OK
    updated_payload = {
        **create_payload,
        "name": {"en": "Alice CapEx Route v2", "de": "Alice Investitionsroute v2"},
    }
    alice_update_resp = await api_client.put(
        f"/api/v1/templates/{template_id}",
        headers={"X-Studio-Token": alice_token},
        json=updated_payload,
    )
    assert alice_update_resp.status_code == 200
    assert alice_update_resp.json()["name"]["en"] == "Alice CapEx Route v2"

    # 5. Alice deletes her own template -> HTTP 204 No Content
    alice_delete_resp = await api_client.delete(
        f"/api/v1/templates/{template_id}",
        headers={"X-Studio-Token": alice_token},
    )
    assert alice_delete_resp.status_code == 204


async def test_alternative_routing_on_rejection_and_escalation_banner(
    api_client: httpx.AsyncClient,
    fake_mm_server: FakeMattermostServer,
    tmp_path: Path,
) -> None:
    """
    Verifies conditional rejection branching:
    - Step 0 ('initial_review') routes rejection to Step 1 ('escalation_board', is_alternative=True).
    - When Step 0 rejects, the workflow does NOT terminate; instead, it routes to Step 1 with
      an escalation banner containing the rejection reason.
    - After Step 1 approves, the workflow advances to Step 2 ('final_accounting') and completes
      as APPROVED, cleaning up the attachment file only at the very end.
    """
    settings = get_settings()
    alice_token = create_studio_session_token(settings, user_id="user_alice", username="alice")
    upload_dir = tmp_path / "uploads"

    # 1. Create a 3-stage template with an alternative rejection branch
    tpl_resp = await api_client.post(
        "/api/v1/templates",
        headers={"X-Studio-Token": alice_token},
        json={
            "name": {"en": "Escalating Purchase Route", "de": "Eskalationsroute Einkauf"},
            "description": {"en": "Routes Stage 1 rejection to Director Escalation"},
            "default_lang": "en",
            "steps": [
                {
                    "id": "initial_review",
                    "name": {"en": "Team Lead Check", "de": "Teamleiter"},
                    "type": "sequential",
                    "approvers": ["user_lead"],
                    "is_alternative": False,
                    "on_reject": "goto_step",
                    "on_reject_step_id": "escalation_board",
                },
                {
                    "id": "escalation_board",
                    "name": {"en": "Director Escalation", "de": "Direktor-Eskalation"},
                    "type": "sequential",
                    "approvers": ["user_director"],
                    "is_alternative": True,
                    "on_reject": "return_to_initiator",
                    "on_reject_step_id": None,
                },
                {
                    "id": "final_accounting",
                    "name": {"en": "Final Accounting", "de": "Buchhaltung"},
                    "type": "sequential",
                    "approvers": ["user_accountant"],
                    "is_alternative": False,
                    "on_reject": "return_to_initiator",
                    "on_reject_step_id": None,
                },
            ],
            "default_fields": [],
        },
    )
    assert tpl_resp.status_code == 201
    template_slug = tpl_resp.json()["slug"]

    # 2. Launch workflow using the newly created visual template slug and custom typed fields
    custom_fields_payload = {
        "_custom_fields": [
            {"name": "Amount", "type": "number", "value": "8900"},
            {"name": "Urgent", "type": "boolean", "value": "Yes"},
        ]
    }
    start_resp = await api_client.post(
        "/api/v1/workflows/start",
        data={
            "workflow_type": template_slug,
            "title": "GPU Workstation Purchase",
            "initiator_id": "user_alice",
            "lang": "en",
            "document_data": json.dumps(custom_fields_payload),
        },
        files=[("files", ("quote_gpu.pdf", b"%PDF-1.4 quote", "application/pdf"))],
    )
    assert start_resp.status_code == 201
    workflow_id = start_resp.json()["workflow_id"]
    assert len(list(upload_dir.glob("*quote_gpu.pdf"))) == 1

    # Verify Step 0 card was sent to user_lead with custom fields rendered
    step0_post = fake_mm_server.posts["post_1"]
    assert step0_post["channel_id"] == "dm_user_lead"
    step0_attachment = step0_post["props"]["attachments"][0]
    assert any("Amount" in f["value"] and "8900" in f["value"] for f in step0_attachment["fields"])
    step0_task_id = step0_attachment["actions"][0]["integration"]["context"]["task_id"]

    # 3. user_lead clicks Reject -> opens dialog -> submits rejection reason
    await api_client.post(
        "/api/v1/mattermost/actions?token=test_secret_token",
        json=_build_button_payload(
            user_id="user_lead",
            user_name="lead_user",
            channel_id="dm_user_lead",
            post_id="post_1",
            action="reject",
            task_id=step0_task_id,
            workflow_id=workflow_id,
            trigger_id="trig_alt_1",
        ),
    )
    dialog_state = fake_mm_server.opened_dialogs[0]["dialog"]["state"]

    rejection_reason = "Exceeds department limit; requires Director sign-off."
    await api_client.post(
        "/api/v1/mattermost/dialogs/reject?token=test_secret_token",
        json={
            "type": "dialog_submission",
            "callback_id": "reject_document_dialog",
            "state": dialog_state,
            "user_id": "user_lead",
            "channel_id": "dm_user_lead",
            "submission": {"rejection_reason": rejection_reason},
            "cancelled": False,
        },
    )

    # Workflow must remain IN_PROGRESS at current_step_index == 1 (escalation_board)
    mid_state = (await api_client.get(f"/api/v1/workflows/{workflow_id}")).json()
    assert mid_state["status"] == "IN_PROGRESS"
    assert mid_state["current_step_index"] == 1
    assert len(list(upload_dir.glob("*quote_gpu.pdf"))) == 1

    # Verify post_1 was marked Rerouted (#F59E0B) and post_2 was dispatched to user_director with escalation banner
    assert fake_mm_server.posts["post_1"]["props"]["attachments"][0]["color"] == "#F59E0B"
    escalation_post = fake_mm_server.posts["post_2"]
    assert escalation_post["channel_id"] == "dm_user_director"
    esc_attachment = escalation_post["props"]["attachments"][0]
    assert rejection_reason in esc_attachment["text"]
    assert "@username_user_lead" in esc_attachment["text"]
    step1_task_id = esc_attachment["actions"][0]["integration"]["context"]["task_id"]

    # 4. Director approves Step 1 -> advances to Step 2 ('final_accounting')
    await api_client.post(
        "/api/v1/mattermost/actions?token=test_secret_token",
        json=_build_button_payload(
            user_id="user_director",
            user_name="director_user",
            channel_id="dm_user_director",
            post_id="post_2",
            action="approve",
            task_id=step1_task_id,
            workflow_id=workflow_id,
        ),
    )
    assert len(fake_mm_server.posts) == 3
    step2_post = fake_mm_server.posts["post_3"]
    assert step2_post["channel_id"] == "dm_user_accountant"
    step2_task_id = step2_post["props"]["attachments"][0]["actions"][0]["integration"]["context"]["task_id"]

    # 5. Accountant approves Step 2 -> workflow finishes as APPROVED and file is cleaned up
    await api_client.post(
        "/api/v1/mattermost/actions?token=test_secret_token",
        json=_build_button_payload(
            user_id="user_accountant",
            user_name="accountant_user",
            channel_id="dm_user_accountant",
            post_id="post_3",
            action="approve",
            task_id=step2_task_id,
            workflow_id=workflow_id,
        ),
    )

    assert list(upload_dir.iterdir()) == []
    final_state = (await api_client.get(f"/api/v1/workflows/{workflow_id}")).json()
    assert final_state["status"] == "APPROVED"
    assert "STEP_REROUTED_ON_REJECT" in [log["action"] for log in final_state["audit_logs"]]
