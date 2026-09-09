export type TurnOption = {
  readonly label: string;
  readonly value: string;
};

export type Citation = {
  readonly index: number;
};

export type RecommendedVehicle = {
  readonly vehicle_id: string;
  readonly rank: number;
  readonly display_name: string;
  readonly image_url: string | null;
  readonly starting_price_vnd: string | null;
  /** Đoạn văn riêng của xe này — cùng nội dung với phần tương ứng trong `answer`. */
  readonly pitch: string;
  readonly citations: readonly Citation[];
};

/** Một dòng tiêu chí của bảng so sánh: mã cột catalog + nhãn gửi khách. */
export type ComparisonSpecField = {
  readonly code: string;
  readonly label: string;
};

/**
 * Một cột của bảng so sánh do agent trả về.
 *
 * `found: false` là trạng thái HỢP LỆ, không phải lỗi: khách nêu một mẫu không
 * còn trong danh mục thì cột đó nói đúng như vậy, các cột kia vẫn hiện.
 */
export type ComparedVehicle = {
  readonly vehicle_id: string;
  readonly found: boolean;
  readonly display_name: string;
  readonly vehicle_type: string;
  readonly image_url: string | null;
  readonly starting_price_vnd: string | null;
  /** `mã cột catalog` → giá trị đã thành chuỗi. Cột thiếu dữ liệu vắng mặt hẳn. */
  readonly specs: Readonly<Record<string, string>>;
};

export type VehicleComparison = {
  readonly vehicles: readonly ComparedVehicle[];
  readonly spec_fields: readonly ComparisonSpecField[];
  /** Đoạn tóm tắt do agent sinh, đặt ngay dưới phần ảnh. Rỗng thì không hiện. */
  readonly summary: string;
  readonly missing_vehicle_names: readonly string[];
};

/** Năm loại địa điểm agent có thể tìm. */
export type LocationKind =
  | "SHOWROOM_CAR"
  | "SHOWROOM_MOTORBIKE"
  | "CHARGING_STATION_CAR"
  | "CHARGING_STATION_MOTORBIKE"
  | "BATTERY_SWAP_CABINET"
  | "SERVICE_WORKSHOP_CAR"
  | "SERVICE_WORKSHOP_MOTORBIKE";

export type NearbyLocation = {
  readonly id: string;
  readonly name: string;
  readonly address: string;
  readonly latitude: number;
  readonly longitude: number;
  readonly distance_km: number | null;
  readonly location_type: LocationKind | string;
  readonly category_label: string;
  readonly maps_url: string;
  readonly charger_type: string | null;
  readonly hotline: string | null;
  readonly open_time: string | null;
  readonly close_time: string | null;
  readonly status: string | null;
};

export type NearbyLocationList = {
  readonly results: readonly NearbyLocation[];
  readonly location_types: readonly string[];
  readonly origin_latitude: number | null;
  readonly origin_longitude: number | null;
  readonly origin_label: string | null;
  readonly searched_radius_km: number | null;
  readonly needs_location_kind: boolean;
   readonly needs_location: boolean;
   readonly quick_replies?: readonly QuickReply[];
};


/** Nút bấm gợi ý — `value` là chuỗi client gửi lại như một tin nhắn thường. */
export type QuickReply = {
  readonly label: string;
  readonly value: string;
};

export type TurnResponse = {
  readonly answer: string | null;
  readonly pending_question: string | null;
  readonly lookup_facts: readonly Record<string, unknown>[];
  readonly terminal_reason: string | null;
  readonly conversation_state?: string | null;
  readonly options?: readonly TurnOption[] | null;
  readonly vehicle_type?: string | null;
  /**
   * A7-4: lượt này đã vào hàng đợi tư vấn viên hay chưa.
   */
  readonly awaiting_review?: boolean;
  /** Optional vì backend cũ không gửi; thiếu thì chỉ hiện `answer` như trước. */
  readonly recommendations?: readonly RecommendedVehicle[];
  /**
   * Bảng so sánh của lượt `COMPARE_VEHICLES`. `null`/vắng mặt ở mọi lượt khác.
   * `answer` vẫn chở toàn văn bảng dạng chữ, nên client chưa render bảng cũng
   * không mất nội dung nào.
   */
  readonly comparison?: VehicleComparison | null;
  /**
   * Danh sách địa điểm của lượt `FIND_NEARBY_LOCATION`.
   */
  readonly nearby_locations?: NearbyLocationList | null;
  /** Nút bấm gợi ý của lượt. */
  readonly quick_replies?: readonly QuickReply[];
  /**
   * Thẻ chi phí 5 năm mà khách CHỈNH ĐƯỢC ngay tại chỗ (Sếp 2026-08-27).
   * `null`/vắng mặt ở mọi lượt khác. `answer` vẫn chở khối chữ như cũ, nên
   * client chưa render thẻ cũng không mất nội dung nào.
   */
  readonly tco_card?: TcoCard | null;
  readonly test_drive_card?: TestDriveCard | null;
  /**
   * Thẻ chi tiết xe khách vừa chốt — dữ liệu CÓ CẤU TRÚC.
   *
   * Tuỳ chọn VÀ nhận `null`: backend mới + frontend cũ vẫn chạy, frontend mới +
   * backend cũ nhận `undefined` và ẩn thẻ. `answer` vẫn chở toàn văn nên client
   * chưa render thẻ cũng không mất nội dung nào.
   */
  readonly vehicle_details?: VehicleDetails | null;
  /**
   * `next_step_panel` (nút "bước tiếp theo" trong đoạn chat) đã BỎ ở client
   * đợt 10: nút điều hướng chen giữa hội thoại kéo khách rời mạch trò chuyện.
   * Backend vẫn gửi trường này cho client cũ — client mới cố ý không khai báo
   * để không ai render lại nó; JSON thừa trường thì parse vẫn chạy bình thường.
   */
  /**
   * "Trang web đi theo hội thoại" (hợp đồng đợt 9, 2026-08-31): lõi bảo client
   * mở panel bên cạnh chat — trang chi tiết xe khách vừa chốt, hoặc bản đồ
   * showroom khi khách xin lái thử. `null`/vắng mặt ở mọi lượt khác, và client
   * KHÔNG tự đóng panel khi lượt sau không có: khách vẫn đang xem thứ vừa mở.
   */
  readonly navigate?: TurnNavigate | null;
};

/** Khách vừa chốt/chọn một mẫu → panel nhúng trang chi tiết `/vehicles/<slug>`. */
export type NavigateVehicle = {
  readonly kind: "vehicle";
  readonly vehicle_id: string;
  readonly slug: string;
  /** Đường dẫn trang thật — backend phát; thiếu thì suy /vehicles/{slug}. */
  path?: string;
  readonly name: string;
};

/** Một ghim showroom trên bản đồ panel. `showroom_id` khớp với thẻ lái thử cùng lượt. */
export type NavigateShowroom = {
  readonly showroom_id: string;
  readonly name: string;
  readonly address: string;
  readonly lat: number;
  readonly lng: number;
  readonly distance_km?: number | null;
};

/**
 * Khách xin lái thử/showroom gần → panel bản đồ. `needs_location=true` thì
 * `showrooms` rỗng và panel tự xin vị trí (cùng logic thẻ lái thử).
 */
export type NavigateMap = {
  readonly kind: "map";
  readonly vehicle_id: string;
  readonly center: { readonly lat: number; readonly lng: number } | null;
  readonly showrooms: readonly NavigateShowroom[];
  readonly needs_location: boolean;
};

export type TurnNavigate = NavigateVehicle | NavigateMap;

/** Một khoản trong bảng chi phí. `amount_vnd` là CHUỖI — tiền không đi qua float. */
export type TcoComponent = {
  readonly code: string;
  readonly label: string;
  readonly amount_vnd: string;
  /**
   * Nhóm hiển thị (Sếp 2026-08-31: giá lăn bánh với TCO là MỘT thẻ):
   * "rolling" = chi phí lăn bánh ban đầu (giá xe + lệ phí), "operating" =
   * vận hành 5 năm. Vắng/rỗng ở backend cũ — thẻ rơi về bảng phẳng như cũ.
   */
  readonly group?: string;
};

export type TcoCard = {
  readonly vehicle_id: string;
  readonly vehicle_name: string;
  readonly total_vnd: string | null;
  readonly components: readonly TcoComponent[];
  readonly daily_distance_km: number;
  /** `false` khi khách chưa nói quãng đường và hệ đang dùng mốc mặc định. */
  readonly daily_distance_known: boolean;
  readonly province_code: string | null;
  readonly region_code: string;
  readonly assumption_note: string;
  /**
   * Danh sách tỉnh GỬI KÈM thẻ. Rỗng ở backend cũ — component tự gọi
   * `/agent/tco/provinces` để bù.
   */
  readonly province_options?: readonly ProvinceOption[];
  /**
   * Công thức + đơn giá để tính lại TCO ngay TẠI CHỖ khi khách kéo thanh km —
   * không phải gọi lại `/agent/tco/estimate` cho từng nấc trượt. Rỗng/không có
   * ở backend cũ thì component rơi về đường gọi mạng cũ (`estimateTco`), thẻ
   * vẫn dùng được bình thường.
   *
   * Công thức (`src/lib/tco.ts` — `computeTco`):
   * `total = fixed + energy_vnd_per_km*km*days_per_year*years
   *        + insurance_vnd_per_year*years
   *        + floor(km*days_per_year*years / maintenance_interval_km) * maintenance_vnd_per_service
   *        + battery_vnd_per_month*12*years`
   */
  readonly rates?: TcoRates | null;
};

/** Đơn giá tính TCO tại chỗ. Mọi khoản tiền là CHUỖI số nguyên VND — cùng quy
 * ước với `TcoComponent.amount_vnd`, không đi qua float khi truyền dữ liệu. */
export type TcoRates = {
  readonly fixed_vnd: string;
  readonly energy_vnd_per_km: string;
  readonly insurance_vnd_per_year: string;
  readonly maintenance_vnd_per_service: string;
  /** Payload thật (VF 7, đợt 11) gửi dạng CHUỖI "12000" — khai đúng thực tế
   * wire để `computeTco` nhớ ép số, không so sánh kiểu ngầm. */
  readonly maintenance_interval_km: number | string;
  /** VẮNG HẲN ở xe không thuê pin (VF 7, đợt 11) — vắng nghĩa là 0 đồng,
   * `Number(undefined)` là NaN nên `computeTco` phải tự đỡ. */
  readonly battery_vnd_per_month?: string | null;
  readonly years: number;
  readonly days_per_year: number;
  /** Câu giải thích ngắn hiện dưới tổng, vd "Tính cho 5 năm, 365 ngày/năm".
   * Payload thật có thể vắng. */
  readonly formula_note?: string;
};

export type ProvinceOption = {
  readonly code: string;
  readonly name: string;
  readonly region_code: string;
};
export type PendingReview = {
  readonly review_id: string;
  readonly session_id: string;
  readonly run_id: string;
  readonly status: string;
  readonly content: string;
  readonly claimed_by: string | null;
  readonly lease_expires_at: string | null;
  readonly created_at: string;
};
export type ReviewDetail = {
  readonly review_id: string;
  readonly session_id: string;
  readonly run_id: string;
  readonly status: string;
  readonly content: string;
  readonly edited_content: string | null;
  readonly comparison_image_base64: string | null;
  /**
   * Hồ sơ khách đóng băng lúc vào hàng chờ — bằng chứng NỘI BỘ cho tư vấn viên.
   * Optional vì hàng cũ trong `review_queue` không có snapshot.
   */
  readonly profile_snapshot?: ProfileSnapshot | null;
  readonly offer_state?: OfferState | null;
  readonly matched_promotions?: readonly MatchedPromotion[];
  readonly adjustment_policies?: readonly OfferAdjustmentPolicy[];
};
export type CustomerDelivery = {
  readonly review_id: string;
  readonly content: string;
  readonly comparison_image_base64: string | null;
};
export type CustomerDeliveries = { readonly items: readonly CustomerDelivery[] };

/**
 * Đúng `ConversationResponse` của backend (`api/conversation_schemas.py`), không
 * thêm một field nào.
 *
 * Bản cũ khai thêm `session_id`, `title`, `status`, `assigned_advisor_id` —
 * **không field nào trong số đó được trả về**. Chúng chỉ là `undefined` lúc chạy
 * mà TypeScript vẫn xanh, và đó đúng là cách con bug 2026-08-26 sống sót: kiểu
 * hứa có `messages`, API không trả, `|| []` biến thiếu-field thành hội-thoại-rỗng.
 *
 * Luật rút ra: kiểu ở đây là BẢN SAO hợp đồng của backend, không phải nơi mô tả
 * dữ liệu mình mong có.
 */
export type ConversationSummary = {
  readonly conversation_id: string;
  readonly state: string;
  readonly created_at: string;
  readonly last_activity_at: string;
  readonly archived_at: string | null;
  // Các field dưới chỉ có ở `memory_routes.ConversationResponse` — route bị
  // `conversation_routes` đăng ký TRƯỚC che mất, nên thực tế `GET /conversations`
  // KHÔNG trả chúng. Giữ tuỳ chọn để `conversation-helpers` biên dịch và tự
  // rơi về `conversation_id`/`state` khi thiếu.
  readonly session_id?: string;
  readonly title?: string | null;
  readonly status?: string;
  readonly assigned_advisor_id?: string | null;
};

export type ConversationMessage = {
  readonly message_id: string;
  readonly role: "USER" | "ASSISTANT" | "ADVISOR" | string;
  readonly content: string;
  readonly client_turn_id: string | null;
  readonly created_at: string;
};

/**
 * `GET /conversations/{id}` KHÔNG trả nội dung hội thoại — nó chỉ trả đúng
 * `ConversationSummary`. Nội dung lấy ở `GET /conversations/{id}/messages`
 * (`fetchAllConversationMessages`). Chỉ endpoint của TƯ VẤN VIÊN
 * (`AdvisorConversationDetail`) mới trả kèm `messages`.
 */
export type ConversationDetail = ConversationSummary;

/* --------------------------------------------------------------------------
 * Hồ sơ khách hàng + ưu đãi (customer-profile-offer-hitl)
 *
 * Các kiểu dưới đây bám sát `src/agents/domain/customer_profile.py`,
 * `src/agents/api/schemas.py` và `src/products/domain/offer_policy.py`.
 * ------------------------------------------------------------------------ */

/** `OfferState` — ba trạng thái ưu đãi của một hồ sơ (D11). */
export type OfferState =
  | "NONE_BOTTLENECK"
  | "BOTTLENECK_NO_OFFER"
  | "BOTTLENECK_OFFER_AVAILABLE";

/** `Bottleneck` — nút thắt đọc được từ hội thoại. */
export type BottleneckCode = "PRICE" | "CHARGING" | "BATTERY" | "RANGE";

/** `PromotionType` — loại chương trình ưu đãi trong catalog. */
export type PromotionType =
  | "FIXED_DISCOUNT"
  | "PERCENT_DISCOUNT"
  | "GIFT"
  | "FINANCING"
  | "REGISTRATION_SUPPORT"
  | "OTHER";

/** Một nút thắt kèm nguyên văn câu khách nói. */
export type BottleneckEvidence = {
  readonly bottleneck: BottleneckCode;
  readonly verbatim_quote: string;
};

/**
 * Một ưu đãi khớp nút thắt. Backend đóng gói snapshot dạng `dict` nên các khoá
 * ngoài ba khoá dưới đây vẫn có thể xuất hiện — đọc bằng khoá, không destructure.
 */
export type MatchedPromotion = {
  readonly promotion_code: string;
  readonly promotion_type: PromotionType;
  readonly gift_group_unclassified?: boolean;
};

/**
 * `ProfileSnapshot` — hồ sơ đóng băng lúc lượt vào hàng chờ. Mọi field đều
 * optional ở phía đọc: hàng cũ trong `review_queue` có snapshot NULL hoặc thiếu
 * khoá, và màn duyệt không được vỡ vì chuyện đó.
 */
export type ProfileSnapshot = {
  readonly needs?: readonly string[];
  readonly considered_vehicles?: readonly string[];
  readonly bottlenecks?: readonly BottleneckEvidence[];
  readonly matched_promotions?: readonly MatchedPromotion[];
  readonly verified_number_tokens?: readonly string[];
  readonly offer_state?: OfferState | null;
  readonly unmet_demand_flag?: boolean;
  readonly unmet_bottleneck?: string | null;
  readonly color_preference?: string | null;
};

/**
 * `OfferAdjustmentPolicy` — biên độ ADMIN cấu hình cho một `promotion_type`.
 * Các trường phần trăm là `Decimal` phía backend, `model_dump(mode="json")` trả
 * về chuỗi, nên kiểu ở đây nhận cả chuỗi lẫn số.
 */
export type OfferAdjustmentPolicy = {
  readonly promotion_type: PromotionType;
  readonly adjust_min_vnd?: number | null;
  readonly adjust_max_vnd?: number | null;
  readonly adjust_min_percent?: number | string | null;
  readonly adjust_max_percent?: number | string | null;
  readonly financing_months_min?: number | null;
  readonly financing_months_max?: number | null;
  readonly financing_support_max_vnd?: number | null;
  readonly gift_value_max_vnd?: number | null;
  readonly allowed_gift_codes?: readonly string[] | null;
  readonly registration_support_max_vnd?: number | null;
  readonly other_max_vnd?: number | null;
};

/** `QueueEntryResponse` — một dòng hàng đợi cho màn tư vấn viên. */
export type QueueEntry = {
  readonly review_id: string;
  readonly session_id: string;
  readonly run_id: string;
  readonly status: string;
  readonly content: string;
  readonly claimed_by: string | null;
  readonly lease_expires_at: string | null;
  readonly created_at: string;
  readonly profile_snapshot: ProfileSnapshot | null;
  readonly offer_state: OfferState | null;
  readonly age_minutes: number | null;
  readonly handoff_requested: boolean;
  readonly offer_suggestion_ignored: boolean;
};

/** Trạng thái lọc của `GET /agent/reviews`. */
export type ReviewQueueStatus = "pending" | "approved" | "rejected";

/** `OfferAdjustmentRequest` — một lần cấp/điều chỉnh ưu đãi. */
export type OfferAdjustment = {
  readonly promotion_code?: string | null;
  readonly promotion_type?: PromotionType | null;
  readonly adjustment_type?: string | null;
  readonly amount_vnd?: number | null;
  readonly percent?: number | null;
  readonly months?: number | null;
  readonly gift_code?: string | null;
  readonly old_value?: string | null;
  readonly new_value?: string | null;
  readonly reason?: string | null;
};

/**
 * `ResolveReviewRequest` — duyệt/từ chối kèm TUỲ CHỌN cấp ưu đãi và cờ chuyển
 * người thật. Bỏ trống `offer_adjustment` là đường đi hợp lệ (D12).
 */
export type ResolveReviewInput = {
  readonly status: "APPROVED" | "REJECTED";
  readonly edited_content?: string | null;
  readonly offer_adjustment?: OfferAdjustment | null;
  readonly handoff_requested?: boolean;
};

export type BottleneckSignalStatus = "PENDING" | "CORRECT" | "INCORRECT";
export type BottleneckSignalVerdict = "CORRECT" | "INCORRECT";
export type BottleneckSignalQueueStatus = "pending" | "correct" | "incorrect";

export type BottleneckSignal = {
  readonly signal_id: string;
  readonly session_id: string;
  readonly client_turn_id: string;
  readonly anchor_client_turn_id: string;
  readonly label: string;
  readonly evidence_quote: string;
  readonly status: BottleneckSignalStatus;
  readonly claimed_by: string | null;
  readonly claimed_at: string | null;
  readonly lease_expires_at: string | null;
  readonly advisor_id: string | null;
  readonly decided_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
};

export type BottleneckSignalDetail = BottleneckSignal & {
  readonly matched_promotions: readonly MatchedPromotion[];
  readonly adjustment_policies: readonly OfferAdjustmentPolicy[];
};

/** `SalesOpportunityResponse` — một dòng màn Cơ hội bán hàng. */
export type SalesOpportunity = {
  readonly session_id: string;
  readonly customer_id: string;
  readonly bottlenecks: readonly string[];
  readonly snapshot: ProfileSnapshot;
  readonly last_active_at: string;
};

/** Một showroom trong thẻ chọn lịch lái thử. */
export type TestDriveShowroom = {
  readonly showroom_id: string;
  readonly name: string;
  readonly address: string;
  readonly distance_label: string;
};

/** Một ô giờ trong cột giờ dùng chung. */
export type TestDriveTime = {
  readonly scheduled_at: string;
  readonly label: string;
};

/** Một ngày và các ô giờ của nó — hợp của mọi showroom trong thẻ. */
export type TestDriveDay = {
  readonly date: string;
  readonly label: string;
  readonly times: readonly TestDriveTime[];
};

/**
 * Một ô CÒN CHỖ, kèm mã nút do backend sinh.
 *
 * Ô vắng mặt ở đây là ô phải làm mờ — client KHÔNG tự suy ra chỗ trống từ đâu
 * khác: đặt nhầm một khung đã đầy là hẹn hai khách vào cùng một giờ.
 */
export type TestDriveOption = {
  readonly showroom_id: string;
  readonly scheduled_at: string;
  readonly value: string;
};

/**
 * Thẻ chọn showroom + khung giờ lái thử.
 *
 * `needs_location=true` (hợp đồng đợt 8, 2026-08-30): lõi nhận ý định lái thử
 * mà CHƯA có vị trí — thẻ tới với `showrooms/days/options` rỗng, và chính thẻ
 * xin vị trí (GPS hoặc gõ quận/huyện) rồi gọi `/agent/test-drive/options` để
 * tự thay mình bằng thẻ đủ showroom/giờ. KHÔNG có lượt hỏi tỉnh bằng chữ nữa.
 */
export type TestDriveCard = {
  readonly vehicle_id: string;
  readonly vehicle_name: string;
  readonly needs_location?: boolean;
  readonly showrooms: readonly TestDriveShowroom[];
  readonly days: readonly TestDriveDay[];
  readonly options: readonly TestDriveOption[];
  readonly default_showroom_id: string;
  readonly default_date: string;
};

/** Một tính năng đã xác minh. Không có `evidence_id`: dấu vết nguồn giữ nội bộ. */
/** Một nhóm thông số. Nhóm không có dòng nào thì backend KHÔNG gửi. */
export type SpecGroup = {
  readonly title: string;
  readonly rows: readonly (readonly [string, string])[];
};

export type VehicleDetails = {
  readonly vehicle_name: string;
  readonly spec_groups: readonly SpecGroup[];
};

/** Trả về của `POST /agent/test-drive/options`: thẻ đủ showroom/giờ thay tại chỗ. */
export type TestDriveOptionsResponse = {
  readonly test_drive_card: TestDriveCard;
  readonly quick_replies?: readonly QuickReply[];
  /** "Chưa tìm thấy showroom quanh đây" — 200 với `showrooms=[]`. */
  readonly message?: string | null;
  /**
   * Bản đồ đi kèm thẻ mới (toạ độ showroom). Tuỳ chọn: backend cũ không gửi thì
   * panel bản đồ chỉ có vị trí khách, không có ghim — thẻ lái thử vẫn đủ dùng.
   */
  readonly navigate?: TurnNavigate | null;
};

/** Ô giờ còn trống của một ngày, nạp riêng khi khách bấm sang ngày khác. */
export type TestDriveAvailability = {
  readonly date: string;
  readonly options: readonly TestDriveOption[];
};
