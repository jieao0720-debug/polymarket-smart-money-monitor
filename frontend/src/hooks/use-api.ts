"use client";

/** react-query hooks over the api-client — single data-access layer for pages. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";

export function useHotMarkets(params: Parameters<typeof api.hotMarkets>[0] = {}) {
  return useQuery({
    queryKey: ["hot-markets", params],
    queryFn: () => api.hotMarkets(params),
  });
}

export function useMarketAnalysis(marketId: string, refresh = false) {
  return useQuery({
    queryKey: ["market-analysis", marketId, refresh],
    queryFn: () => api.marketAnalysis(marketId, refresh),
    enabled: !!marketId,
  });
}

export function useAccountProfile(address: string | null, marketId?: string) {
  return useQuery({
    queryKey: ["account-profile", address, marketId],
    queryFn: () => api.accountProfile(address!, marketId),
    enabled: !!address,
  });
}

export function useSignals(params: Parameters<typeof api.signals>[0] = {}) {
  return useQuery({ queryKey: ["signals", params], queryFn: () => api.signals(params) });
}

export function usePaperTrades() {
  return useQuery({ queryKey: ["paper-trades"], queryFn: () => api.paperTrades() });
}

export function useScannerLatest(pollMs: number | false = 4000) {
  return useQuery({
    queryKey: ["scanner-latest"],
    queryFn: () => api.scannerLatest(),
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 2000 : pollMs,
  });
}

export function useRunScanner() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.runScanner(),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["scanner-latest"] }),
  });
}

export function useGeoblock(walletAddress?: string) {
  return useQuery({
    queryKey: ["geoblock", walletAddress ?? "anon"],
    queryFn: () => api.geoblock(walletAddress),
    staleTime: 60_000,
  });
}

export function useBalances(walletAddress: string | undefined) {
  return useQuery({
    queryKey: ["balances", walletAddress],
    queryFn: () => api.balances(walletAddress!),
    enabled: !!walletAddress,
  });
}

export function useAllowance(walletAddress: string | undefined) {
  return useQuery({
    queryKey: ["allowance", walletAddress],
    queryFn: () => api.allowance(walletAddress!),
    enabled: !!walletAddress,
  });
}

export function usePublicSettings() {
  return useQuery({
    queryKey: ["public-settings"],
    queryFn: () => api.publicSettings(),
    staleTime: 5 * 60_000,
  });
}

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: () => api.health(), staleTime: 30_000 });
}
