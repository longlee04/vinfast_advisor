"""Chuẩn hoá brochure ô tô trong `data-p150/car_pdf/` thành chunk cho `vehicle_documents`.

Nguồn crawl là trang đại lý nên trộn ba loại nội dung: mô tả sản phẩm dùng được,
nội dung chào mời (hotline, khuyến mãi, trả góp) và rác giao diện web (menu, form
rỗng, bảng bị bẹp thành dòng chạy). `quote_evidence_from()` trích nguyên văn chunk
ra câu trả lời cho khách, nên mọi thứ ngoài nhóm thứ nhất phải bị loại trước khi
embedding, không lọc sau.

Số liệu định lượng (giá, range, công suất, dung lượng pin) KHÔNG đi qua đây: nguồn
uy quyền là `vehicle_prices` và `cars`. Brochure gộp nhiều phiên bản trong một trang
nên giữ lại số sẽ gán nhầm thông số bản Plus cho bản Eco.

    python scripts/build_car_documents.py --dry-run    # thống kê + CSV review
    python scripts/build_car_documents.py --load       # embedding + ghi DB
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

SOURCE_DIR = REPO_ROOT / "data-p150" / "car_pdf"
REVIEW_CSV = REPO_ROOT / "data-p150" / "catalog" / "vehicle_documents_car_review.csv"
# Chunk thu thập ngoài brochure (bài báo, PDF chính sách). Nạp mặc định nếu có mặt
# để chạy lại từ máy sạch ra đúng corpus, không phải nhớ thêm cờ.
DEFAULT_EXTRA_CSV = REPO_ROOT / "data-p150" / "catalog" / "vehicle_documents_extra.csv"

# `doc_id` trong front-matter -> `model_name` trong bảng `vehicles`. Chunk gán cho
# mọi biến thể của model vì phần giữ lại chỉ mô tả định tính ở mức model.
DOC_TO_MODEL: dict[str, str] = {
    "VF2": "VF 2",
    "VF3": "VF 3",
    "VF5": "VF 5",
    "VF6": "VF 6",
    "VF7": "VF 7",
    "VF8": "VF 8",
    "VF8_2026": "VF 8",
    "VF9": "VF 9",
    # MPV7 chưa có hàng tương ứng trong `vehicles`; bỏ qua thay vì gán bừa.
}

# Mục mô tả sản phẩm. So khớp trên tiêu đề đã bỏ dấu `#`.
SECTION_ALLOW = re.compile(
    r"(ngoại thất|nội thất|vận hành|an toàn|tiện nghi|thiết kế"
    r"|là mẫu xe như thế nào|định vị phân khúc|đối tượng khách hàng"
    r"|sẽ thu hút ai|điểm đáng chú ý|công nghệ"
    # Cấu trúc .md viết lại (2026-08-12) đổi tên mục và thêm nhóm theo nhu cầu —
    # nhóm nhu cầu là phần khớp trực tiếp với câu hỏi của khách nên phải giữ.
    r"|hệ truyền động|pin và sạc|pin và quãng đường|khung gầm|bảng màu"
    r"|ghế và không gian|không gian chứa đồ|điểm nổi bật|tóm tắt điểm mạnh"
    r"|phù hợp với nhu cầu|đi phố|đô thị|gia đình|đi đường dài|đi đèo|đường dốc"
    r"|người thích|người mua|đi làm|du lịch|công việc|đưa đón|cao tốc"
    r"|dịch vụ vận tải)",
    re.IGNORECASE,
)

# Mục chào mời, tài chính, rác web. Kiểm tra trước ALLOW vì vài tiêu đề chứa cả hai
# (ví dụ "VinFast gửi bạn GIÁ BÁN ĐẶC BIỆT ... ƯU ĐÃI ... HOTLINE").
SECTION_DENY = re.compile(
    r"(khuyến mãi|ưu đãi|giá bán|bảng giá|trả góp|tính lãi|chính sách"
    r"|hình ảnh|video|liên hệ|gửi bạn|chính hãng tại|vinfast việt nam"
    r"|thông số|kết luận|tổng quan)",
    re.IGNORECASE,
)

# Dòng mang nội dung bán hàng hoặc điều hướng web.
LINE_DENY = re.compile(
    r"(hotline|liên hệ|đặt cọc|trả góp|vay|lãi suất|khuyến mãi|ưu đãi|báo giá"
    r"|quà tặng|showroom|đại lý|hồ sơ|ngân hàng|cứu hộ miễn phí|giảm giá"
    r"|\b0\d{2}[.\s]?\d{3}[.\s]?\d{3,4}\b)",
    re.IGNORECASE,
)

# Số tiền và mọi số nhóm nghìn kiểu 789.000.000 — giá thuộc về `vehicle_prices`.
MONEY = re.compile(r"(\d[\d.,]*\s*(vnđ|vnd|triệu|tỷ)|\d{1,3}(\.\d{3}){2,})", re.IGNORECASE)

# Thông số truyền động, pin và quãng đường: bảng `cars` mới là nguồn uy quyền.
# Brochure gộp nhiều phiên bản nên số ở đây vừa lệch hệ đo vừa lệch phiên bản —
# ví dụ VF 6 ghi 460/485 km trong khi `cars` ghi 310/315 km WLTP. Giữ lại là để
# guardrail đối chiếu hai con số mâu thuẫn của cùng một chiếc xe.
SPEC_NUMBER = re.compile(r"\d[\d.,]*\s*(kwh|kw|nm|km|mã lực|hp)\b", re.IGNORECASE)

# Đoạn văn ngắn hơn ngưỡng này trong bộ nguồn đều là mẩu menu, nhãn form hoặc
# dòng bảng bị bẹp, không phải câu mô tả.
MIN_PARAGRAPH_CHARS = 200
MAX_CHUNK_CHARS = 1500

# Văn bản chính sách trích từ PDF gốc: câu ngắn vẫn là một điều khoản trọn vẹn,
# nên ngưỡng 200 (đặt ra để giết mẩu menu web) không áp dụng được.
EXTRA_MIN_CHARS = 120

# `ưu đãi` trong thông báo chính sách là tên gọi của quyền lợi, không phải lời
# chào bán như trên trang đại lý — chặn nó ở đây thì loại sạch nội dung chính sách.
POLICY_LINE_DENY = re.compile(
    r"(hotline|showroom|đại lý|trả góp|lãi suất|báo giá|\b0\d{2}[.\s]?\d{3}[.\s]?\d{3,4}\b)",
    re.IGNORECASE,
)

# Chunk gán cho mọi xe đang bán, dùng cho tài liệu áp dụng chung như chính sách sạc.
ALL_MODELS = "*"

EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_VERSION = "v1"
DOCUMENT_TYPE = "OVERVIEW"
CREATED_BY = "car_brochure_import"


@dataclass
class Chunk:
    """Một đoạn đã lọc, chưa gắn `vehicle_id`."""

    doc_id: str
    model_name: str
    section_title: str
    content: str
    chunk_index: int
    source_url: str
    source_hash: str
    document_type: str = DOCUMENT_TYPE


@dataclass
class FileStats:
    """Số liệu lọc của một file, để review trước khi ghi DB."""

    doc_id: str
    paragraphs: int = 0
    kept: int = 0
    dropped_section: int = 0
    dropped_short: int = 0
    dropped_sales: int = 0
    dropped_money: int = 0
    dropped_spec: int = 0
    dropped_duplicate: int = 0
    sections: set[str] = field(default_factory=set)


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Tách front-matter YAML đơn giản khỏi phần thân."""

    if not text.startswith("---"):
        return {}, text
    _, _, rest = text.partition("---\n")
    raw_meta, _, body = rest.partition("---\n")
    meta = {}
    for line in raw_meta.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    return meta, body


def split_paragraphs(body: str) -> list[tuple[str, str]]:
    """Trả `(section_title, paragraph)` theo tiêu đề gần nhất phía trên."""

    current = ""
    out: list[tuple[str, str]] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            current = line.lstrip("#").strip()
            continue
        out.append((current, line))
    return out


def split_long(content: str) -> list[str]:
    """Cắt đoạn quá dài theo ranh giới câu để không đứt giữa mệnh đề."""

    if len(content) <= MAX_CHUNK_CHARS:
        return [content]
    parts: list[str] = []
    buffer = ""
    for sentence in re.split(r"(?<=[.!?])\s+", content):
        if buffer and len(buffer) + len(sentence) + 1 > MAX_CHUNK_CHARS:
            parts.append(buffer.strip())
            buffer = sentence
        else:
            buffer = f"{buffer} {sentence}".strip()
    if buffer:
        parts.append(buffer.strip())
    return parts


def normalise(text: str) -> str:
    """Khoá khử trùng lặp: cùng câu boilerplate lặp ở nhiều file chỉ giữ một lần."""

    return re.sub(r"\s+", " ", text).strip().lower()


def build_chunks() -> tuple[list[Chunk], list[FileStats]]:
    """Đọc toàn bộ brochure, lọc và trả chunk sạch kèm thống kê từng file."""

    chunks: list[Chunk] = []
    stats: list[FileStats] = []
    seen: set[str] = set()

    for path in sorted(SOURCE_DIR.glob("*.md")):
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        doc_id = meta.get("doc_id", path.stem)
        stat = FileStats(doc_id=doc_id)
        stats.append(stat)

        model_name = DOC_TO_MODEL.get(doc_id)
        if model_name is None:
            # Bỏ trước vòng lọc, nếu không các đoạn của file không map được sẽ
            # chiếm chỗ trong `seen` và làm đoạn tương tự ở file map được bị coi
            # là trùng rồi biến mất.
            continue
        source_url = meta.get("source_url", "")
        source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        index = 0

        for section_title, paragraph in split_paragraphs(body):
            stat.paragraphs += 1
            if SECTION_DENY.search(section_title) or not SECTION_ALLOW.search(section_title):
                stat.dropped_section += 1
                continue
            if len(paragraph) < MIN_PARAGRAPH_CHARS:
                stat.dropped_short += 1
                continue
            if LINE_DENY.search(paragraph):
                stat.dropped_sales += 1
                continue
            if MONEY.search(paragraph):
                stat.dropped_money += 1
                continue
            if SPEC_NUMBER.search(paragraph):
                stat.dropped_spec += 1
                continue
            key = normalise(paragraph)
            if key in seen:
                stat.dropped_duplicate += 1
                continue
            seen.add(key)

            for piece in split_long(paragraph):
                chunks.append(
                    Chunk(
                        doc_id=doc_id,
                        model_name=model_name,
                        section_title=section_title,
                        content=piece,
                        chunk_index=index,
                        source_url=source_url,
                        source_hash=source_hash,
                    )
                )
                index += 1
                stat.kept += 1
            stat.sections.add(section_title)

    return chunks, stats


def load_extra_chunks(path: Path, existing: list[Chunk]) -> list[Chunk]:
    """Nạp chunk thu thập ngoài `car_pdf/` (CSV: model_name, section_title, content, source_url).

    Áp cùng bộ lọc như brochure — nguồn khác không phải lý do để lọt giá, số
    truyền động hay nội dung chào mời vào corpus.
    """

    index_by_model: dict[str, int] = {}
    for chunk in existing:
        index_by_model[chunk.model_name] = max(index_by_model.get(chunk.model_name, -1), chunk.chunk_index) + 1

    seen = {normalise(c.content) for c in existing}
    extra: list[Chunk] = []
    rejected = 0
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            content = (row.get("content") or "").strip()
            model_name = (row.get("model_name") or "").strip()
            if not content or not model_name:
                continue
            document_type = (row.get("document_type") or DOCUMENT_TYPE).strip()
            deny = POLICY_LINE_DENY if document_type == "POLICY" else LINE_DENY
            if (
                len(content) < EXTRA_MIN_CHARS
                or deny.search(content)
                or MONEY.search(content)
                or SPEC_NUMBER.search(content)
                or normalise(content) in seen
            ):
                rejected += 1
                continue
            seen.add(normalise(content))
            source_url = (row.get("source_url") or "").strip()
            index = index_by_model.get(model_name, 0)
            for piece in split_long(content):
                extra.append(
                    Chunk(
                        doc_id=f"extra:{model_name}",
                        model_name=model_name,
                        section_title=(row.get("section_title") or "").strip(),
                        content=piece,
                        chunk_index=index,
                        source_url=source_url,
                        source_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                        document_type=document_type,
                    )
                )
                index += 1
            index_by_model[model_name] = index
    print(f"Chunk bo sung: nhan {len(extra)}, loai {rejected} (ngan/co gia/co spec/trung)")
    return extra


def report(chunks: list[Chunk], stats: list[FileStats]) -> None:
    """In thống kê lọc và ghi CSV để đọc lại từng chunk trước khi nạp."""

    print(
        f"{'file':12} {'doan':>5} {'giu':>4} {'ngoai-muc':>10} {'ngan':>5} "
        f"{'ban-hang':>9} {'co-gia':>7} {'co-spec':>8} {'trung':>6}"
    )
    for stat in stats:
        print(
            f"{stat.doc_id:12} {stat.paragraphs:5} {stat.kept:4} {stat.dropped_section:10} "
            f"{stat.dropped_short:5} {stat.dropped_sales:9} {stat.dropped_money:7} "
            f"{stat.dropped_spec:8} {stat.dropped_duplicate:6}"
        )
    total_chars = sum(len(c.content) for c in chunks)
    print(
        f"\nTong chunk sach: {len(chunks)} | {total_chars} ky tu | "
        f"trung binh {total_chars // max(len(chunks), 1)} ky tu/chunk"
    )

    by_model: dict[str, int] = {}
    for chunk in chunks:
        by_model[chunk.model_name] = by_model.get(chunk.model_name, 0) + 1
    print("Theo model: " + ", ".join(f"{k}={v}" for k, v in sorted(by_model.items())))

    REVIEW_CSV.parent.mkdir(parents=True, exist_ok=True)
    with REVIEW_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["doc_id", "model_name", "section_title", "chunk_index", "chars", "content"])
        for chunk in chunks:
            writer.writerow(
                [
                    chunk.doc_id,
                    chunk.model_name,
                    chunk.section_title,
                    chunk.chunk_index,
                    len(chunk.content),
                    chunk.content,
                ]
            )
    print(f"CSV review: {REVIEW_CSV.relative_to(REPO_ROOT)}")


def resolve_dsn(explicit: str | None) -> str:
    """DSN async cho SQLAlchemy. `Settings` chưa có URL riêng cho product/agent."""

    dsn = explicit or os.environ.get("PRODUCT_DATABASE_URL") or os.environ.get("AGENT_DATABASE_URL")
    if not dsn:
        raise SystemExit("Thieu DSN: dat PRODUCT_DATABASE_URL/AGENT_DATABASE_URL hoac truyen --dsn")
    if dsn.startswith("postgresql://"):
        dsn = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    return dsn


async def load(chunks: list[Chunk], dsn: str) -> None:
    """Sinh embedding thật rồi upsert vào `vehicle_documents` với `status=ACTIVE`."""

    from sqlalchemy import delete, select
    from sqlalchemy.dialects.postgresql import insert
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from src.agents.adapters.embedding import EMBEDDING_DIMENSION, OpenAIEmbeddingAdapter
    from src.config import get_settings
    from src.document.infrastructure.models import VehicleDocumentRow
    from src.products.infrastructure.models import VehicleRow

    if not get_settings().openai_api_key:
        raise SystemExit("OPENAI_API_KEY trong: khong sinh duoc embedding that")

    engine = create_async_engine(dsn)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(VehicleRow.vehicle_id, VehicleRow.model_name).where(
                    VehicleRow.vehicle_type == "CAR",
                    # Xe ARCHIVED không xuất hiện trong tư vấn nên cũng không cần
                    # tài liệu; gán vào chỉ làm phình corpus.
                    VehicleRow.status == "ACTIVE",
                )
            )
        ).all()
    model_to_vehicles: dict[str, list[str]] = {}
    for vehicle_id, model_name in rows:
        model_to_vehicles.setdefault(model_name, []).append(vehicle_id)
    model_to_vehicles[ALL_MODELS] = [vehicle_id for vehicle_id, _ in rows]

    missing = sorted({c.model_name for c in chunks} - set(model_to_vehicles))
    if missing:
        raise SystemExit(f"Model khong co trong bang vehicles: {missing}")

    adapter = OpenAIEmbeddingAdapter(EMBEDDING_MODEL)
    vectors: list[list[float]] = []
    batch = 64
    for start in range(0, len(chunks), batch):
        window = [c.content for c in chunks[start : start + batch]]
        batch_vectors = await adapter.embed(window)
        # Adapter nuốt lỗi API rồi tụt xuống vector băm 1536 chiều. Chặn ở đây,
        # nếu không sẽ ghi vector giả vào cột 1024 và chỉ vỡ ở tầng DB.
        wrong = {len(v) for v in batch_vectors} - {EMBEDDING_DIMENSION}
        if wrong:
            raise SystemExit(f"Embedding sai chieu {sorted(wrong)}: OpenAI that bai, da tut xuong fallback")
        vectors.extend(batch_vectors)
        print(f"  embedded {min(start + batch, len(chunks))}/{len(chunks)}")

    now = datetime.now(UTC)
    payload = []
    for chunk, vector in zip(chunks, vectors, strict=True):
        for vehicle_id in model_to_vehicles[chunk.model_name]:
            key = f"{chunk.doc_id}:{vehicle_id}:{chunk.chunk_index}"
            payload.append(
                {
                    "document_id": str(uuid5(NAMESPACE_URL, key)),
                    "vehicle_id": vehicle_id,
                    "source_content_hash": chunk.source_hash,
                    "document_type": chunk.document_type,
                    "title": f"{chunk.model_name} — {chunk.section_title}"[:255],
                    "content": chunk.content,
                    "chunk_index": chunk.chunk_index,
                    "section_title": chunk.section_title[:255],
                    "source_url": chunk.source_url,
                    "embedding_model": EMBEDDING_MODEL,
                    "embedding_version": EMBEDDING_VERSION,
                    "embedding": vector,
                    "status": "ACTIVE",
                    "valid_from": now,
                    "created_by": CREATED_BY,
                    "approved_by": CREATED_BY,
                    "approved_at": now,
                    "created_at": now,
                    "updated_at": now,
                }
            )

    async with session_factory() as session, session.begin():
        await session.execute(delete(VehicleDocumentRow).where(VehicleDocumentRow.created_by == CREATED_BY))
        statement = insert(VehicleDocumentRow).values(payload)
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[VehicleDocumentRow.document_id],
                set_={
                    "content": statement.excluded.content,
                    "embedding": statement.excluded.embedding,
                    "title": statement.excluded.title,
                    "section_title": statement.excluded.section_title,
                    "source_content_hash": statement.excluded.source_content_hash,
                    "status": statement.excluded.status,
                    "updated_at": statement.excluded.updated_at,
                },
            )
        )
    await engine.dispose()
    print(f"Da ghi {len(payload)} hang vehicle_documents cho {len(model_to_vehicles)} model.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="chi thong ke va xuat CSV review")
    parser.add_argument("--load", action="store_true", help="sinh embedding va ghi DB")
    parser.add_argument("--dsn", help="DSN Postgres; mac dinh doc PRODUCT_DATABASE_URL/AGENT_DATABASE_URL")
    parser.add_argument(
        "--extra-chunks",
        type=Path,
        help="CSV chunk thu thap ngoai car_pdf/; mac dinh dung data-p150/catalog/vehicle_documents_extra.csv",
    )
    args = parser.parse_args()

    chunks, stats = build_chunks()
    extra_path = args.extra_chunks or (DEFAULT_EXTRA_CSV if DEFAULT_EXTRA_CSV.exists() else None)
    if extra_path:
        chunks.extend(load_extra_chunks(extra_path, chunks))
    report(chunks, stats)

    if args.load:
        asyncio.run(load(chunks, resolve_dsn(args.dsn)))
    elif not args.dry_run:
        print("\nChua ghi gi. Them --load de sinh embedding va nap DB.")


if __name__ == "__main__":
    main()
