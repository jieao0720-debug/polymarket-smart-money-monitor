"use client";

/**
 * Lightweight homegrown i18n (EN / 简体中文) — no route locales, no extra deps.
 *
 * - The locale preference lives in a cookie (`pm_locale`) so the server layout can
 *   render the correct language on first paint (no hydration flash). It is a UI
 *   preference only — never sensitive data.
 * - `en` is the source of truth; `zh` is type-checked to cover every key.
 * - Components work without a provider (default = en), so unit tests that assert
 *   the mandated English safety strings keep passing.
 * - Market questions/categories come from Polymarket data and are not translated.
 */
import * as React from "react";
import { LOCALE_COOKIE, parseLocale, type Locale } from "./locale";

export { LOCALE_COOKIE, parseLocale };
export type { Locale };

const en = {
  // ---------------------------------------------------------------- nav / shell
  "nav.brand": "Polymarket",
  "nav.brandSub": "Smart Money Monitor",
  "nav.dashboard": "Dashboard",
  "nav.signals": "Signals",
  "nav.paperTrading": "Paper Trading",
  "nav.walletTrading": "Wallet / Trading",
  "nav.settings": "Settings",
  "nav.disclaimer":
    "Analysis signals only. Not financial advice. Paper trading by default — live trading is disabled unless explicitly enabled server-side.",

  // ---------------------------------------------------------------- common
  "common.failedToLoad": "Failed to load data",
  "common.retry": "Retry",
  "common.noData": "No data yet",
  "common.neutral": "Neutral",
  "common.copyAddress": "Copy address",
  "common.confidenceTooltip":
    "Analysis confidence (heuristic ranking aid — NOT a win probability)",
  "common.signalDisclaimer":
    "Analysis signal — heuristic, rule-based ranking of observed positioning. Not financial advice, not a win probability, and historic stats do not predict future results.",

  // account labels
  "labels.HIGH_WIN_RATE": "High win rate",
  "labels.ABNORMAL_POSITION": "Abnormal position",
  "labels.NEW_ACCOUNT": "New account",
  "labels.OTHER": "Other",

  // risk flags
  "flags.LOW_LIQUIDITY": "low liquidity",
  "flags.WIDE_SPREAD": "wide spread",
  "flags.NEAR_RESOLUTION": "near resolution",
  "flags.EXTREME_PRICE": "extreme price",
  "flags.LOW_SMART_SAMPLE": "low smart sample",
  "flags.NEW_ACCOUNT_HEAVY": "new account heavy",
  "flags.ONE_SIDED_BOOK": "one sided book",
  "flags.PARTIAL_DATA": "partial data",

  // ---------------------------------------------------------------- dashboard
  "dash.title": "Hot Markets",
  "dash.runScanner": "Run Scanner",
  "dash.scanning": "Scanning…",
  "dash.refresh": "Refresh",
  "dash.notRunYet": "Scanner has not run yet",
  "dash.lastScan": "Last scan: {status} · {analyzed} analyzed · {signals} signals",
  "dash.errors": "{n} errors",
  "dash.scanCount": "{analyzed}/{found} markets",
  "dash.allCategories": "All categories",
  "dash.anyDirection": "Any direction",
  "dash.anyConfidence": "Any confidence",
  "dash.confGte": "Confidence ≥ {n}",
  "dash.anyLiquidity": "Any liquidity",
  "dash.liqGte": "Liquidity ≥ ${n}",
  "dash.exclude": "Exclude:",
  "dash.excludeTooltip": "Hide markets flagged {flag}",
  "dash.thMarket": "Market",
  "dash.thCategory": "Category",
  "dash.thYes": "Yes",
  "dash.thNo": "No",
  "dash.thSpread": "Spread",
  "dash.thVol": "24h Vol",
  "dash.thLiquidity": "Liquidity",
  "dash.thOi": "OI*",
  "dash.oiTooltip": "Event-level open interest (see data notes)",
  "dash.thSmart": "Smart $",
  "dash.thConf": "Conf.",
  "dash.thRiskFlags": "Risk flags",
  "dash.analyzedAt": "analyzed {time}",
  "dash.emptyHint":
    'No analyzed markets yet. Click "Run Scanner" to scan Polymarket hot markets.',

  // ---------------------------------------------------------------- market detail
  "market.reanalyze": "Re-analyze",
  "market.reanalyzing": "Re-analyzing…",
  "market.generateTicket": "Generate trade ticket",
  "market.ends": "ends {time}",
  "market.active": "active",
  "market.inactiveClosed": "inactive/closed",
  "market.notAccepting": "not accepting orders",
  "market.analyzedAt": "analyzed {time}",
  "market.statYes": "YES price",
  "market.statNo": "NO price",
  "market.statSpread": "Spread",
  "market.statLiquidity": "Liquidity",
  "market.statVol": "24h volume",
  "market.statOi": "Open interest",
  "market.eventLevel": "event-level",
  "market.summaryTitle": "Smart money summary",
  "market.yesSmart": "YES smart money",
  "market.noSmart": "NO smart money",
  "market.holdersCount": "{n} holders",
  "market.confLine": "Confidence (analysis, not win probability)",
  "market.riskFlags": "Risk flags",
  "market.suggPrice": "Suggested limit price",
  "market.suggMax": "Suggested max notional",
  "market.chartTitle": "YES vs NO smart money notional",
  "market.holdersTitle": "Top holders (both sides, ranked by current position value)",
  "market.holdersEmpty": "No holder data captured for this market yet — try Re-analyze.",
  "market.thRank": "Rank",
  "market.thAddress": "Address",
  "market.thSide": "Side",
  "market.thPosValue": "Position value",
  "market.thShares": "Shares",
  "market.thAvgPx": "Avg px",
  "market.thLabel": "Label",
  "market.thWinRate": "Win rate",
  "market.thResolved": "Resolved",
  "market.thCatWr": "Cat. WR",
  "market.catWrTooltip": "Same-category win rate (keyword approximation)",
  "market.thAnomaly": "Anomaly",
  "market.anomalyTooltip": "Entry notional (approx) ÷ median historical entry",
  "market.thScore": "Score",
  "market.approxTooltip":
    "Approximated as shares × current price (position fetch unavailable)",

  // ---------------------------------------------------------------- account drawer
  "drawer.overallTitle": "Overall resolved history",
  "drawer.truncated":
    "⚠ History truncated at fetch limit — stats cover the most recent closed positions only.",
  "drawer.resolvedPositions": "Resolved positions",
  "drawer.winRate": "Win rate",
  "drawer.realizedPnl": "Realized PnL",
  "drawer.avgRoi": "Average ROI",
  "drawer.medianEntry": "Median entry notional",
  "drawer.firstSeen": "First seen",
  "drawer.lastSeen": "Last seen",
  "drawer.sameCatTitle": "Same category",
  "drawer.keywordApprox": "(keyword-matched approximation)",
  "drawer.trades": "Trades",
  "drawer.currentMarketTitle": "Current market",
  "drawer.direction": "Direction",
  "drawer.shares": "Shares",
  "drawer.avgPrice": "Average price",
  "drawer.posValue": "Position value",
  "drawer.entryApprox": "Entry notional (approx)",
  "drawer.entryApproxHint":
    "Cost basis of current holding (initialValue) — approximation of true opening amount, see data notes",
  "drawer.anomalyIndex": "Anomaly index",
  "drawer.anomalyHint": "entry notional (approx) ÷ median historical entry notional",
  "drawer.smartScore": "Smart money score",
  "drawer.label": "Label",
  "drawer.asOfNote":
    "Stats computed as of {date} using only positions resolved before that time (look-ahead-safe).",

  // ---------------------------------------------------------------- trade ticket modal
  "modal.title": "Trade Ticket",
  "modal.manualStatement":
    "This is not automated trading. You are manually confirming this order.",
  "modal.closeOnlyStatement":
    "This region is close-only. Opening new positions is disabled.",
  "modal.blockedStatement": "Trading is blocked for this region{suffix}.",
  "modal.failClosedSuffix": " (geoblock verification failed — failing closed)",
  "modal.liveDisabledAlert":
    "Live trading is disabled server-side (ENABLE_LIVE_TRADING=false). You can review the full flow and log this as a paper trade instead.",
  "modal.curPrice": "Current price",
  "modal.spread": "Spread",
  "modal.liquidity": "Liquidity",
  "modal.confidence": "Confidence",
  "modal.confValue": "{score} / 100 (analysis)",
  "modal.suggPrice": "Suggested price",
  "modal.suggMax": "Suggested max",
  "modal.riskFlags": "Risk flags",
  "modal.limitLabel": "Limit price (0–1, tick {tick})",
  "modal.notionalLabel": "Max notional (USDC)",
  "modal.cancel": "Cancel",
  "modal.logPaper": "Log as paper trade",
  "modal.paperLogged": "Paper trade logged ✓",
  "modal.runChecks": "Run risk checks",
  "modal.checksTitle": "Backend risk checks",
  "modal.allPassed": "all passed",
  "modal.checksFailed": "failed",
  "modal.checkGeoblock": "Geoblock ({mode})",
  "modal.checkMarket": "Market active & accepting orders",
  "modal.checkSpread": "Spread within limit",
  "modal.checkLiquidity": "Liquidity above minimum",
  "modal.checkPrice": "Limit price valid (slippage cap)",
  "modal.checkNotional": "Notional within cap",
  "modal.checkLive": "Live trading enabled (server)",
  "modal.ticketLine": "Ticket {id} · status {status}",
  "modal.expires": " · expires {time}",
  "modal.confirmCheckbox":
    "I manually confirm this order: BUY {direction} · limit {price} · max {notional}. I understand this is an analysis tool, not financial advice.",
  "modal.confirmSign": "Confirm & sign",
  "modal.submitting": "Submitting…",
  "modal.closeBtn": "Close",
  "modal.statusConfirming": "Recording manual confirmation…",
  "modal.statusSigning": "Waiting for order signature in your wallet…",
  "modal.statusDeriving": "Deriving CLOB API credentials (wallet attestation signature)…",
  "modal.statusSubmitting": "Submitting order (backend re-runs all risk checks)…",
  "modal.statusDone": "Order {status} — id {id}",
  "modal.doneSuffix": "— order recorded on the ticket.",
  "modal.createFailed": "Failed to create ticket",
  "modal.paperFailed": "Failed to log paper trade",
  "modal.submitFailed": "Submission failed: {message}",

  // ---------------------------------------------------------------- signals
  "signals.title": "Signal Log",
  "signals.thTime": "Time",
  "signals.thDirection": "Direction",
  "signals.thYesSmart": "YES smart $",
  "signals.thNoSmart": "NO smart $",
  "signals.thCounts": "Counts",
  "signals.thSuggPrice": "Sugg. price",
  "signals.thSuggMax": "Sugg. max",
  "signals.emptyHint": "No signals recorded yet — run the scanner from the dashboard.",

  // ---------------------------------------------------------------- paper trades
  "paper.title": "Paper Trading",
  "paper.subtitle":
    "Qualifying signals auto-log here at the side's best ask (taker price). Extreme-price and wide-spread signals are skipped, and one open auto position per market+direction — so PnL reflects signal quality, not spread cost. Simulated fills, no real orders. PnL = shares × (exit − entry); entries cross the spread, so a fresh position starts slightly negative until the price moves.",
  "paper.open": "Open",
  "paper.closed": "Closed",
  "paper.realizedPnl": "Realized PnL",
  "paper.unrealizedPnl": "Unrealized PnL",
  "paper.markedNote": "marked at best bid",
  "paper.winRateClosed": "Win rate (closed)",
  "paper.thEntryTime": "Entry time",
  "paper.thMarket": "Market",
  "paper.thSide": "Side",
  "paper.thSource": "Source",
  "paper.thEntry": "Entry",
  "paper.thNotional": "Notional",
  "paper.thShares": "Shares",
  "paper.thNowExit": "Now / Exit",
  "paper.thPnl": "PnL",
  "paper.thStatus": "Status",
  "paper.auto": "auto",
  "paper.manual": "manual",
  "paper.unrealizedTag": "unrlzd",
  "paper.closeAtMkt": "Close @ mkt",
  "paper.closing": "Closing…",
  "paper.emptyHint":
    "No paper trades yet. Run the scanner (qualifying signals auto-log) or log one from a market's trade ticket.",
  "paper.closeFailed": "Failed to close trade",
  "paper.closeAtBid": "Sell into bids",
  "paper.partialFill": "Book absorbed only part of the position — {n} shares still open.",
  "paper.remainingOf": "{left} of {total} left",
  "paper.thShadow": "Shadow exit",
  "paper.shadowTooltip":
    "Position monitor, shadow mode: what the exit rules WOULD do. Nothing is executed. R = share of the followed smart money's entry position still held.",
  "paper.shadowHold": "hold {pct}",
  "paper.shadowRetention": "R {pct}",
  "paper.settled": "settled",
  "paper.midFallback": "mid",

  // ---------------------------------------------------------------- trading page
  "trading.title": "Wallet / Trading",
  "trading.subtitle":
    "This app never asks for, stores, or transmits private keys. It only reads your address and requests EIP-712 signatures inside your own wallet.",
  "trading.walletCard": "Wallet",
  "trading.noWallet": "No wallet connected.",
  "trading.connect": "Connect {name}",
  "trading.connecting": "Connecting…",
  "trading.disconnect": "Disconnect",
  "trading.switchPolygon": "Switch to Polygon",
  "trading.wrongChain": "wrong chain ({id})",
  "trading.noInjected":
    "No injected wallet detected — install MetaMask or a compatible wallet.",
  "trading.geoCard": "Geographic restrictions",
  "trading.countryLine": "country {country} · checked from the backend's egress IP",
  "trading.openPositions": "Open new positions:",
  "trading.closePositions": "Close positions:",
  "trading.allowed": "allowed",
  "trading.blocked": "blocked",
  "trading.blockedAlert":
    "Trading is blocked for this region{suffix}. This tool will not bypass geographic restrictions.",
  "trading.failClosedSuffix": " (verification failed — failing closed)",
  "trading.checkingGeo": "Checking geoblock…",
  "trading.geoUnavailable": "Geoblock status unavailable.",
  "trading.balancesCard": "Balances & allowances (Polygon)",
  "trading.usdcBalance": "USDC.e balance",
  "trading.polBalance": "POL balance",
  "trading.ctfAllowance": "CTF Exchange allowance",
  "trading.negAllowance": "Neg-risk allowance",
  "trading.sufficient": "sufficient",
  "trading.insufficient": "insufficient",
  "trading.approvalsNote":
    "Approvals must be made from your own wallet (e.g. on Polymarket's site or a block explorer) — this app never sends approval transactions for you.",
  "trading.connectToView": "Connect a wallet to view balances and allowances.",
  "trading.modeCard": "Trading mode",
  "trading.liveEnabled": "LIVE TRADING ENABLED",
  "trading.paperMode": "PAPER MODE (live disabled)",
  "trading.serverFlag": "server-side ENABLE_LIVE_TRADING={value}",
  "trading.liveAlert":
    "Live order submission is enabled on the backend. Every order still requires your manual confirmation and wallet signature, and passes geoblock/balance/allowance/spread/slippage/notional checks twice.",
  "trading.paperAlert":
    "Default safe mode: orders cannot reach the exchange. Signals are tracked via paper trading. To enable live trading, set ENABLE_LIVE_TRADING=true on the backend after reading docs/risk-control.md.",
  "trading.limitsLine":
    "Max notional {notional} · max spread {spread} bps · max slippage {slippage} bps · close-only regions: {regions}",

  // ---------------------------------------------------------------- settings
  "settings.title": "Settings",
  "settings.subtitle":
    "Read-only view of backend configuration (set via environment variables — see .env.example). Nothing here can enable live trading from the browser.",
  "settings.prefsCard": "Preferences (this browser)",
  "settings.language": "Language",
  "settings.languageHint":
    "Stored in a browser cookie — applies to this browser only.",
  "settings.backendCard": "Backend",
  "settings.apiBase": "API base",
  "settings.status": "Status",
  "settings.database": "Database",
  "settings.version": "Version",
  "settings.scheduler": "Scheduler",
  "settings.running": "running",
  "settings.schedulerOff": "off (manual scans)",
  "settings.safetyCard": "Trading safety (server-side)",
  "settings.spreadBpsValue": "{bps} bps (= {abs} price units)",
  "settings.bpsHint": "1 bp = 0.0001 absolute price on the 0–1 scale",
  "settings.closeOnlyRegions": "Close-only regions",
  "settings.scannerCard": "Scanner & signals",
  "settings.maxMarkets": "Max markets per scan",
  "settings.interval": "Scheduled interval",
  "settings.intervalMin": "{n} min",
  "settings.intervalDisabled": "disabled (manual)",
  "settings.scoreThreshold": "Smart money score threshold",
  "settings.nearResFlag": "Near-resolution flag",
  "settings.nearResValue": "< {h}h to end",
  "settings.autoPaper": "Auto paper-trade signals",
  "settings.disclaimersCard": "Data semantics & disclaimers",
  "settings.d1": "· Confidence scores are heuristic analysis aids — never win probabilities.",
  "settings.d2":
    '· "Entry notional (approx)" is the cost basis of the current holding, an approximation of true opening size (see docs/data-field-uncertainties.md).',
  "settings.d3": "· Same-category stats use keyword matching — approximate by design.",
  "settings.d4":
    "· Account stats only use positions resolved before each signal's timestamp (look-ahead-safe).",
  "settings.d5":
    "· Open interest shown is event-level (market-level OI is not exposed by the API).",
  "settings.d6": "· This software is an analysis tool. Nothing it produces is financial advice.",
} as const;

export type MessageKey = keyof typeof en;

const zh: Record<MessageKey, string> = {
  "nav.brand": "Polymarket",
  "nav.brandSub": "聪明钱监控台",
  "nav.dashboard": "仪表盘",
  "nav.signals": "信号记录",
  "nav.paperTrading": "模拟交易",
  "nav.walletTrading": "钱包 / 交易",
  "nav.settings": "设置",
  "nav.disclaimer":
    "仅为分析信号，不构成投资建议。默认模拟交易——除非在服务端显式开启，真实交易始终关闭。",

  "common.failedToLoad": "数据加载失败",
  "common.retry": "重试",
  "common.noData": "暂无数据",
  "common.neutral": "中性",
  "common.copyAddress": "复制地址",
  "common.confidenceTooltip": "分析信心分（启发式排序工具——不是胜率）",
  "common.signalDisclaimer":
    "分析信号——基于持仓观察的启发式规则排序。不构成投资建议，不是胜率，历史统计不预示未来结果。",

  "labels.HIGH_WIN_RATE": "高胜率",
  "labels.ABNORMAL_POSITION": "异常仓位",
  "labels.NEW_ACCOUNT": "新账户",
  "labels.OTHER": "其他",

  "flags.LOW_LIQUIDITY": "流动性低",
  "flags.WIDE_SPREAD": "价差过宽",
  "flags.NEAR_RESOLUTION": "临近结算",
  "flags.EXTREME_PRICE": "极端价格",
  "flags.LOW_SMART_SAMPLE": "聪明钱样本少",
  "flags.NEW_ACCOUNT_HEAVY": "新账户占比高",
  "flags.ONE_SIDED_BOOK": "盘口单边",
  "flags.PARTIAL_DATA": "数据不完整",

  "dash.title": "热门市场",
  "dash.runScanner": "运行扫描",
  "dash.scanning": "扫描中…",
  "dash.refresh": "刷新",
  "dash.notRunYet": "扫描器尚未运行",
  "dash.lastScan": "上次扫描：{status} · 分析 {analyzed} 个 · 信号 {signals} 条",
  "dash.errors": "{n} 个错误",
  "dash.scanCount": "{analyzed}/{found} 个市场",
  "dash.allCategories": "全部类目",
  "dash.anyDirection": "任意方向",
  "dash.anyConfidence": "任意信心分",
  "dash.confGte": "信心分 ≥ {n}",
  "dash.anyLiquidity": "任意流动性",
  "dash.liqGte": "流动性 ≥ ${n}",
  "dash.exclude": "排除：",
  "dash.excludeTooltip": "隐藏带 {flag} 标签的市场",
  "dash.thMarket": "市场",
  "dash.thCategory": "类目",
  "dash.thYes": "Yes",
  "dash.thNo": "No",
  "dash.thSpread": "价差",
  "dash.thVol": "24h成交",
  "dash.thLiquidity": "流动性",
  "dash.thOi": "持仓量*",
  "dash.oiTooltip": "事件级未平仓量（见数据口径说明）",
  "dash.thSmart": "聪明钱",
  "dash.thConf": "信心分",
  "dash.thRiskFlags": "风险标签",
  "dash.analyzedAt": "分析于 {time}",
  "dash.emptyHint": "还没有已分析的市场。点击“运行扫描”开始扫描 Polymarket 热门市场。",

  "market.reanalyze": "重新分析",
  "market.reanalyzing": "重新分析中…",
  "market.generateTicket": "生成交易票据",
  "market.ends": "结算于 {time}",
  "market.active": "进行中",
  "market.inactiveClosed": "已停止/已关闭",
  "market.notAccepting": "不接受订单",
  "market.analyzedAt": "分析于 {time}",
  "market.statYes": "YES 价格",
  "market.statNo": "NO 价格",
  "market.statSpread": "价差",
  "market.statLiquidity": "流动性",
  "market.statVol": "24h 成交额",
  "market.statOi": "未平仓量",
  "market.eventLevel": "事件级",
  "market.summaryTitle": "聪明钱概览",
  "market.yesSmart": "YES 侧聪明钱",
  "market.noSmart": "NO 侧聪明钱",
  "market.holdersCount": "{n} 个持仓人",
  "market.confLine": "信心分（分析用途，不是胜率）",
  "market.riskFlags": "风险标签",
  "market.suggPrice": "建议限价",
  "market.suggMax": "建议金额上限",
  "market.chartTitle": "YES vs NO 聪明钱持仓金额",
  "market.holdersTitle": "Top 持仓人（双边，按当前仓位市值排序）",
  "market.holdersEmpty": "该市场暂无持仓人数据——试试“重新分析”。",
  "market.thRank": "排名",
  "market.thAddress": "地址",
  "market.thSide": "方向",
  "market.thPosValue": "仓位市值",
  "market.thShares": "份额",
  "market.thAvgPx": "均价",
  "market.thLabel": "标签",
  "market.thWinRate": "胜率",
  "market.thResolved": "已结算",
  "market.thCatWr": "同类胜率",
  "market.catWrTooltip": "同类目胜率（关键词匹配近似）",
  "market.thAnomaly": "异常指数",
  "market.anomalyTooltip": "开仓成本(近似) ÷ 历史开仓中位数",
  "market.thScore": "评分",
  "market.approxTooltip": "由 份额 × 现价 近似（持仓接口未取到）",

  "drawer.overallTitle": "整体已结算历史",
  "drawer.truncated": "⚠ 历史已在抓取上限处截断——统计仅覆盖最近的已结算仓位。",
  "drawer.resolvedPositions": "已结算仓位",
  "drawer.winRate": "胜率",
  "drawer.realizedPnl": "已实现盈亏",
  "drawer.avgRoi": "平均回报率",
  "drawer.medianEntry": "开仓金额中位数",
  "drawer.firstSeen": "首次活跃",
  "drawer.lastSeen": "最近活跃",
  "drawer.sameCatTitle": "同类目",
  "drawer.keywordApprox": "（关键词匹配近似）",
  "drawer.trades": "笔数",
  "drawer.currentMarketTitle": "当前市场",
  "drawer.direction": "方向",
  "drawer.shares": "份额",
  "drawer.avgPrice": "开仓均价",
  "drawer.posValue": "仓位市值",
  "drawer.entryApprox": "开仓成本（近似）",
  "drawer.entryApproxHint":
    "当前持仓的成本基（initialValue）——真实首次开仓金额的近似值，见数据口径说明",
  "drawer.anomalyIndex": "异常指数",
  "drawer.anomalyHint": "开仓成本(近似) ÷ 历史开仓金额中位数",
  "drawer.smartScore": "聪明钱评分",
  "drawer.label": "标签",
  "drawer.asOfNote": "统计基准时间 {date}，仅使用该时点之前已结算的仓位（防未来函数）。",

  "modal.title": "交易票据",
  "modal.manualStatement":
    "这不是自动交易，您正在手动确认此订单。(This is not automated trading. You are manually confirming this order.)",
  "modal.closeOnlyStatement":
    "当前地区为仅平仓（close-only）模式，禁止开新仓。(This region is close-only. Opening new positions is disabled.)",
  "modal.blockedStatement": "当前地区禁止交易{suffix}。",
  "modal.failClosedSuffix": "（地区校验失败——按封禁保守处理）",
  "modal.liveDisabledAlert":
    "服务端已关闭真实交易（ENABLE_LIVE_TRADING=false）。您可以完整体验流程，并改为记录一笔模拟交易。",
  "modal.curPrice": "当前价格",
  "modal.spread": "价差",
  "modal.liquidity": "流动性",
  "modal.confidence": "信心分",
  "modal.confValue": "{score} / 100（分析用途）",
  "modal.suggPrice": "建议限价",
  "modal.suggMax": "建议上限",
  "modal.riskFlags": "风险标签",
  "modal.limitLabel": "限价（0–1，最小变动 {tick}）",
  "modal.notionalLabel": "金额上限（USDC）",
  "modal.cancel": "取消",
  "modal.logPaper": "记为模拟交易",
  "modal.paperLogged": "已记录模拟交易 ✓",
  "modal.runChecks": "运行风控检查",
  "modal.checksTitle": "后端风控检查",
  "modal.allPassed": "全部通过",
  "modal.checksFailed": "未通过",
  "modal.checkGeoblock": "地区限制（{mode}）",
  "modal.checkMarket": "市场有效且接受订单",
  "modal.checkSpread": "价差在限制内",
  "modal.checkLiquidity": "流动性高于下限",
  "modal.checkPrice": "限价有效（滑点上限）",
  "modal.checkNotional": "金额在上限内",
  "modal.checkLive": "服务端已开启真实交易",
  "modal.ticketLine": "票据 {id} · 状态 {status}",
  "modal.expires": " · 过期时间 {time}",
  "modal.confirmCheckbox":
    "我手动确认此订单：买入 {direction} · 限价 {price} · 上限 {notional}。我理解这是分析工具，不构成投资建议。",
  "modal.confirmSign": "确认并签名",
  "modal.submitting": "提交中…",
  "modal.closeBtn": "关闭",
  "modal.statusConfirming": "正在记录手动确认…",
  "modal.statusSigning": "等待您在钱包中签名订单…",
  "modal.statusDeriving": "正在派生 CLOB API 凭证（钱包认证签名）…",
  "modal.statusSubmitting": "正在提交订单（后端复检全部风控）…",
  "modal.statusDone": "订单 {status} — 编号 {id}",
  "modal.doneSuffix": "——结果已记录在票据上。",
  "modal.createFailed": "创建票据失败",
  "modal.paperFailed": "记录模拟交易失败",
  "modal.submitFailed": "提交失败：{message}",

  "signals.title": "信号记录",
  "signals.thTime": "时间",
  "signals.thDirection": "方向",
  "signals.thYesSmart": "YES 聪明钱",
  "signals.thNoSmart": "NO 聪明钱",
  "signals.thCounts": "人数",
  "signals.thSuggPrice": "建议价",
  "signals.thSuggMax": "建议上限",
  "signals.emptyHint": "暂无信号记录——请先在仪表盘运行扫描。",

  "paper.title": "模拟交易",
  "paper.subtitle":
    "合格信号会按该方向的卖一价（taker 可成交价）自动入账。极端价格与宽价差信号会被跳过，且同一市场同方向只保留一笔未平自动仓——因此盈亏反映的是信号质量而非价差成本。全部为模拟成交，无真实订单。盈亏 = 份额 ×（出场价 − 入场价）；入场需跨越价差，新仓位在价格变动前会略为负值。",
  "paper.open": "持仓中",
  "paper.closed": "已平仓",
  "paper.realizedPnl": "已实现盈亏",
  "paper.unrealizedPnl": "未实现盈亏",
  "paper.markedNote": "按买一价盯市",
  "paper.winRateClosed": "胜率（已平仓）",
  "paper.thEntryTime": "入场时间",
  "paper.thMarket": "市场",
  "paper.thSide": "方向",
  "paper.thSource": "来源",
  "paper.thEntry": "入场价",
  "paper.thNotional": "金额",
  "paper.thShares": "份额",
  "paper.thNowExit": "现价 / 出场价",
  "paper.thPnl": "盈亏",
  "paper.thStatus": "状态",
  "paper.auto": "自动",
  "paper.manual": "手动",
  "paper.unrealizedTag": "未实现",
  "paper.closeAtMkt": "按市价平仓",
  "paper.closing": "平仓中…",
  "paper.emptyHint": "暂无模拟交易。运行扫描（合格信号会自动入账），或在市场详情的交易票据中手动记录。",
  "paper.closeFailed": "平仓失败",
  "paper.closeAtBid": "按买盘深度平仓",
  "paper.partialFill": "买盘只承接了部分仓位，仍有 {n} 份未平。",
  "paper.remainingOf": "剩余 {left} / {total}",
  "paper.thShadow": "影子退出",
  "paper.shadowTooltip":
    "持仓监控（影子模式）：退出规则本会怎么做，不会实际执行。R = 入场跟随的聪明钱仍保留的入场仓位比例。",
  "paper.shadowHold": "保留 {pct}",
  "paper.shadowRetention": "R {pct}",
  "paper.settled": "已结算",
  "paper.midFallback": "中间价",

  "trading.title": "钱包 / 交易",
  "trading.subtitle":
    "本应用绝不索取、存储或传输私钥，只读取地址并在您自己的钱包内请求 EIP-712 签名。",
  "trading.walletCard": "钱包",
  "trading.noWallet": "未连接钱包。",
  "trading.connect": "连接 {name}",
  "trading.connecting": "连接中…",
  "trading.disconnect": "断开连接",
  "trading.switchPolygon": "切换到 Polygon",
  "trading.wrongChain": "链不正确（{id}）",
  "trading.noInjected": "未检测到浏览器钱包——请安装 MetaMask 或兼容钱包。",
  "trading.geoCard": "地区限制",
  "trading.countryLine": "国家/地区 {country} · 按后端出口 IP 检测",
  "trading.openPositions": "开新仓：",
  "trading.closePositions": "平仓：",
  "trading.allowed": "允许",
  "trading.blocked": "禁止",
  "trading.blockedAlert": "当前地区禁止交易{suffix}。本工具不会绕过任何地区限制。",
  "trading.failClosedSuffix": "（校验失败——按封禁保守处理）",
  "trading.checkingGeo": "正在检查地区限制…",
  "trading.geoUnavailable": "地区限制状态不可用。",
  "trading.balancesCard": "余额与授权（Polygon）",
  "trading.usdcBalance": "USDC.e 余额",
  "trading.polBalance": "POL 余额",
  "trading.ctfAllowance": "CTF 交易所授权",
  "trading.negAllowance": "Neg-risk 授权",
  "trading.sufficient": "充足",
  "trading.insufficient": "不足",
  "trading.approvalsNote":
    "授权（approve）需在您自己的钱包中完成（例如在 Polymarket 官网或区块浏览器）——本应用绝不代发授权交易。",
  "trading.connectToView": "连接钱包后可查看余额与授权。",
  "trading.modeCard": "交易模式",
  "trading.liveEnabled": "真实交易已开启",
  "trading.paperMode": "模拟模式（真实交易关闭）",
  "trading.serverFlag": "服务端 ENABLE_LIVE_TRADING={value}",
  "trading.liveAlert":
    "后端已开启真实下单。每笔订单仍需您手动确认并用钱包签名，且两次通过地区/余额/授权/价差/滑点/金额上限检查。",
  "trading.paperAlert":
    "默认安全模式：订单无法到达交易所，信号通过模拟交易跟踪。如需开启真实交易，请先阅读 docs/risk-control.md，再在后端设置 ENABLE_LIVE_TRADING=true。",
  "trading.limitsLine":
    "金额上限 {notional} · 价差上限 {spread} bps · 滑点上限 {slippage} bps · 仅平仓地区：{regions}",

  "settings.title": "设置",
  "settings.subtitle":
    "后端配置的只读视图（通过环境变量设置——见 .env.example）。浏览器中无法开启真实交易。",
  "settings.prefsCard": "偏好（仅本浏览器）",
  "settings.language": "界面语言",
  "settings.languageHint": "保存在浏览器 cookie 中——仅对当前浏览器生效。",
  "settings.backendCard": "后端",
  "settings.apiBase": "API 地址",
  "settings.status": "状态",
  "settings.database": "数据库",
  "settings.version": "版本",
  "settings.scheduler": "定时扫描",
  "settings.running": "运行中",
  "settings.schedulerOff": "关闭（手动扫描）",
  "settings.safetyCard": "交易安全（服务端）",
  "settings.spreadBpsValue": "{bps} bps（= {abs} 价格单位）",
  "settings.bpsHint": "1 bp = 0–1 报价上的 0.0001 绝对价格",
  "settings.closeOnlyRegions": "仅平仓地区",
  "settings.scannerCard": "扫描与信号",
  "settings.maxMarkets": "单次扫描市场数上限",
  "settings.interval": "定时间隔",
  "settings.intervalMin": "{n} 分钟",
  "settings.intervalDisabled": "关闭（手动）",
  "settings.scoreThreshold": "聪明钱评分门槛",
  "settings.nearResFlag": "临近结算标记",
  "settings.nearResValue": "距结算 < {h} 小时",
  "settings.autoPaper": "信号自动记模拟交易",
  "settings.disclaimersCard": "数据口径与免责声明",
  "settings.d1": "· 信心分是启发式分析工具——永远不是胜率。",
  "settings.d2":
    "· “开仓成本（近似）”是当前持仓的成本基，是真实首次开仓金额的近似值（见 docs/data-field-uncertainties.md）。",
  "settings.d3": "· 同类目统计基于关键词匹配——设计上即为近似。",
  "settings.d4": "· 账户统计仅使用各信号时间点之前已结算的仓位（防未来函数）。",
  "settings.d5": "· 展示的未平仓量为事件级（API 不提供市场级数据）。",
  "settings.d6": "· 本软件是分析工具，其任何输出均不构成投资建议。",
};

const MESSAGES: Record<Locale, Record<MessageKey, string>> = { en, zh };

export function translate(locale: Locale, key: MessageKey,
                          params?: Record<string, string | number>): string {
  let text: string = MESSAGES[locale][key] ?? en[key] ?? key;
  if (params) {
    for (const [name, value] of Object.entries(params)) {
      text = text.replaceAll(`{${name}}`, String(value));
    }
  }
  return text;
}

/** Confirm-gating returns canonical English blockers (single tested source of truth);
 * the UI translates them for display. Unknown/backend-generated strings pass through. */
const BLOCKER_ZH: [string, string][] = [
  ["Wallet is not connected.", "钱包未连接。"],
  ["Wallet is not on Polygon (chain 137).", "钱包未切换到 Polygon（链 137）。"],
  ["Geoblock status not verified yet.", "地区限制状态尚未校验。"],
  ["Trading is blocked for this region.", "当前地区禁止交易。"],
  ["This region is close-only. Opening new positions is disabled.",
   "当前地区为仅平仓模式，禁止开新仓。"],
  ["Backend risk checks not available.", "后端风控检查结果不可用。"],
  ["Backend risk check failed", "后端风控检查未通过"],
  ["Live trading is disabled (ENABLE_LIVE_TRADING=false).",
   "真实交易已关闭（ENABLE_LIVE_TRADING=false）。"],
  ["Ticket expired — prices are stale. Create a new one.",
   "票据已过期——价格已陈旧，请重新创建。"],
  ["Manual confirmation checkbox is not checked.", "尚未勾选手动确认。"],
];

export function translateBlocker(locale: Locale, blocker: string): string {
  if (locale !== "zh") return blocker;
  for (const [enText, zhText] of BLOCKER_ZH) {
    if (blocker === enText) return zhText;
    if (blocker.startsWith(enText)) return zhText + blocker.slice(enText.length);
  }
  return blocker;
}

// ---------------------------------------------------------------- context

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: MessageKey, params?: Record<string, string | number>) => string;
}

const I18nContext = React.createContext<I18nContextValue>({
  locale: "en",
  setLocale: () => undefined,
  t: (key, params) => translate("en", key, params),
});

export function I18nProvider({ initialLocale, children }: {
  initialLocale: Locale;
  children: React.ReactNode;
}) {
  const [locale, setLocaleState] = React.useState<Locale>(initialLocale);
  const setLocale = React.useCallback((next: Locale) => {
    setLocaleState(next);
    // UI preference only (never sensitive data); 1-year cookie so SSR matches.
    document.cookie = `${LOCALE_COOKIE}=${next}; path=/; max-age=31536000; samesite=lax`;
  }, []);
  const value = React.useMemo<I18nContextValue>(() => ({
    locale,
    setLocale,
    t: (key, params) => translate(locale, key, params),
  }), [locale, setLocale]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  return React.useContext(I18nContext);
}

