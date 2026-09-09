"use client";

import type React from "react";

import { PreviewLink } from "@/components/common/preview-link";

/**
 * Render văn bản Markdown rút gọn mà agent sinh ra: chữ đậm, mục đánh số,
 * bullet, và xuống dòng thật.
 *
 * Vì sao cần component này thay vì `{text}`: React in một chuỗi thành MỘT text
 * node, và HTML gộp mọi khoảng trắng liên tiếp — kể cả `\n` — thành một dấu
 * cách. Backend vẫn trả về đúng bố cục có xuống dòng (`domain/reply_format`),
 * nhưng đổ thẳng vào JSX thì cả câu trả lời dồn thành một đoạn văn liền mạch.
 * Đó là lỗi khách nhìn thấy, và nó nằm ở tầng hiển thị chứ không ở tầng sinh chữ.
 *
 * Cố ý KHÔNG kéo thêm `react-markdown`: cú pháp agent dùng chỉ có bốn thứ dưới
 * đây, còn một trình phân tích Markdown đầy đủ mang theo HTML thô, link và ảnh —
 * tức là một bề mặt injection mới cho nội dung do LLM sinh, đổi lấy những cú
 * pháp không ai dùng.
 *
 * Cú pháp được hỗ trợ:
 * - `**đậm**` (kể cả nhiều lần trong một dòng).
 * - `*gợi ý*` → chữ nghiêng, màu dịu; `* ` ở đầu dòng vẫn là bullet.
 * - `[nhãn](/duong-dan)` → liên kết NỘI BỘ, xem `INTERNAL_LINK` bên dưới.
 * - `1. **Mục lớn**:` → mục đánh số của một danh sách.
 * - `* nội dung` hoặc `- nội dung` → bullet.
 * - Dòng trống → tách đoạn.
 *
 * Mọi thứ khác đi qua nguyên văn dưới dạng text node, nên không có đường nào để
 * chuỗi trả về biến thành thẻ HTML.
 */

/**
 * Liên kết nội bộ: nhãn không chứa `]`, đường dẫn CHỈ được là đường dẫn tương
 * đối bắt đầu bằng đúng một dấu `/`.
 *
 * Ràng buộc đó là cả lý do component này dám mở cú pháp link. Nội dung ở đây do
 * LLM sinh; cho phép `http(s)` hay `javascript:` là mở đúng bề mặt injection mà
 * docstring trên vừa nói là lý do không dùng `react-markdown`. `(?!\/)` chặn
 * `//evil.com` — trình duyệt đọc nó là URL tuyệt đối theo giao thức hiện tại.
 */
const INTERNAL_LINK = /(\[[^\]\n]+\]\((?:\/(?!\/)|https:\/\/www\.google\.com\/maps\/)[^\s)]*\))/g;
const HINT = /(?<!\*)\*((?:\*\*[^*\n]+\*\*|[^*\n])+)\*(?!\*)/g;

function renderInline(text: string, keyPrefix: string): React.ReactNode[] {
  return text.split(HINT).flatMap((chunk, chunkIndex): React.ReactNode[] => {
    if (chunk === "") return [];
    const chunkKey = `${keyPrefix}-${chunkIndex}`;
    if (chunkIndex % 2 === 1) {
      return [
        <em className="rich-text-hint" key={chunkKey}>
          {renderLinks(chunk, chunkKey)}
        </em>,
      ];
    }
    return renderLinks(chunk, chunkKey);
  });
}

function renderLinks(text: string, keyPrefix: string): React.ReactNode[] {
  return text.split(INTERNAL_LINK).flatMap((chunk, chunkIndex): React.ReactNode[] => {
    if (chunk === "") return [];
    const chunkKey = `${keyPrefix}-${chunkIndex}`;
    const link = /^\[([^\]\n]+)\]\((\/[^\s)]*)\)$/.exec(chunk);
    if (link) {
      return [
        <PreviewLink href={link[2]} key={chunkKey}>
          {renderBold(link[1], chunkKey)}
        </PreviewLink>,
      ];
    }
    // Ngoại lệ DUY NHẤT cho link tuyệt đối: chỉ đường Google Maps sau khi đặt
    // lịch lái thử (Sếp 2026-08-31 "bắn sang giao diện gg map"). Allowlist chết
    // cứng đúng một tiền tố — không mở http(s) chung, lý do ở docstring trên.
    const mapsLink = /^\[([^\]\n]+)\]\((https:\/\/www\.google\.com\/maps\/[^\s)]*)\)$/.exec(chunk);
    if (mapsLink) {
      return [
        <a href={mapsLink[2]} key={chunkKey} rel="noopener noreferrer" target="_blank">
          {renderBold(mapsLink[1], chunkKey)}
        </a>,
      ];
    }
    return renderBold(chunk, chunkKey);
  });
}

/** `**đậm**` → `<strong>`; phần còn lại giữ nguyên văn. */
function renderBold(text: string, keyPrefix: string): React.ReactNode[] {
  // Bắt cặp `**...**` không rỗng và không nuốt qua một cặp khác (`[^*]`).
  return text.split(/(\*\*[^*]+\*\*)/g).flatMap((part, index): React.ReactNode[] => {
    if (part === "") return [];
    const key = `${keyPrefix}-${index}`;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return [<strong key={key}>{part.slice(2, -2)}</strong>];
    }
    return [<span key={key}>{part}</span>];
  });
}

type Block =
  | { readonly kind: "paragraph"; readonly lines: string[] }
  | { readonly kind: "bullets"; readonly lines: string[] };

const BULLET_PREFIX = /^[*-]\s+/;

/**
 * Gom các dòng liền nhau thành khối.
 *
 * Bullet liền nhau thành MỘT `<ul>`; mọi thứ khác gộp thành đoạn. Dòng "1. **Mục
 * lớn**:" cố ý KHÔNG thành `<ol>`: số thứ tự do backend sinh và đã nằm sẵn trong
 * chữ, nên để trình duyệt tự đánh số nữa sẽ ra "1. 1. Thông số kỹ thuật".
 */
function toBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (trimmed === "") {
      // Dòng trống đóng khối đang mở; khối rỗng không được tạo ra.
      if (blocks.length > 0 && blocks[blocks.length - 1].lines.length > 0) {
        blocks.push({ kind: "paragraph", lines: [] });
      }
      continue;
    }
    const isBullet = BULLET_PREFIX.test(trimmed);
    const kind = isBullet ? "bullets" : "paragraph";
    const content = isBullet ? trimmed.replace(BULLET_PREFIX, "") : trimmed;
    const last = blocks[blocks.length - 1];
    if (last !== undefined && last.kind === kind && last.lines.length > 0) {
      last.lines.push(content);
    } else if (last !== undefined && last.lines.length === 0) {
      blocks[blocks.length - 1] = { kind, lines: [content] };
    } else {
      blocks.push({ kind, lines: [content] });
    }
  }
  return blocks.filter((block) => block.lines.length > 0);
}

export function RichText({ text }: Readonly<{ text: string }>): React.JSX.Element {
  const blocks = toBlocks(text);
  return (
    <div className="rich-text">
      {blocks.map((block, blockIndex) =>
        block.kind === "bullets" ? (
          <ul key={`b-${blockIndex}`}>
            {block.lines.map((line, lineIndex) => (
              <li key={`b-${blockIndex}-${lineIndex}`}>
                {renderInline(line, `b-${blockIndex}-${lineIndex}`)}
              </li>
            ))}
          </ul>
        ) : (
          <p key={`p-${blockIndex}`}>
            {block.lines.flatMap((line, lineIndex) => [
              // Nhiều dòng không có dòng trống ở giữa vẫn là một đoạn, nhưng mỗi
              // dòng phải xuống dòng thật — đó là bố cục backend đã chọn.
              ...(lineIndex > 0 ? [<br key={`p-${blockIndex}-${lineIndex}-br`} />] : []),
              ...renderInline(line, `p-${blockIndex}-${lineIndex}`),
            ])}
          </p>
        ),
      )}
    </div>
  );
}
