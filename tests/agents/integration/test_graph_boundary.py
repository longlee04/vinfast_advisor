"""[A0-3] Cưỡng chế biên điều phối (mục 6.5/6.5b): `nodes/`/`graph.py`/`routing.py`/`chain.py`
chỉ nối, không nghiệp vụ; `AgentServices` chỉ chứa nhóm advisory (mục 6.3).
"""

from __future__ import annotations

import ast
from pathlib import Path

from src.agents.services.registry import AgentServices

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
AGENTS_ROOT = REPOSITORY_ROOT / "src" / "agents"
NODES_DIR = AGENTS_ROOT / "nodes"

FORBIDDEN_ORCHESTRATION_PREFIXES = (
    "sqlalchemy",
    "src.agents.adapters",
    "src.agents.domain",
)

MAX_NODE_STATEMENTS = 15


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def _node_files() -> list[Path]:
    return sorted(p for p in NODES_DIR.glob("*.py") if p.name != "__init__.py")


def test_nodes_do_not_import_sqlalchemy_adapters_or_domain() -> None:
    violations = [
        f"{path.relative_to(REPOSITORY_ROOT)} imports {module}"
        for path in _node_files()
        for module in sorted(_imported_modules(path))
        if module.startswith(FORBIDDEN_ORCHESTRATION_PREFIXES)
    ]
    assert violations == []


def _call_method_statement_count(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "__call__":
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                body = body[1:]  # bỏ docstring, không tính là câu lệnh nghiệp vụ
            return len(body)
    raise AssertionError(f"{path} không có __call__ async — không phải node hợp lệ")


def test_each_node_body_has_at_most_fifteen_statements() -> None:
    oversized = [
        f"{path.relative_to(REPOSITORY_ROOT)}: {count} câu lệnh"
        for path in _node_files()
        if (count := _call_method_statement_count(path)) > MAX_NODE_STATEMENTS
    ]
    assert oversized == []


def test_agent_services_only_contains_advisory_use_cases() -> None:
    """Advisory dependencies only; operations remain outside this registry."""
    advisory_fields = {
        "conversation",
        # Đếm số lần đã hỏi mỗi slot: cùng nhóm state phiên với `conversation`,
        # không phải chiều tiêu thụ của `operations/`. `chain.run_turn` đọc nó để
        # bỏ qua slot khách không trả lời được sau MAX_ASK_ATTEMPTS lần.
        "ask_tracking",
        "memory",
        "slot_extraction",
        "slot_planning",
        "intent_routing",
        "catalog_browse",
        "vehicle_overview",
        # Ảnh catalog để `chain.run_turn` dựng `TurnResult.recommendations`: chỉ
        # graph biết lượt này vừa đề xuất xe nào, nên việc ghép ảnh vẫn là
        # advisory chứ không phải một use case operations.
        "vehicle_media",
        # Tra `vehicle_id` từ tên xe cho các lượt NGOÀI pipeline đề xuất (đặt lịch
        # lái thử, tính chi phí cho mẫu khách vừa chốt). Thuộc nhóm advisory: nó
        # chỉ ĐỌC catalog, không ghi gì.
        "vehicle_names",
        "retrieval",
        "candidate_tuning",
        "snapshotting",
        "recommendation",
        "tco_estimation",
        "synthesis",
        # Bước 3: LLM chỉ diễn đạt lại câu hỏi slot graph vừa dựng — cùng lượt,
        # cùng lý do advisory với `synthesis` ngay trên.
        "verification",
        # Chặn nội dung nguy hiểm trước khi resume task hoặc chạy graph; đây là
        # dependency của một lượt advisory, không phải use case vận hành ngoài luồng.
        "moderation",
        # I4: tìm đoạn tài liệu chính sách cho câu hỏi bảo hành/trả góp trong CÙNG
        # lượt tư vấn (`core/act._policy_lookup`) — chỉ lượt đó biết khách đang hỏi
        # chính sách gì, không route HTTP nào đứng ra thay được.
        "policy_search",
        "scope_classifier",
        # A7-9: giá lăn bánh tính deterministic từ biểu phí đã công bố, chạy
        # thẳng không qua HITL. Cùng nhóm advisory vì chỉ graph biết lượt này
        # đang hỏi giá lăn bánh của xe nào.
        # A7-10: nối câu trả lời ngắn vào câu hỏi slot bot vừa đặt. Chạy trước
        # `classify_scope` nên phải là service của lượt, không phải route HTTP.
        "pending_slot",
        # Bốn lớp nhận diện ý định. Advisory vì cùng lý do với `pending_slot`
        # ngay trên: chúng chạy trong lượt, trước `classify_scope`, và chỉ graph
        # (hoặc `chain.run_turn`) mới biết lượt này đang ở trạng thái nào —
        # không đặt được ở route HTTP.
        "nlu_pipeline",
        # Tiêu thụ câu trả lời cho câu xác nhận ý định. Tách khỏi `pending_slot`
        # vì hai bản ghi khác hẳn ngữ nghĩa ("thiếu giá trị nào" vs "hiểu đúng ý
        # chưa") và có hai vòng đời khác nhau.
        "pending_intent_confirmation",
        "on_road_price",
        # [COMPARE_VEHICLES] Bảng so sánh 2–3 mẫu. Advisory vì cùng lý do với
        # `catalog_browse`: nó chạy TRONG lượt, đọc `intents`/entity mà chỉ graph
        # có, và quyết định của nó (đủ xe chưa, trùng xe chưa) phụ thuộc câu khách
        # vừa gõ — không đặt được ở route HTTP. Khác `POST /agent/compare` (A5-4),
        # vốn so sánh từ snapshot của một run đã có và thuộc nhóm operations.
        "compare_vehicles",
        "nearby_location",
        "test_drive",
        # Giữ task/form có cấu trúc để lượt sau có thể sửa một trường rồi chạy
        # lại đúng tool, thay vì phân loại toàn bộ câu sửa đổi như intent mới.
        "task_context",
        # A7-4: quyết định một lượt có phải chờ người duyệt không. Chỉ graph biết
        # lượt này sắp gửi gì cho khách, nên quyết định chặn/không chặn không đặt
        # được ở route HTTP.
        "quote_gate",
        # Todo 7: detector là advisory use case của node `detect_bottleneck`.
        # Persistence vẫn qua memory UoW; detector không nhận DB adapter.
        "bottleneck_detector",
        # A7-1: enqueue là CHIỀU SẢN XUẤT của hàng đợi duyệt (PRD 5.6), khác
        # chiều tiêu thụ (claim/duyệt/từ chối) ở `services/operations/review.py`.
        # `hitl` ĐÃ GỠ: `EnqueueHitlNode` không còn ghi database, nên `AgentServices`
        # không cần cổng ghi hàng đợi nữa. Việc ghi nằm ở transaction chốt outcome
        # (`ConversationMemoryService.finalize_turn`) và ở `turn_handoff`.
        # C1/C2: hai service dựng HỒ SƠ KHÁCH HÀNG và đề xuất ưu đãi kèm theo mục
        # enqueue. Chỉ graph mới biết lượt này sắp bị chặn
        # và transcript/slot của nó ra sao, nên hồ sơ phải dựng trong lượt chứ
        # không dựng lại được từ route HTTP của tư vấn viên.
        "profile_snapshot_service",
        "offer_suggestion_service",
        # Todo 4: ghi một lần chuyển người trong một giao dịch. Chốt tất định chạy
        # trong `chain.run_turn` trước cả graph, còn guardrail cạn lượt thì chỉ
        # graph mới biết — nên không route HTTP nào đứng ra làm việc này được.
        "turn_handoff",
        # J1 chống-crack: judge tiêm nhiễm là lớp HAI sau `moderation`, chạy
        # trong lượt ngay sau blocklist — chỉ chain biết vị trí đó, không đặt
        # được ở route HTTP.
        "injection_judge",
        # J2: judge risk flag nằm TRONG quote_gate (soát nội dung sắp gửi khách),
        # J3: judge vague nằm trong lượt trước graph (biết bot có hỏi không).
        "risk_flag_judge",
        "vague_answer_judge",
    }
    field_names = {f.name for f in AgentServices.__dataclass_fields__.values()}
    assert field_names == advisory_fields
