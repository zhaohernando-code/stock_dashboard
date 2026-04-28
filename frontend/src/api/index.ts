import { getApiBase, getBetaAccessKey, getRuntimeConfig } from "./core";
import { loadShellData, getStockDashboard, getOperationsDashboard } from "./dashboard";
import { addWatchlist, refreshWatchlist, removeWatchlist } from "./watchlist";
import {
  getSimulationWorkspace, updateSimulationConfig, startSimulation,
  pauseSimulation, resumeSimulation, stepSimulation, restartSimulation,
  endSimulation, submitManualSimulationOrder,
} from "./simulation";
import {
  getRuntimeSettings, upsertProviderCredential, createModelApiKey,
  updateModelApiKey, setDefaultModelApiKey, deleteModelApiKey,
} from "./settings";
import {
  createManualResearchRequest, listManualResearchRequests,
  getManualResearchRequest, executeManualResearchRequest,
  completeManualResearchRequest, failManualResearchRequest,
  retryManualResearchRequest, runFollowUpAnalysis,
} from "./manual-research";

export const api = {
  getApiBase,
  getBetaAccessKey,
  setBetaAccessKey: (value: string) => {
    const trimmed = value.trim();
    if (trimmed) {
      window.localStorage.setItem("ashare-beta-access-key", trimmed);
    } else {
      window.localStorage.removeItem("ashare-beta-access-key");
    }
  },
  getRuntimeConfig,
  loadShellData,
  addWatchlist,
  refreshWatchlist,
  removeWatchlist,
  getStockDashboard,
  getOperationsDashboard,
  getSimulationWorkspace,
  updateSimulationConfig,
  startSimulation,
  pauseSimulation,
  resumeSimulation,
  stepSimulation,
  restartSimulation,
  endSimulation,
  submitManualSimulationOrder,
  getRuntimeSettings,
  upsertProviderCredential,
  createModelApiKey,
  updateModelApiKey,
  setDefaultModelApiKey,
  deleteModelApiKey,
  createManualResearchRequest,
  listManualResearchRequests,
  getManualResearchRequest,
  executeManualResearchRequest,
  completeManualResearchRequest,
  failManualResearchRequest,
  retryManualResearchRequest,
  runFollowUpAnalysis,
};
