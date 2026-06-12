/**
 * Polymarket CLOB order construction + EIP-712 typed-data helpers.
 *
 * The order struct/domain follow the official CTF Exchange contracts; the signature
 * is produced by the USER'S WALLET via wagmi signTypedData — no key material ever
 * touches this app. v1 supports EOA wallets only (signatureType=0, ASSUMPTION-A11)
 * and BUY orders only (ASSUMPTION-A12). UNCERTAINTY-U10: this path is gated behind
 * ENABLE_LIVE_TRADING and has not been exercised against production CLOB.
 */
import type { TypedDataDomain } from "viem";

export const CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E" as const;
export const NEG_RISK_CTF_EXCHANGE = "0xC5d563A36AE78145C45a50134d48A1215220f80a" as const;
export const ZERO_ADDRESS = "0x0000000000000000000000000000000000000000" as const;
const USDC_DECIMALS = 6;

export const ORDER_TYPES = {
  Order: [
    { name: "salt", type: "uint256" },
    { name: "maker", type: "address" },
    { name: "signer", type: "address" },
    { name: "taker", type: "address" },
    { name: "tokenId", type: "uint256" },
    { name: "makerAmount", type: "uint256" },
    { name: "takerAmount", type: "uint256" },
    { name: "expiration", type: "uint256" },
    { name: "nonce", type: "uint256" },
    { name: "feeRateBps", type: "uint256" },
    { name: "side", type: "uint8" },
    { name: "signatureType", type: "uint8" },
  ],
} as const;

export const CLOB_AUTH_TYPES = {
  ClobAuth: [
    { name: "address", type: "address" },
    { name: "timestamp", type: "string" },
    { name: "nonce", type: "uint256" },
    { name: "message", type: "string" },
  ],
} as const;

export const CLOB_AUTH_MESSAGE = "This message attests that I control the given wallet";

export interface BuiltOrder {
  salt: string;
  maker: `0x${string}`;
  signer: `0x${string}`;
  taker: `0x${string}`;
  tokenId: string;
  makerAmount: string;
  takerAmount: string;
  expiration: string;
  nonce: string;
  feeRateBps: string;
  side: "BUY";
  signatureType: number;
}

function randomSalt(): string {
  const bytes = new Uint8Array(8);
  crypto.getRandomValues(bytes);
  let value = 0n;
  for (const b of bytes) value = (value << 8n) | BigInt(b);
  return value.toString();
}

/**
 * Build a BUY order: spend up to `notional` USDC for outcome tokens at `limitPrice`.
 * makerAmount = USDC paid (6dp), takerAmount = outcome shares received (6dp);
 * shares are floored to 2dp so price = maker/taker stays ≥ the signed limit.
 */
export function buildBuyOrder(params: {
  maker: `0x${string}`;
  tokenId: string;
  limitPrice: number;
  notional: number;
}): BuiltOrder {
  const { maker, tokenId, limitPrice, notional } = params;
  if (!(limitPrice > 0 && limitPrice < 1)) throw new Error("limit price must be in (0, 1)");
  if (!(notional > 0)) throw new Error("notional must be positive");
  const shares = Math.floor((notional / limitPrice) * 100) / 100;
  const takerAmount = BigInt(Math.round(shares * 10 ** USDC_DECIMALS));
  const makerAmount = BigInt(Math.round(shares * limitPrice * 10 ** USDC_DECIMALS));
  return {
    salt: randomSalt(),
    maker,
    signer: maker,
    taker: ZERO_ADDRESS,
    tokenId,
    makerAmount: makerAmount.toString(),
    takerAmount: takerAmount.toString(),
    expiration: "0",
    nonce: "0",
    feeRateBps: "0",
    side: "BUY",
    signatureType: 0, // EOA
  };
}

export function orderDomain(negRisk: boolean): TypedDataDomain {
  return {
    name: "Polymarket CTF Exchange",
    version: "1",
    chainId: 137,
    verifyingContract: negRisk ? NEG_RISK_CTF_EXCHANGE : CTF_EXCHANGE,
  };
}

/** Typed-data message for wallet signing (side/signatureType as integers per contract). */
export function orderTypedMessage(order: BuiltOrder) {
  return {
    salt: BigInt(order.salt),
    maker: order.maker,
    signer: order.signer,
    taker: order.taker,
    tokenId: BigInt(order.tokenId),
    makerAmount: BigInt(order.makerAmount),
    takerAmount: BigInt(order.takerAmount),
    expiration: BigInt(order.expiration),
    nonce: BigInt(order.nonce),
    feeRateBps: BigInt(order.feeRateBps),
    side: 0, // BUY
    signatureType: order.signatureType,
  };
}

export function clobAuthTypedData(address: `0x${string}`, timestamp: number, nonce = 0) {
  return {
    domain: { name: "ClobAuthDomain", version: "1", chainId: 137 } as TypedDataDomain,
    types: CLOB_AUTH_TYPES,
    primaryType: "ClobAuth" as const,
    message: {
      address,
      timestamp: String(timestamp),
      nonce: BigInt(nonce),
      message: CLOB_AUTH_MESSAGE,
    },
  };
}
