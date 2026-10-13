import { QueryClient, queryOptions } from "@tanstack/react-query";
import { productionAPI } from "../production";
import { serverLibrary } from "../library";

export const workbenchKeys = {
  all: ["workbench"] as const,
  characters: ["workbench", "characters"] as const,
  snapshot: (id: string) => ["workbench", "snapshot", id] as const,
  capabilities: ["workbench", "capabilities"] as const,
  presets: ["workbench", "presets"] as const,
  promptSettings: ["workbench", "prompt-settings"] as const,
};

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: true },
      // An uncertain write must be reconciled using the persisted request key.
      mutations: { retry: false },
    },
  });
}

export function createWorkbenchQueries(
  api = productionAPI,
  library = serverLibrary,
) {
  return {
    characters: () =>
      queryOptions({
        queryKey: workbenchKeys.characters,
        queryFn: ({ signal }) => library.characters(signal),
        staleTime: 30_000,
      }),
    snapshot: (id: string) =>
      queryOptions({
        queryKey: workbenchKeys.snapshot(id),
        queryFn: ({ signal }) => api.snapshot(id, signal),
        enabled: Boolean(id),
        refetchInterval: 5_000,
      }),
    capabilities: () =>
      queryOptions({
        queryKey: workbenchKeys.capabilities,
        queryFn: ({ signal }) => api.capabilities(signal),
        refetchInterval: 5_000,
      }),
    presets: () =>
      queryOptions({
        queryKey: workbenchKeys.presets,
        queryFn: ({ signal }) => api.presets(signal),
        staleTime: 5 * 60_000,
        refetchInterval: (query) =>
          query.state.status === "error" ? 15_000 : false,
      }),
    promptSettings: () =>
      queryOptions({
        queryKey: workbenchKeys.promptSettings,
        queryFn: ({ signal }) => api.promptSettings(signal),
        staleTime: Infinity,
      }),
  };
}

export const workbenchQueries = createWorkbenchQueries();
