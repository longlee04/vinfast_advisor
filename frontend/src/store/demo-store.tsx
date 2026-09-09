"use client";

import { createContext, useContext, useMemo, useState } from "react";

import { initialAdvisorQueue } from "@/mocks/advisor-queue";
import type {
  AdvisorQueueItem,
  BookingStatus,
  CustomerNeedProfile,
  DemoRole,
  DemoState,
  PreviewState,
} from "@/types/demo";

const INITIAL_PROFILE: CustomerNeedProfile = { priorities: [] };

const INITIAL_STATE: DemoState = {
  activeRole: "customer",
  consultationStep: 0,
  needProfile: INITIAL_PROFILE,
  recommendationStatus: "not_started",
  recommendationPreview: "default",
  selectedVehicleIds: [],
  bookingStatus: "idle",
  advisorQueue: initialAdvisorQueue,
  editedRecommendationText:
    "VF 6 Plus là lựa chọn cân bằng cho gia đình 5 người, phù hợp ngân sách và nhu cầu di chuyển hàng ngày.",
};

type ReviewAction = "approved" | "edited" | "rejected";

type DemoStore = {
  state: DemoState;
  setActiveRole: (role: DemoRole) => void;
  startConsultation: () => void;
  answerNeed: (answer: Partial<CustomerNeedProfile>) => void;
  goToConsultationStep: (step: number) => void;
  completeConsultation: () => void;
  simulateAdvisorApproval: () => void;
  setRecommendationPreview: (preview: PreviewState) => void;
  toggleSelectedVehicle: (vehicleId: string) => void;
  setBookingStatus: (status: BookingStatus) => void;
  resetDemo: () => void;
};

const DemoContext = createContext<DemoStore | null>(null);

function updateQueueItem(items: AdvisorQueueItem[], reviewId: string, action: ReviewAction): AdvisorQueueItem[] {
  return items.map((item) => (item.id === reviewId ? { ...item, status: action } : item));
}

export function DemoStoreProvider({ children }: Readonly<{ children: React.ReactNode }>) {
  const [state, setState] = useState<DemoState>(INITIAL_STATE);

  const store = useMemo<DemoStore>(
    () => ({
      state,
      setActiveRole: (activeRole) => setState((current) => ({ ...current, activeRole })),
      startConsultation: () =>
        setState((current) => ({
          ...current,
          consultationStep: 0,
          needProfile: { priorities: [] },
          recommendationStatus: "collecting",
          recommendationPreview: "default",
        })),
      answerNeed: (answer) =>
        setState((current) => ({
          ...current,
          needProfile: { ...current.needProfile, ...answer },
          consultationStep: current.consultationStep + 1,
          recommendationStatus: "collecting",
        })),
      goToConsultationStep: (consultationStep) => setState((current) => ({ ...current, consultationStep })),
      completeConsultation: () => setState((current) => ({ ...current, recommendationStatus: "pending" })),
      simulateAdvisorApproval: () =>
        setState((current) => ({
          ...current,
          recommendationStatus: "approved",
          advisorQueue: updateQueueItem(current.advisorQueue, "review-0182", "approved"),
        })),
      setRecommendationPreview: (recommendationPreview) =>
        setState((current) => ({ ...current, recommendationPreview })),
      toggleSelectedVehicle: (vehicleId) =>
        setState((current) => {
          const selected = current.selectedVehicleIds.includes(vehicleId);
          const selectedVehicleIds = selected
            ? current.selectedVehicleIds.filter((id) => id !== vehicleId)
            : [...current.selectedVehicleIds, vehicleId].slice(-3);
          return { ...current, selectedVehicleIds };
        }),
      setBookingStatus: (bookingStatus) => setState((current) => ({ ...current, bookingStatus })),
      resetDemo: () => setState({ ...INITIAL_STATE, advisorQueue: initialAdvisorQueue.map((item) => ({ ...item })) }),
    }),
    [state],
  );

  return <DemoContext.Provider value={store}>{children}</DemoContext.Provider>;
}

export function useDemoStore(): DemoStore {
  const context = useContext(DemoContext);
  if (!context) {
    throw new Error("useDemoStore must be used inside DemoStoreProvider");
  }
  return context;
}
