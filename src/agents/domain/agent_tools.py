"""Registry tool CHỈ-ĐỌC của agent loop (plan agent-migration Bước 4, §2.1).

Sáu tool, KHÔNG tool nào có side effect: đặt lái thử (`Book`), đẩy hàng duyệt
(`EnqueueHitl`), chuyển người (`Handoff`), sinh token khung giờ
(`ShowroomOptions`) và mọi hàm ghi DB đều nằm NGOÀI registry — LLM không có
cách nào gọi tới. `tests/agents/unit/domain/test_agent_tools.py` khẳng định
điều đó bằng tên.

Module này chỉ giữ TÊN, SCHEMA và DTO; việc chạy tool (đọc `AgentServices`)
nằm ở `core/act` (Bước 6). Tách như vậy để adapter LLM (Bước 5) dựng được
schema mà không kéo theo service, và test schema không cần mock gì.

`additionalProperties: false` + mọi field đều `required` (nullable khi khách
chưa nói): registry nhiều tool, khoá lạ dễ lẫn giữa các tool — siết từ đầu
thay vì bù bằng `extra="ignore"` như `adapters/tco_tool_llm.py`.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LLM SDK.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.agents.domain.nearby_location import LocationKind

AGENT_TOOL_TRA_THONG_SO: Final = "tra_thong_so_xe"
AGENT_TOOL_TINH_CHI_PHI: Final = "tinh_chi_phi_xe"
AGENT_TOOL_SO_SANH: Final = "so_sanh_xe"
AGENT_TOOL_TIM_DIEM: Final = "tim_diem_dich_vu"
AGENT_TOOL_DANH_MUC: Final = "liet_ke_danh_muc"
AGENT_TOOL_TRA_LOI: Final = "tra_loi_khach"

#: Cả sáu tool đều chỉ đọc. Tool KHÔNG có ở đây là tool không tồn tại với LLM.
READ_ONLY_TOOLS: Final[frozenset[str]] = frozenset(
    {
        AGENT_TOOL_TRA_THONG_SO,
        AGENT_TOOL_TINH_CHI_PHI,
        AGENT_TOOL_SO_SANH,
        AGENT_TOOL_TIM_DIEM,
        AGENT_TOOL_DANH_MUC,
        AGENT_TOOL_TRA_LOI,
    }
)

#: Mã lỗi ngắn, ASCII — đi vào transcript loop và vệt trace, KHÔNG phải chữ khách.
ERROR_UNKNOWN_TOOL: Final = "unknown_tool"
ERROR_BAD_ARGS: Final = "bad_args"
ERROR_UNKNOWN_VEHICLE: Final = "unknown_vehicle"
ERROR_TOOL_FAILED: Final = "tool_failed"
ERROR_EMPTY: Final = "empty"
ERROR_REPEAT_CALL: Final = "repeat_call"

#: Loại điểm dịch vụ LLM được chọn — đúng bằng `LocationKind` (một nguồn).
LOCATION_KIND_VALUES: Final[tuple[str, ...]] = tuple(kind.value for kind in LocationKind)
VEHICLE_TYPE_VALUES: Final[tuple[str, ...]] = ("CAR", "ELECTRIC_MOTORBIKE")


def _frozen(mapping: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(mapping or {}))


@dataclass(frozen=True, slots=True)
class AgentToolCall:
    """Một lần LLM gọi tool: tên + args thô (đã qua JSON, chưa qua schema)."""

    name: str
    args: Mapping[str, Any] = field(default_factory=lambda: _frozen({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "args", _frozen(self.args))


@dataclass(frozen=True, slots=True)
class AgentToolResult:
    """Kết quả một tool: DỮ LIỆU tất định (`payload`), KHÔNG phải chữ trả khách.

    `ok=True, error="empty"` = tra được nhưng không có dữ liệu (khác `tool_failed`
    = tra hỏng). LLM đọc cả hai để tự sửa ở bước sau.
    """

    name: str
    ok: bool
    payload: Mapping[str, Any] = field(default_factory=lambda: _frozen({}))
    error: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _frozen(self.payload))


# --------------------------------------------------------------- args (pydantic)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TraThongSoArgs(_Strict):
    vehicle_name: str = Field(min_length=1)
    question: str | None = None


class TinhChiPhiArgs(_Strict):
    vehicle_name: str = Field(min_length=1)
    daily_km: int | None = Field(default=None, ge=1, le=2000)
    province: str | None = None


class SoSanhArgs(_Strict):
    vehicle_names: list[str] = Field(min_length=2, max_length=3)


class TimDiemArgs(_Strict):
    kind: LocationKind
    area: str | None = None


class DanhMucArgs(_Strict):
    vehicle_type: Literal["CAR", "ELECTRIC_MOTORBIKE"] | None = None


class TraLoiArgs(_Strict):
    answer: str = Field(min_length=1)
    vehicle_ids_used: list[str] = Field(default_factory=list)


ARG_MODELS: Final[Mapping[str, type[_Strict]]] = MappingProxyType(
    {
        AGENT_TOOL_TRA_THONG_SO: TraThongSoArgs,
        AGENT_TOOL_TINH_CHI_PHI: TinhChiPhiArgs,
        AGENT_TOOL_SO_SANH: SoSanhArgs,
        AGENT_TOOL_TIM_DIEM: TimDiemArgs,
        AGENT_TOOL_DANH_MUC: DanhMucArgs,
        AGENT_TOOL_TRA_LOI: TraLoiArgs,
    }
)


def is_read_only(name: str) -> bool:
    """Tool này có trong registry chỉ-đọc không. Tên lạ → `False`."""

    return name in READ_ONLY_TOOLS


def parse_tool_args(name: str, args: Mapping[str, Any]) -> _Strict:
    """Args thô → model đã kiểm. Ném `KeyError` (tool lạ) / `ValidationError` (sai schema).

    Hai lỗi tách kiểu để loop ghi đúng mã: `unknown_tool` vs `bad_args`.
    """

    model = ARG_MODELS[name]
    return model.model_validate(dict(args))


# --------------------------------------------------------------- schema (OpenAI function)


def _nullable(kind: str, description: str) -> dict[str, Any]:
    return {"type": [kind, "null"], "description": description}


def _tool(name: str, description: str, properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            },
        },
    }


def build_agent_tools() -> list[dict[str, Any]]:
    """Schema OpenAI của cả sáu tool — thứ tự cố định, mô tả tiếng Việt."""

    return [
        _tool(
            AGENT_TOOL_TRA_THONG_SO,
            "Tra thông số kỹ thuật của MỘT mẫu xe (tầm chạy, pin, số chỗ, trang bị). "
            "Chỉ dùng tên xe có trong khối Danh sách xe đã cho.",
            {
                "vehicle_name": {
                    "type": "string",
                    "description": "Tên chuẩn của mẫu xe, lấy đúng từ khối Danh sách xe.",
                },
                "question": _nullable(
                    "string", "Khía cạnh khách hỏi (ví dụ tầm chạy, cốp); null nếu muốn xem tổng quan."
                ),
            },
        ),
        _tool(
            AGENT_TOOL_TINH_CHI_PHI,
            "Tính chi phí sử dụng 5 năm và giá lăn bánh của MỘT mẫu xe. "
            "Chỉ dùng tên xe có trong khối Danh sách xe đã cho.",
            {
                "vehicle_name": {
                    "type": "string",
                    "description": "Tên chuẩn của mẫu xe, lấy đúng từ khối Danh sách xe.",
                },
                "daily_km": _nullable("integer", "Số km khách chạy mỗi ngày; null nếu khách chưa nói."),
                "province": _nullable("string", "Tỉnh hoặc thành phố đăng ký xe; null nếu khách chưa nói."),
            },
        ),
        _tool(
            AGENT_TOOL_SO_SANH,
            "So sánh 2 đến 3 mẫu xe trên cùng bộ tiêu chí (giá, tầm chạy, số chỗ, trang bị). "
            "Chỉ dùng tên xe có trong khối Danh sách xe đã cho.",
            {
                "vehicle_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tên chuẩn của 2 đến 3 mẫu xe cần so, lấy đúng từ khối Danh sách xe.",
                },
            },
        ),
        _tool(
            AGENT_TOOL_TIM_DIEM,
            "Tìm showroom, xưởng dịch vụ, trạm sạc hoặc tủ đổi pin gần khách.",
            {
                "kind": {
                    "type": "string",
                    "enum": list(LOCATION_KIND_VALUES),
                    "description": "Loại điểm cần tìm.",
                },
                "area": _nullable("string", "Khu vực khách nêu (quận, tỉnh, thành phố); null nếu khách chưa nói."),
            },
        ),
        _tool(
            AGENT_TOOL_DANH_MUC,
            "Liệt kê các mẫu xe đang bán theo loại xe.",
            {
                "vehicle_type": {
                    "type": ["string", "null"],
                    "enum": [*VEHICLE_TYPE_VALUES, None],
                    "description": "Loại xe: ô tô hoặc xe máy điện, chọn đúng một giá trị trong danh sách; null nếu muốn xem cả hai.",
                },
            },
        ),
        _tool(
            AGENT_TOOL_TRA_LOI,
            "Nộp câu trả lời cuối cùng cho khách. Gọi tool này khi đã đủ dữ liệu. "
            "Mọi con số trong câu trả lời phải lấy nguyên văn từ kết quả tool, "
            "tuyệt đối không tự tính, không làm tròn, không ước lượng.",
            {
                "answer": {"type": "string", "description": "Câu trả lời tiếng Việt, xưng em với anh/chị."},
                "vehicle_ids_used": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Id các xe đã nhắc tới trong câu trả lời.",
                },
            },
        ),
    ]


__all__ = [
    "AGENT_TOOL_DANH_MUC",
    "AGENT_TOOL_SO_SANH",
    "AGENT_TOOL_TIM_DIEM",
    "AGENT_TOOL_TINH_CHI_PHI",
    "AGENT_TOOL_TRA_LOI",
    "AGENT_TOOL_TRA_THONG_SO",
    "ARG_MODELS",
    "ERROR_BAD_ARGS",
    "ERROR_EMPTY",
    "ERROR_REPEAT_CALL",
    "ERROR_TOOL_FAILED",
    "ERROR_UNKNOWN_TOOL",
    "ERROR_UNKNOWN_VEHICLE",
    "LOCATION_KIND_VALUES",
    "READ_ONLY_TOOLS",
    "VEHICLE_TYPE_VALUES",
    "AgentToolCall",
    "AgentToolResult",
    "DanhMucArgs",
    "SoSanhArgs",
    "TimDiemArgs",
    "TinhChiPhiArgs",
    "TraLoiArgs",
    "TraThongSoArgs",
    "ValidationError",
    "build_agent_tools",
    "is_read_only",
    "parse_tool_args",
]
