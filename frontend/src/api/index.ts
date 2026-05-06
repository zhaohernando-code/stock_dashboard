import { getApiBase, getBetaAccessKey, getRuntimeConfig, getActAsLogin, setActAsLogin } from "./core";
import { getAuthContext } from "./auth";
import {
  acceptImprovementSuggestionForPlan,
  getImprovementSuggestionDetails,
  getImprovementSuggestionSummary,
  loadShellData,
  getStockDashboard,
  getOperationsDashboard,
  getOperationsDetails,
  getOperationsSummary,
  getScheduledRefreshStatus,
  runImprovementSuggestionReview,
  updateImprovementSuggestionStatus,
} from "./dashboard";
import { addWatchlist, refreshWatchlist, removeWatchlist } from "./watchlist";
import {
  getSimulationWorkspace, updateSimulationConfig, startSimulation,
  pauseSimulation, resumeSimulation, stepSimulation, restartSimulation,
  endSimulation, submitManualSimulationOrder,
} from "./simulation";
import {
  getRuntimeSettings, getRuntimeOverview, upsertProviderCredential, createModelApiKey,
  updateModelApiKey, setDefaultModelApiKey, deleteModelApiKey,
} from "./settings";
import {
  createManualResearchRequest, listManualResearchRequests,
  getManualResearchRequest, executeManualResearchRequest,
  completeManualResearchRequest, failManualResearchRequest,
  retryManualResearchRequest, runFollowUpAnalysis,
} from "./manual-research";
import {
  createShortpickRun,
  getShortpickCandidate,
  getShortpickCandidates,
  getShortpickModelFeedback,
  getShortpickRun,
  getShortpickRuns,
  getShortpickValidationQueue,
  retryShortpickFailedRounds,
  validateShortpickRun,
} from "./shortpick";

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
  getAuthContext,
  getActAsLogin,
  setActAsLogin,
  loadShellData,
  addWatchlist,
  refreshWatchlist,
  removeWatchlist,
  getStockDashboard,
  getOperationsDashboard,
  getOperationsSummary,
  getOperationsDetails,
  getScheduledRefreshStatus,
  getImprovementSuggestionSummary,
  getImprovementSuggestionDetails,
  runImprovementSuggestionReview,
  acceptImprovementSuggestionForPlan,
  updateImprovementSuggestionStatus,
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
  getRuntimeOverview,
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
  getShortpickRuns,
  getShortpickRun,
  createShortpickRun,
  validateShortpickRun,
  retryShortpickFailedRounds,
  getShortpickCandidates,
  getShortpickCandidate,
  getShortpickValidationQueue,
  getShortpickModelFeedback,
};
