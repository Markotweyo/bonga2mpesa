import uuid
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import LedgerEntry, LedgerEntryType, Transaction

logger = get_logger(__name__)


class LedgerService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_running_balance(self) -> float:
        result = await self.db.execute(
            select(func.sum(
                func.case(
                    (LedgerEntry.entry_type == LedgerEntryType.CREDIT, LedgerEntry.amount),
                    else_=-LedgerEntry.amount,
                )
            ))
        )
        return float(result.scalar() or 0.0)

    async def record_credit(
        self,
        transaction: Transaction,
        amount: float,
        description: str = "Safaricom C2B inflow",
    ) -> LedgerEntry:
        balance = await self.get_running_balance()
        balance_after = balance + amount

        entry = LedgerEntry(
            id=uuid.uuid4(),
            transaction_id=transaction.id,
            entry_type=LedgerEntryType.CREDIT,
            amount=amount,
            balance_after=balance_after,
            description=description,
        )
        self.db.add(entry)
        await self.db.flush()

        logger.info(
            "ledger_credit",
            transaction_id=str(transaction.id),
            amount=amount,
            balance_after=balance_after,
        )
        return entry

    async def record_debit(
        self,
        transaction: Transaction,
        amount: float,
        description: str = "User B2C payout",
    ) -> LedgerEntry:
        balance = await self.get_running_balance()
        balance_after = balance - amount

        entry = LedgerEntry(
            id=uuid.uuid4(),
            transaction_id=transaction.id,
            entry_type=LedgerEntryType.DEBIT,
            amount=amount,
            balance_after=balance_after,
            description=description,
        )
        self.db.add(entry)
        await self.db.flush()

        logger.info(
            "ledger_debit",
            transaction_id=str(transaction.id),
            amount=amount,
            balance_after=balance_after,
        )
        return entry

    async def record_transaction_complete(
        self,
        transaction: Transaction,
    ) -> None:
        """Record both legs of a completed transaction."""
        await self.record_credit(
            transaction,
            float(transaction.safaricom_amount),
            "Safaricom C2B inflow",
        )
        await self.record_debit(
            transaction,
            float(transaction.payout_amount),
            "User B2C payout",
        )
        await self.db.flush()
