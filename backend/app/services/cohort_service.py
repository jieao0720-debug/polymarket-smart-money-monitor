"""Freeze the smart-money cohort a paper trade followed at entry (A26).

The cohort is rebuilt from what the scanner persisted at the entry signal's snapshot
(market_holders + account_labels at the same snapshot_time), so a fresh entry and a
backfill of an older OPEN trade go through exactly the same code path.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Account,
    AccountLabel,
    MarketHolder,
    PaperTrade,
    PaperTradeCohortMember,
    SmartMoneySignal,
)
from app.services.exit_rules import HolderRecord, build_cohort
from app.services.smart_money_service import LABEL_NEW_ACCOUNT

COHORT_SOURCE_ENTRY = "ENTRY"
COHORT_SOURCE_BACKFILL = "BACKFILL"


async def has_cohort(session: AsyncSession, trade: PaperTrade) -> bool:
    row = (await session.execute(select(PaperTradeCohortMember.id).where(
        PaperTradeCohortMember.paper_trade_id == trade.id).limit(1))).first()
    return row is not None


async def capture_cohort(session: AsyncSession, trade: PaperTrade, *,
                         smart_money_score_threshold: float,
                         source: str = COHORT_SOURCE_ENTRY) -> list[PaperTradeCohortMember]:
    """Idempotent. Returns [] when the trade has no signal (e.g. manual without one) or
    the entry snapshot held no qualifying smart-money account."""
    if trade.signal_id is None or await has_cohort(session, trade):
        return []
    signal = (await session.execute(select(SmartMoneySignal).where(
        SmartMoneySignal.signal_uid == trade.signal_id))).scalar_one_or_none()
    if signal is None:
        return []
    rows = (await session.execute(
        select(MarketHolder, Account.wallet_address, AccountLabel)
        .join(Account, MarketHolder.account_id == Account.id)
        .join(AccountLabel, (AccountLabel.account_id == MarketHolder.account_id)
              & (AccountLabel.market_id == MarketHolder.market_id)
              & (AccountLabel.snapshot_time == MarketHolder.snapshot_time)
              # A two-sided wallet has one label per side. Legacy labels carry no
              # direction and match both rows; those are resolved below.
              & ((AccountLabel.direction == MarketHolder.direction)
                 | AccountLabel.direction.is_(None)))
        .where(MarketHolder.market_id == signal.market_id,
               MarketHolder.snapshot_time == signal.snapshot_time))).all()
    # One record per (wallet, side). With ambiguous legacy labels keep the LOWEST score:
    # a wallet is only followed if every label that could be its own says smart money.
    by_key: dict[tuple[str, str], HolderRecord] = {}
    for holder, wallet, label in rows:
        record = HolderRecord(
            wallet_address=wallet, direction=holder.direction, shares=holder.shares,
            position_value=holder.current_position_value,
            smart_money_score=label.smart_money_score, label=label.label,
            # ASSUMPTION-A8, same rule the scanner applied when it built the signal.
            is_smart_money=(label.label != LABEL_NEW_ACCOUNT
                            and label.smart_money_score >= smart_money_score_threshold),
            opposite_shares=holder.opposite_shares)
        key = (wallet, holder.direction)
        if key not in by_key or record.smart_money_score < by_key[key].smart_money_score:
            by_key[key] = record
    holders = list(by_key.values())
    members = [PaperTradeCohortMember(
        paper_trade_id=trade.id, wallet_address=seed.wallet_address,
        direction=trade.direction, entry_shares=seed.entry_shares,
        entry_opposite_shares=seed.entry_opposite_shares,
        entry_net_exposure=seed.entry_net_exposure, entry_value=seed.entry_value,
        entry_baseline_verified=seed.baseline_verified,
        weight=seed.weight, smart_money_score=seed.smart_money_score, label=seed.label,
        source=source, signal_snapshot_time=signal.snapshot_time)
        for seed in build_cohort(holders, trade.direction)]
    session.add_all(members)
    await session.flush()
    return members
