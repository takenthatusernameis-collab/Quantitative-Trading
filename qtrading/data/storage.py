"""SQLite/PostgreSQL data storage with SQLAlchemy."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    create_engine,
    delete,
    select,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from qtrading.data.models import OHLCV, Exchange, Timeframe


class Base(DeclarativeBase):
    pass


class OHLCVModel(Base):
    __tablename__ = "ohlcv_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    symbol = Column(String, nullable=False, index=True)
    timeframe = Column(String, nullable=False, index=True)
    exchange = Column(String, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)

    __table_args__ = (
        Index(
            "idx_ohlcv_symbol_tf_exchange",
            "symbol",
            "timeframe",
            "exchange",
            "timestamp",
            unique=True,
        ),
    )

    def to_ohlcv(self) -> OHLCV:
        return OHLCV(
            timestamp=self.timestamp,
            open=Decimal(str(self.open)),
            high=Decimal(str(self.high)),
            low=Decimal(str(self.low)),
            close=Decimal(str(self.close)),
            volume=Decimal(str(self.volume)),
            symbol=self.symbol,
            timeframe=Timeframe(self.timeframe),
            exchange=Exchange(self.exchange),
        )

    @classmethod
    def from_ohlcv(cls, ohlcv: OHLCV) -> "OHLCVModel":
        return cls(
            timestamp=ohlcv.timestamp,
            symbol=ohlcv.symbol,
            timeframe=ohlcv.timeframe.value,
            exchange=ohlcv.exchange.value,
            open=float(ohlcv.open),
            high=float(ohlcv.high),
            low=float(ohlcv.low),
            close=float(ohlcv.close),
            volume=float(ohlcv.volume),
        )


class DataStorage:
    """Manages persistent storage of OHLCV data using SQLAlchemy."""

    def __init__(self, db_path: str = "./data/market_data.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            echo=False,
        )
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    def save_ohlcv(self, ohlcvs: list[OHLCV]) -> int:
        """Save OHLCV data to the database. Returns count of saved records."""
        if not ohlcvs:
            return 0
        with self.SessionLocal() as session:
            models = [OHLCVModel.from_ohlcv(c) for c in ohlcvs]
            for model in models:
                existing = session.execute(
                    select(OHLCVModel).where(
                        OHLCVModel.symbol == model.symbol,
                        OHLCVModel.timeframe == model.timeframe,
                        OHLCVModel.exchange == model.exchange,
                        OHLCVModel.timestamp == model.timestamp,
                    )
                ).scalar_one_or_none()
                if existing is None:
                    session.add(model)
            session.commit()
            return len(models)

    def load_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        exchange: Exchange,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> list[OHLCV]:
        """Load OHLCV data from the database."""
        with self.SessionLocal() as session:
            query = select(OHLCVModel).where(
                OHLCVModel.symbol == symbol,
                OHLCVModel.timeframe == timeframe.value,
                OHLCVModel.exchange == exchange.value,
            )
            if since:
                query = query.where(OHLCVModel.timestamp >= since)
            query = query.order_by(OHLCVModel.timestamp)
            if limit:
                query = query.limit(limit)
            results = session.execute(query).scalars().all()
            return [m.to_ohlcv() for m in results]

    def delete_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        exchange: Exchange,
    ) -> int:
        """Delete OHLCV data for a specific symbol/timeframe/exchange."""
        with self.SessionLocal() as session:
            stmt = delete(OHLCVModel).where(
                OHLCVModel.symbol == symbol,
                OHLCVModel.timeframe == timeframe.value,
                OHLCVModel.exchange == exchange.value,
            )
            result = session.execute(stmt)
            session.commit()
            return int(result.rowcount) if result.rowcount else 0

    def get_available_symbols(self) -> list[str]:
        """Get list of all available symbols in storage."""
        with self.SessionLocal() as session:
            results = session.execute(
                select(OHLCVModel.symbol).distinct()
            ).scalars().all()
            return list(results)

    def get_available_timeframes(self, symbol: str) -> list[str]:
        """Get list of available timeframes for a symbol."""
        with self.SessionLocal() as session:
            results = session.execute(
                select(OHLCVModel.timeframe).where(
                    OHLCVModel.symbol == symbol
                ).distinct()
            ).scalars().all()
            return list(results)

    def close(self) -> None:
        """Close the database connection."""
        self.engine.dispose()
