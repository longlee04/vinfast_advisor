export type DemoRole = "customer" | "advisor" | "admin";

export type VehicleType = "car" | "electric_motorbike";

export type RecommendationStatus =
  | "not_started"
  | "collecting"
  | "generating"
  | "pending"
  | "approved"
  | "edited"
  | "rejected";

export type PreviewState = "default" | "loading" | "empty" | "error";

export type BookingStatus = "idle" | "submitting" | "success" | "conflict" | "error";

export type CustomerNeedProfile = {
  vehicleType?: VehicleType;
  passengerCount?: number;
  electricMotorbikeUse?: "commuting" | "delivery" | "personal";
  monthlyDistanceKm?: number;
  homeChargingAccess?: boolean | "unknown";
  budgetMaxVnd?: number;
  primaryUse?: "family" | "personal" | "business" | "mixed";
  priorities: string[];
};

export type Vehicle = {
  id: string;
  modelName: string;
  variant: string;
  vehicleType: VehicleType;
  priceVnd: number;
  rangeKm: number;
  seats?: number;
  chargeMinutes: number;
  warranty: string;
  dimensions: string;
  strongestAdvantage: string;
  tradeoff: string;
  bestFor: string;
  assetStatus: "authorized" | "missing";
  posterPath?: string;
  modelPath?: string;
  availableColors: { id: string; name: string; hex: string }[];
};

export type VehicleRecommendation = {
  id: string;
  vehicleId: string;
  rank: number;
  reasons: string[];
  tradeoff: string;
  sourceLabels: string[];
  advisorReviewed: boolean;
};

export type AdvisorQueueItem = {
  id: string;
  customerName: string;
  customerEmail: string;
  proposedVehicleIds: string[];
  submittedAt: string;
  priority: "normal" | "high";
  status: "pending" | "approved" | "edited" | "rejected";
  generatedAt: string;
  warningLabels: string[];
};

export type Showroom = {
  id: string;
  name: string;
  address: string;
  city: string;
};

export type DemoBooking = {
  vehicleId: string;
  showroomId: string;
  date: string;
  timeSlot: string;
  fullName: string;
  phone: string;
};

export type AdminMetric = {
  label: string;
  value: string;
  change: string;
};

export type InternalNotice = {
  id: string;
  title: string;
  priority: "normal" | "high";
  createdAt: string;
  readCount: number;
  audienceCount: number;
};

export type CustomerRecord = {
  id: string;
  name: string;
  email: string;
  phone: string;
  assignedAdvisor: string;
  needSummary: string;
  lastActivity: string;
  sessions: number;
  status: "new" | "consulting" | "test_drive";
};

export type DemoUser = {
  id: string;
  name: string;
  email: string;
  role: DemoRole;
  status: "active" | "invited" | "locked";
  lastSeen: string;
};

export type DemoState = {
  activeRole: DemoRole;
  consultationStep: number;
  needProfile: CustomerNeedProfile;
  recommendationStatus: RecommendationStatus;
  recommendationPreview: PreviewState;
  selectedVehicleIds: string[];
  bookingStatus: BookingStatus;
  advisorQueue: AdvisorQueueItem[];
  editedRecommendationText: string;
};
