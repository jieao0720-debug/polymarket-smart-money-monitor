// `injected` comes from @wagmi/core directly: the `wagmi/connectors` barrel pulls the
// whole WalletConnect dependency tree into the dev-server module graph, whose storage
// layer mistakes Node's experimental global localStorage for a browser (SSR crash).
import { injected } from "@wagmi/core";
import { cookieStorage, createConfig, createStorage, http } from "wagmi";
import { polygon } from "wagmi/chains";

/**
 * Wallet config: injected browser wallets only (MetaMask etc.), Polygon mainnet.
 * The app only ever requests addresses and EIP-712 signatures — it never asks for,
 * stores, or transmits private keys (development-rules.md #2).
 *
 * cookieStorage (wagmi's recommended SSR setup) holds only public connection state
 * (connector id / last connected address) — never credentials. It also keeps SSR off
 * localStorage, which is unavailable server-side.
 */
export const wagmiConfig = createConfig({
  chains: [polygon],
  connectors: [injected()],
  storage: createStorage({ storage: cookieStorage }),
  transports: { [polygon.id]: http() },
  ssr: true,
});

export const POLYGON_CHAIN_ID = polygon.id; // 137
