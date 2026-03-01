/**
 * workspaceStore — central Zustand store for the Model Workspace.
 * Single source of truth for plan, intelligence, cost, time, conversation, versions.
 */

import { create } from "zustand";
import type { MachiningPlan } from "@/types/machining";
import type {
  CostBreakdown,
  TimeBreakdown,
  SpatialOperationMap,
  ConversationMessage,
  VersionInfo,
  StrategyVariant,
  RiskItem,
  ProcessingStage,
} from "@/types/intelligence";

// ─── State Shape ─────────────────────────────────────────────────────────────

export interface WorkspaceState {
  // Core identifiers
  modelId: string | null;
  modelName: string;
  gltfUrl: string | null;

  // Plan data
  plan: MachiningPlan | null;
  selectedStrategy: string;
  strategies: StrategyVariant[];
  risks: RiskItem[];

  // Intelligence data
  cost: CostBreakdown | null;
  time: TimeBreakdown | null;
  spatialMap: SpatialOperationMap | null;

  // Conversation
  conversationHistory: ConversationMessage[];

  // Version history
  versionHistory: VersionInfo[];

  // UI state
  selectedOperationId: string | null;
  selectedFeatureId: string | null;
  selectedSetupIndex: number;
  processingStage: ProcessingStage;
  error: string | null;

  // Actions
  setModelId: (id: string) => void;
  setModelName: (name: string) => void;
  setGltfUrl: (url: string | null) => void;
  setPlan: (plan: MachiningPlan | null) => void;
  setSelectedStrategy: (strategy: string) => void;
  setStrategies: (strategies: StrategyVariant[]) => void;
  setRisks: (risks: RiskItem[]) => void;
  setCost: (cost: CostBreakdown | null) => void;
  setTime: (time: TimeBreakdown | null) => void;
  setSpatialMap: (map: SpatialOperationMap | null) => void;
  addMessage: (message: ConversationMessage) => void;
  clearConversation: () => void;
  setVersionHistory: (versions: VersionInfo[]) => void;
  selectOperation: (id: string | null) => void;
  selectFeature: (id: string | null) => void;
  selectSetup: (index: number) => void;
  setProcessingStage: (stage: ProcessingStage) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

// ─── Initial State ───────────────────────────────────────────────────────────

const initialState = {
  modelId: null as string | null,
  modelName: "",
  gltfUrl: null as string | null,
  plan: null as MachiningPlan | null,
  selectedStrategy: "CONSERVATIVE",
  strategies: [] as StrategyVariant[],
  risks: [] as RiskItem[],
  cost: null as CostBreakdown | null,
  time: null as TimeBreakdown | null,
  spatialMap: null as SpatialOperationMap | null,
  conversationHistory: [] as ConversationMessage[],
  versionHistory: [] as VersionInfo[],
  selectedOperationId: null as string | null,
  selectedFeatureId: null as string | null,
  selectedSetupIndex: 0,
  processingStage: "idle" as ProcessingStage,
  error: null as string | null,
};

// ─── Store ───────────────────────────────────────────────────────────────────

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  ...initialState,

  setModelId: (id) => set({ modelId: id }),
  setModelName: (name) => set({ modelName: name }),
  setGltfUrl: (url) => set({ gltfUrl: url }),
  setPlan: (plan) => set({ plan }),
  setSelectedStrategy: (strategy) => set({ selectedStrategy: strategy }),
  setStrategies: (strategies) => set({ strategies }),
  setRisks: (risks) => set({ risks }),
  setCost: (cost) => set({ cost }),
  setTime: (time) => set({ time }),
  setSpatialMap: (map) => set({ spatialMap: map }),

  addMessage: (message) =>
    set((state) => ({
      conversationHistory: [...state.conversationHistory, message],
    })),

  clearConversation: () => set({ conversationHistory: [] }),

  setVersionHistory: (versions) => set({ versionHistory: versions }),

  selectOperation: (id) =>
    set({ selectedOperationId: id }),

  selectFeature: (id) =>
    set({ selectedFeatureId: id }),

  selectSetup: (index) => set({ selectedSetupIndex: index }),

  setProcessingStage: (stage) => set({ processingStage: stage }),
  setError: (error) => set({ error }),

  reset: () => set(initialState),
}));
