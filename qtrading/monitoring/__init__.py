import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from loguru import logger
from prometheus_client import Counter, Gauge, Histogram, start_http_server

from qtrading.config import get_settings
from qtrading.monitoring.dashboard import (
    DashboardMetrics,
    DashboardState,
    PortfolioState,
    RiskDashboard,
    WebSocketManager,
    dashboard_session,
    run_dashboard,
)


@dataclass
class MetricSnapshot:
    timestamp: datetime
    portfolio_value: Decimal
    cash: Decimal
    positions: dict[str, Decimal]
    daily_pnl: Decimal
    total_pnl: Decimal
    drawdown: Decimal
    open_orders: int
    filled_orders: int
    rejected_orders: int
    strategy_signals: int
    risk_metrics: dict[str, Any]


class MetricsCollector:
    def __init__(self, config_path: str | None = None):
        settings = get_settings(config_path)
        self.port = settings.monitoring.metrics_port
        self._server_started = False

        self.portfolio_value = Gauge("qtrading_portfolio_value", "Current portfolio value")
        self.cash = Gauge("qtrading_cash", "Available cash")
        self.daily_pnl = Gauge("qtrading_daily_pnl", "Daily P&L")
        self.total_pnl = Gauge("qtrading_total_pnl", "Total P&L")
        self.drawdown = Gauge("qtrading_drawdown", "Current drawdown")
        self.position_count = Gauge("qtrading_position_count", "Number of open positions")
        self.open_orders = Gauge("qtrading_open_orders", "Number of open orders")
        self.filled_orders = Counter(
            "qtrading_filled_orders_total", "Total filled orders", ["symbol", "side"]
        )
        self.rejected_orders = Counter(
            "qtrading_rejected_orders_total", "Total rejected orders", ["symbol", "side"]
        )
        self.strategy_signals = Counter(
            "qtrading_strategy_signals_total", "Total strategy signals", ["strategy", "signal_type"]
        )
        self.order_latency = Histogram("qtrading_order_latency_seconds", "Order execution latency")
        self.data_fetch_latency = Histogram(
            "qtrading_data_fetch_latency_seconds", "Data fetch latency"
        )
        self.strategy_latency = Histogram(
            "qtrading_strategy_latency_seconds", "Strategy execution latency"
        )
        self.risk_var = Gauge("qtrading_risk_var", "Portfolio Value at Risk")
        self.risk_leverage = Gauge("qtrading_risk_leverage", "Portfolio leverage")
        self.risk_correlation = Gauge(
            "qtrading_risk_max_correlation", "Maximum position correlation"
        )

    def start_server(self) -> None:
        if not self._server_started:
            start_http_server(self.port)
            self._server_started = True
            logger.info(f"Metrics server started on port {self.port}")

    def record_portfolio(
        self, value: Decimal, cash: Decimal, positions: dict[str, Decimal]
    ) -> None:
        self.portfolio_value.set(float(value))
        self.cash.set(float(cash))
        self.position_count.set(len(positions))

    def record_pnl(self, daily: Decimal, total: Decimal, drawdown: Decimal) -> None:
        self.daily_pnl.set(float(daily))
        self.total_pnl.set(float(total))
        self.drawdown.set(float(drawdown))

    def record_order(self, symbol: str, side: str, status: str, latency: float) -> None:
        self.order_latency.observe(latency)
        if status == "filled":
            self.filled_orders.labels(symbol=symbol, side=side).inc()
        elif status == "rejected":
            self.rejected_orders.labels(symbol=symbol, side=side).inc()

    def record_signal(self, strategy: str, signal_type: str) -> None:
        self.strategy_signals.labels(strategy=strategy, signal_type=signal_type).inc()

    def record_data_fetch(self, latency: float) -> None:
        self.data_fetch_latency.observe(latency)

    def record_strategy_execution(self, latency: float) -> None:
        self.strategy_latency.observe(latency)

    def record_risk_metrics(self, var: Decimal, leverage: float, correlation: float) -> None:
        self.risk_var.set(float(var))
        self.risk_leverage.set(leverage)
        self.risk_correlation.set(correlation)


class StructuredLogger:
    def __init__(self, config_path: str | None = None):
        settings = get_settings(config_path)
        self.log_level = settings.monitoring.log_level
        self._setup_logger()

    def _setup_logger(self) -> None:
        logger.remove()
        logger.add(
            lambda msg: sys.stdout.write(msg),
            level=self.log_level,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                "<level>{message}</level>"
            ),
            colorize=True,
        )

    def log_trade(
        self, symbol: str, side: str, quantity: Decimal, price: Decimal, strategy: str
    ) -> None:
        logger.info(
            f"TRADE | {symbol} | {side} | {quantity} @ {price} | Strategy: {strategy}",
            extra={
                "event_type": "trade",
                "symbol": symbol,
                "side": side,
                "quantity": str(quantity),
                "price": str(price),
                "strategy": strategy,
            },
        )

    def log_signal(self, symbol: str, signal_type: str, strength: float, strategy: str) -> None:
        logger.info(
            f"SIGNAL | {symbol} | {signal_type} | Strength: {strength:.2f} | Strategy: {strategy}",
            extra={
                "event_type": "signal",
                "symbol": symbol,
                "signal_type": signal_type,
                "strength": strength,
                "strategy": strategy,
            },
        )

    def log_order(
        self, order_id: str, symbol: str, side: str, status: str, details: str = ""
    ) -> None:
        logger.info(
            f"ORDER | {order_id} | {symbol} | {side} | {status} | {details}",
            extra={
                "event_type": "order",
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "status": status,
                "details": details,
            },
        )

    def log_risk(self, event: str, details: dict[str, Any]) -> None:
        logger.warning(
            f"RISK | {event} | {json.dumps(details)}",
            extra={"event_type": "risk", "risk_event": event, **details},
        )

    def log_error(self, component: str, error: Exception, context: dict[str, Any] = None) -> None:
        logger.error(
            f"ERROR | {component} | {type(error).__name__}: {error}",
            extra={
                "event_type": "error",
                "component": component,
                "error": str(error),
                **(context or {}),
            },
        )

    def log_performance(self, component: str, latency: float, success: bool) -> None:
        logger.debug(
            f"PERF | {component} | {latency:.4f}s | {'OK' if success else 'FAIL'}",
            extra={
                "event_type": "performance",
                "component": component,
                "latency": latency,
                "success": success,
            },
        )


class HealthChecker:
    def __init__(self, config_path: str | None = None):
        settings = get_settings(config_path)
        self.interval = settings.monitoring.health_check_interval
        self._checks: dict[str, Callable[[], Awaitable[bool]]] = {}
        self._running = False
        self._task: asyncio.Task | None = None

    def register_check(self, name: str, check: Callable[[], Awaitable[bool]]) -> None:
        self._checks[name] = check

    async def run_checks(self) -> dict[str, bool]:
        results = {}
        for name, check in self._checks.items():
            try:
                results[name] = await check()
            except Exception as e:
                logger.error(f"Health check '{name}' failed: {e}")
                results[name] = False
        return results

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _monitor_loop(self) -> None:
        while self._running:
            results = await self.run_checks()
            unhealthy = [name for name, ok in results.items() if not ok]
            if unhealthy:
                logger.warning(f"Health check failed for: {unhealthy}")
            await asyncio.sleep(self.interval)


class AlertManager:
    def __init__(self):
        self._alerts: list[dict[str, Any]] = []
        self._handlers: list[Callable[[dict[str, Any]], Awaitable[None]]] = []

    def add_handler(self, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        self._handlers.append(handler)

    async def send_alert(
        self, level: str, title: str, message: str, metadata: dict[str, Any] = None
    ) -> None:
        alert = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "title": title,
            "message": message,
            "metadata": metadata or {},
        }
        self._alerts.append(alert)

        for handler in self._handlers:
            try:
                await handler(alert)
            except Exception as e:
                logger.error(f"Alert handler failed: {e}")

    def get_alerts(
        self, since: datetime | None = None, level: str | None = None
    ) -> list[dict[str, Any]]:
        alerts = self._alerts
        if since:
            alerts = [a for a in alerts if datetime.fromisoformat(a["timestamp"]) >= since]
        if level:
            alerts = [a for a in alerts if a["level"] == level]
        return alerts

    def clear_alerts(self) -> None:
        self._alerts.clear()


@asynccontextmanager
async def monitoring_session(config_path: str | None = None):
    metrics = MetricsCollector(config_path)
    structured_logger = StructuredLogger(config_path)
    health_checker = HealthChecker(config_path)
    alert_manager = AlertManager()

    metrics.start_server()
    await health_checker.start()

    try:
        yield {
            "metrics": metrics,
            "logger": structured_logger,
            "health": health_checker,
            "alerts": alert_manager,
        }
    finally:
        await health_checker.stop()


__all__ = [
    "MetricSnapshot",
    "MetricsCollector",
    "StructuredLogger",
    "HealthChecker",
    "AlertManager",
    "monitoring_session",
    "RiskDashboard",
    "DashboardState",
    "PortfolioState",
    "DashboardMetrics",
    "WebSocketManager",
    "dashboard_session",
    "run_dashboard",
]
