# ruff: noqa: E501
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from loguru import logger

from qtrading.config import get_settings
from qtrading.risk import PositionSizeResult, RiskMetrics, StressTestResult
from qtrading.strategy import Position

if TYPE_CHECKING:
    from qtrading.monitoring import AlertManager, MetricsCollector, StructuredLogger
    from qtrading.risk import RiskManager


@dataclass
class PortfolioState:
    timestamp: datetime
    total_value: Decimal
    cash: Decimal
    positions: dict[str, dict[str, Any]]
    daily_pnl: Decimal
    total_pnl: Decimal
    drawdown: Decimal
    leverage: float


@dataclass
class DashboardMetrics:
    risk: RiskMetrics
    portfolio: PortfolioState
    alerts: list[dict[str, Any]]
    position_sizing: list[PositionSizeResult]
    stress_tests: list[StressTestResult]


class DashboardState:
    def __init__(self):
        self.portfolio_value: Decimal = Decimal("0")
        self.cash: Decimal = Decimal("0")
        self.positions: dict[str, Position] = {}
        self.positions_dict: dict[str, dict[str, Any]] = {}
        self.price_history: dict[str, Any] = {}
        self.daily_pnl: Decimal = Decimal("0")
        self.total_pnl: Decimal = Decimal("0")
        self.drawdown: Decimal = Decimal("0")
        self.leverage: float = 0.0
        self.risk_metrics: RiskMetrics | None = None
        self.position_sizing_results: list[PositionSizeResult] = []
        self.stress_test_results: list[StressTestResult] = []
        self._last_update: datetime = datetime.now()

    def update_portfolio(
        self,
        value: Decimal,
        cash: Decimal,
        positions: dict[str, Position],
        prices: dict[str, Decimal],
    ) -> None:
        self.portfolio_value = value
        self.cash = cash
        self.positions = positions
        self._last_update = datetime.now()

        pos_dict = {}
        for symbol, pos in positions.items():
            unrealized = "0"
            if hasattr(pos, "entry_price") and pos.entry_price:
                unrealized = str((pos.current_price - pos.entry_price) * pos.quantity)
            pos_dict[symbol] = {
                "quantity": str(pos.quantity),
                "current_price": str(pos.current_price),
                "value": str(abs(pos.quantity) * pos.current_price),
                "unrealized_pnl": unrealized,
            }
        self.positions_dict = pos_dict

    def update_risk_metrics(self, metrics: RiskMetrics) -> None:
        self.risk_metrics = metrics
        self.drawdown = metrics.current_drawdown
        self.daily_pnl = metrics.daily_pnl
        self.leverage = metrics.leverage
        self._last_update = datetime.now()

    def update_position_sizing(self, results: list[PositionSizeResult]) -> None:
        self.position_sizing_results = results
        self._last_update = datetime.now()

    def update_stress_tests(self, results: list[StressTestResult]) -> None:
        self.stress_test_results = results
        self._last_update = datetime.now()

    def get_portfolio_state(self) -> PortfolioState:
        return PortfolioState(
            timestamp=self._last_update,
            total_value=self.portfolio_value,
            cash=self.cash,
            positions=self.positions_dict,
            daily_pnl=self.daily_pnl,
            total_pnl=self.total_pnl,
            drawdown=self.drawdown,
            leverage=self.leverage,
        )


class WebSocketManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict[str, Any]) -> None:
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)

        for conn in dead_connections:
            self.disconnect(conn)

    async def send_personal(self, websocket: WebSocket, message: dict[str, Any]) -> None:
        try:
            await websocket.send_json(message)
        except Exception:
            self.disconnect(websocket)


class RiskDashboard:
    def __init__(self, config_path: str | None = None):
        settings = get_settings(config_path)
        self.config_path = config_path
        self.dashboard_port = getattr(settings.monitoring, "dashboard_port", 8080)
        self.update_interval = getattr(settings.monitoring, "dashboard_update_interval", 5)

        self.state = DashboardState()
        self.ws_manager = WebSocketManager()
        self.risk_manager: RiskManager | None = None
        self.metrics_collector: MetricsCollector | None = None
        self.structured_logger: StructuredLogger | None = None
        self.alert_manager: AlertManager | None = None

        self._running = False
        self._update_task: asyncio.Task | None = None
        self._app = self._create_app()

    def _create_app(self) -> FastAPI:
        app = FastAPI(title="QTrading Risk Dashboard", version="1.0.0")

        @app.get("/")
        async def root() -> HTMLResponse:
            return HTMLResponse(self._get_dashboard_html())

        @app.get("/api/health")
        async def health() -> dict[str, str]:
            return {"status": "healthy", "timestamp": datetime.now().isoformat()}

        @app.get("/api/portfolio")
        async def get_portfolio() -> dict[str, Any]:
            portfolio = self.state.get_portfolio_state()
            return self._portfolio_to_dict(portfolio)

        @app.get("/api/risk")
        async def get_risk() -> dict[str, Any]:
            if self.state.risk_metrics:
                return self._risk_metrics_to_dict(self.state.risk_metrics)
            return {}

        @app.get("/api/position-sizing")
        async def get_position_sizing() -> list[dict[str, Any]]:
            return [
                self._position_size_to_dict(r) for r in self.state.position_sizing_results
            ]

        @app.get("/api/stress-tests")
        async def get_stress_tests() -> list[dict[str, Any]]:
            return [
                self._stress_test_to_dict(r) for r in self.state.stress_test_results
            ]

        @app.get("/api/alerts")
        async def get_alerts(
            since: str | None = None, level: str | None = None
        ) -> list[dict[str, Any]]:
            if not self.alert_manager:
                return []
            since_dt = datetime.fromisoformat(since) if since else None
            return self.alert_manager.get_alerts(since=since_dt, level=level)

        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket) -> None:
            await self.ws_manager.connect(websocket)
            try:
                await websocket.send_json(
                    {
                        "type": "initial_state",
                        "data": {
                            "portfolio": self._portfolio_to_dict(
                                self.state.get_portfolio_state()
                            ),
                            "risk": self._risk_metrics_to_dict(self.state.risk_metrics)
                            if self.state.risk_metrics
                            else {},
                            "position_sizing": [
                                self._position_size_to_dict(r)
                                for r in self.state.position_sizing_results
                            ],
                            "stress_tests": [
                                self._stress_test_to_dict(r)
                                for r in self.state.stress_test_results
                            ],
                        },
                    }
                )
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                self.ws_manager.disconnect(websocket)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                self.ws_manager.disconnect(websocket)

        return app

    def _portfolio_to_dict(self, portfolio: PortfolioState) -> dict[str, Any]:
        return {
            "timestamp": portfolio.timestamp.isoformat(),
            "total_value": str(portfolio.total_value),
            "cash": str(portfolio.cash),
            "positions": portfolio.positions,
            "daily_pnl": str(portfolio.daily_pnl),
            "total_pnl": str(portfolio.total_pnl),
            "drawdown": str(portfolio.drawdown),
            "leverage": portfolio.leverage,
        }

    def _risk_metrics_to_dict(self, metrics: RiskMetrics) -> dict[str, Any]:
        return {
            "current_drawdown": str(metrics.current_drawdown),
            "daily_pnl": str(metrics.daily_pnl),
            "portfolio_var": str(metrics.portfolio_var),
            "max_correlation": metrics.max_correlation,
            "position_count": metrics.position_count,
            "total_exposure": str(metrics.total_exposure),
            "leverage": metrics.leverage,
            "sector_exposure": metrics.sector_exposure,
            "factor_exposure": metrics.factor_exposure,
            "portfolio_beta": metrics.portfolio_beta,
        }

    def _position_size_to_dict(self, result: PositionSizeResult) -> dict[str, Any]:
        return {
            "symbol": result.symbol,
            "recommended_size": str(result.recommended_size),
            "max_size": str(result.max_size),
            "kelly_size": str(result.kelly_size),
            "volatility_target_size": str(result.volatility_target_size),
            "reason": result.reason,
        }

    def _stress_test_to_dict(self, result: StressTestResult) -> dict[str, Any]:
        return {
            "scenario_name": result.scenario_name,
            "initial_capital": result.initial_capital,
            "final_capital": result.final_capital,
            "total_return": result.total_return,
            "max_drawdown": result.max_drawdown,
            "sharpe_ratio": result.sharpe_ratio,
            "recovery_time": result.recovery_time,
        }

    def _get_dashboard_html(self) -> str:  # noqa: E501
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QTrading Risk Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        .metric-card { transition: all 0.3s ease; }
        .metric-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        .positive { color: #10b981; }
        .negative { color: #ef4444; }
        .warning { color: #f59e0b; }
        .ws-status.connected { background-color: #10b981; }
        .ws-status.disconnected { background-color: #ef4444; }
    </style>
</head>
<body class="bg-gray-50 min-h-screen">
    <div class="container mx-auto px-4 py-8">
        <div class="flex justify-between items-center mb-8">
            <h1 class="text-3xl font-bold text-gray-900">QTrading Risk Dashboard</h1>
            <div class="flex items-center gap-4">
                <span id="last-update" class="text-sm text-gray-500">Last update: --</span>
                <div id="ws-status" class="ws-status disconnected w-3 h-3 rounded-full"></div>
                <span id="ws-text" class="text-sm text-gray-500">Disconnected</span>
            </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            <div class="metric-card bg-white rounded-lg shadow p-6">
                <h3 class="text-sm font-medium text-gray-500">Portfolio Value</h3>
                <p id="portfolio-value" class="text-3xl font-bold text-gray-900 mt-1">$0.00</p>
            </div>
            <div class="metric-card bg-white rounded-lg shadow p-6">
                <h3 class="text-sm font-medium text-gray-500">Daily P&L</h3>
                <p id="daily-pnl" class="text-3xl font-bold mt-1">$0.00</p>
            </div>
            <div class="metric-card bg-white rounded-lg shadow p-6">
                <h3 class="text-sm font-medium text-gray-500">Total P&L</h3>
                <p id="total-pnl" class="text-3xl font-bold mt-1">$0.00</p>
            </div>
            <div class="metric-card bg-white rounded-lg shadow p-6">
                <h3 class="text-sm font-medium text-gray-500">Drawdown</h3>
                <p id="drawdown" class="text-3xl font-bold mt-1">0.00%</p>
            </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
            <div class="metric-card bg-white rounded-lg shadow p-6">
                <h3 class="text-sm font-medium text-gray-500">Leverage</h3>
                <p id="leverage" class="text-3xl font-bold text-gray-900 mt-1">0.00x</p>
            </div>
            <div class="metric-card bg-white rounded-lg shadow p-6">
                <h3 class="text-sm font-medium text-gray-500">Portfolio VaR (95%)</h3>
                <p id="var" class="text-3xl font-bold text-gray-900 mt-1">$0.00</p>
            </div>
            <div class="metric-card bg-white rounded-lg shadow p-6">
                <h3 class="text-sm font-medium text-gray-500">Max Correlation</h3>
                <p id="max-corr" class="text-3xl font-bold text-gray-900 mt-1">0.00</p>
            </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
            <div class="bg-white rounded-lg shadow p-6">
                <h3 class="text-lg font-semibold text-gray-900 mb-4">Positions</h3>
                <div class="overflow-x-auto">
                    <table class="w-full">
                        <thead>
                            <tr class="text-left text-sm text-gray-500 border-b">
                                <th class="pb-2">Symbol</th>
                                <th class="pb-2">Quantity</th>
                                <th class="pb-2">Price</th>
                                <th class="pb-2">Value</th>
                                <th class="pb-2">Unrealized P&L</th>
                            </tr>
                        </thead>
                        <tbody id="positions-table" class="text-sm">
                        </tbody>
                    </table>
                </div>
            </div>

            <div class="bg-white rounded-lg shadow p-6">
                <h3 class="text-lg font-semibold text-gray-900 mb-4">Sector Exposure</h3>
                <div id="sector-exposure" class="space-y-3">
                </div>
            </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
            <div class="bg-white rounded-lg shadow p-6">
                <h3 class="text-lg font-semibold text-gray-900 mb-4">Position Sizing Recommendations</h3>  # noqa: E501
                <div class="overflow-x-auto">
                    <table class="w-full">
                        <thead>
                            <tr class="text-left text-sm text-gray-500 border-b">
                                <th class="pb-2">Symbol</th>
                                <th class="pb-2">Recommended</th>
                                <th class="pb-2">Max Size</th>
                                <th class="pb-2">Kelly</th>
                                <th class="pb-2">Vol Target</th>
                                <th class="pb-2">Method</th>
                            </tr>
                        </thead>
                        <tbody id="position-sizing-table" class="text-sm">
                        </tbody>
                    </table>
                </div>
            </div>

            <div class="bg-white rounded-lg shadow p-6">
                <h3 class="text-lg font-semibold text-gray-900 mb-4">Stress Test Results</h3>
                <div class="overflow-x-auto">
                    <table class="w-full">
                        <thead>
                            <tr class="text-left text-sm text-gray-500 border-b">
                                <th class="pb-2">Scenario</th>
                                <th class="pb-2">Return</th>
                                <th class="pb-2">Max DD</th>
                                <th class="pb-2">Sharpe</th>
                                <th class="pb-2">Recovery</th>
                            </tr>
                        </thead>
                        <tbody id="stress-tests-table" class="text-sm">
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <div class="bg-white rounded-lg shadow p-6 mb-8">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Recent Alerts</h3>
            <div id="alerts-list" class="space-y-2 max-h-60 overflow-y-auto">
            </div>
        </div>
    </div>

    <script>
        let ws = null;
        let reconnectAttempts = 0;
        const maxReconnectAttempts = 10;
        const reconnectDelay = 5000;

        function connect() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

            ws.onopen = () => {
                console.log('WebSocket connected');
                updateWsStatus(true);
                reconnectAttempts = 0;
            };

            ws.onmessage = (event) => {
                const msg = JSON.parse(event.data);
                if (msg.type === 'initial_state' || msg.type === 'update') {
                    updateDashboard(msg.data);
                }
            };

            ws.onclose = () => {
                console.log('WebSocket disconnected');
                updateWsStatus(false);
                if (reconnectAttempts < maxReconnectAttempts) {
                    reconnectAttempts++;
                    setTimeout(connect, reconnectDelay);
                }
            };

            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
        }

        function updateWsStatus(connected) {
            const statusEl = document.getElementById('ws-status');
            const textEl = document.getElementById('ws-text');
            if (connected) {
                statusEl.classList.remove('disconnected');
                statusEl.classList.add('connected');
                textEl.textContent = 'Connected';
            } else {
                statusEl.classList.remove('connected');
                statusEl.classList.add('disconnected');
                textEl.textContent = 'Disconnected';
            }
        }

        function fmtValue(val, decimals = 2) {
            return parseFloat(val).toLocaleString(undefined, {
                minimumFractionDigits: decimals,
                maximumFractionDigits: decimals,
            });
        }

        function updateDashboard(data) {
            document.getElementById('last-update').textContent =
                'Last update: ' + new Date().toLocaleTimeString();

            if (data.portfolio) {
                const p = data.portfolio;
                document.getElementById('portfolio-value').textContent = '$' + fmtValue(p.total_value);  # noqa: E501
                document.getElementById('daily-pnl').textContent = '$' + fmtValue(p.daily_pnl);
                document.getElementById('daily-pnl').className = 'text-3xl font-bold mt-1 ' +
                    (parseFloat(p.daily_pnl) >= 0 ? 'positive' : 'negative');
                document.getElementById('total-pnl').textContent = '$' + fmtValue(p.total_pnl);
                document.getElementById('total-pnl').className = 'text-3xl font-bold mt-1 ' +
                    (parseFloat(p.total_pnl) >= 0 ? 'positive' : 'negative');
                document.getElementById('drawdown').textContent =
                    (parseFloat(p.drawdown) * 100).toFixed(2) + '%';
                const dd = parseFloat(p.drawdown);
                document.getElementById('drawdown').className = 'text-3xl font-bold mt-1 ' +
                    (dd > 0.1 ? 'negative' : dd > 0.05 ? 'warning' : 'positive');
                document.getElementById('leverage').textContent = p.leverage.toFixed(2) + 'x';

                const tbody = document.getElementById('positions-table');
                tbody.innerHTML = '';
                for (const [symbol, pos] of Object.entries(p.positions)) {
                    const pnl = parseFloat(pos.unrealized_pnl || 0);
                    const row = document.createElement('tr');
                    row.className = 'border-b';
                    row.innerHTML = `
                        <td class="py-2 font-mono">${symbol}</td>
                        <td class="py-2">${parseFloat(pos.quantity).toFixed(4)}</td>
                        <td class="py-2">$${parseFloat(pos.current_price).toFixed(2)}</td>
                        <td class="py-2">$${parseFloat(pos.value).toLocaleString(undefined, {minimumFractionDigits: 2})}</td>  # noqa: E501
                        <td class="py-2 ${pnl >= 0 ? 'positive' : 'negative'}">$${pnl.toLocaleString(undefined, {minimumFractionDigits: 2})}</td>  # noqa: E501
                    `;
                    tbody.appendChild(row);
                }
            }

            if (data.risk) {
                const r = data.risk;
                document.getElementById('var').textContent = '$' + fmtValue(r.portfolio_var);
                document.getElementById('max-corr').textContent = r.max_correlation.toFixed(2);

                const sectorDiv = document.getElementById('sector-exposure');
                sectorDiv.innerHTML = '';
                for (const [sector, exposure] of Object.entries(r.sector_exposure || {})) {
                    const pct = (exposure * 100).toFixed(1);
                    const barColor = exposure > 0.3 ? 'bg-red-500' :
                        exposure > 0.2 ? 'bg-yellow-500' : 'bg-green-500';
                    sectorDiv.innerHTML += `
                        <div>
                            <div class="flex justify-between text-sm mb-1">
                                <span>${sector}</span>
                                <span>${pct}%</span>
                            </div>
                            <div class="h-2 bg-gray-200 rounded-full overflow-hidden">
                                <div class="${barColor} h-full rounded-full" style="width: ${Math.min(exposure * 300, 100)}%"></div>  # noqa: E501
                            </div>
                        </div>
                    `;
                }
            }

            if (data.position_sizing) {
                const tbody = document.getElementById('position-sizing-table');
                tbody.innerHTML = '';
                for (const item of data.position_sizing) {
                    const row = document.createElement('tr');
                    row.className = 'border-b';
                    row.innerHTML = `
                        <td class="py-2 font-mono">${item.symbol}</td>
                        <td class="py-2">${parseFloat(item.recommended_size).toFixed(4)}</td>
                        <td class="py-2">${parseFloat(item.max_size).toFixed(4)}</td>
                        <td class="py-2">${parseFloat(item.kelly_size).toFixed(4)}</td>
                        <td class="py-2">${parseFloat(item.volatility_target_size).toFixed(4)}</td>
                        <td class="py-2 text-gray-600">${item.reason}</td>
                    `;
                    tbody.appendChild(row);
                }
            }

            if (data.stress_tests) {
                const tbody = document.getElementById('stress-tests-table');
                tbody.innerHTML = '';
                for (const item of data.stress_tests) {
                    const row = document.createElement('tr');
                    row.className = 'border-b';
                    const returnClass = item.total_return >= 0 ? 'positive' : 'negative';
                    row.innerHTML = `
                        <td class="py-2 font-mono">${item.scenario_name}</td>
                        <td class="py-2 ${returnClass}">${(item.total_return * 100).toFixed(2)}%</td>  # noqa: E501
                        <td class="py-2">${(item.max_drawdown * 100).toFixed(2)}%</td>
                        <td class="py-2">${item.sharpe_ratio.toFixed(2)}</td>
                        <td class="py-2">${item.recovery_time ? item.recovery_time + ' days' : 'N/A'}</td>  # noqa: E501
                    `;
                    tbody.appendChild(row);
                }
            }

            if (data.alerts) {
                const alertsDiv = document.getElementById('alerts-list');
                alertsDiv.innerHTML = '';
                for (const alert of data.alerts.slice(-20).reverse()) {
                    const levelClass = alert.level === 'critical' ? 'bg-red-100 text-red-800' :
                        alert.level === 'warning' ? 'bg-yellow-100 text-yellow-800' :
                        'bg-blue-100 text-blue-800';
                    alertsDiv.innerHTML += `
                        <div class="p-3 rounded ${levelClass} text-sm">
                            <div class="flex justify-between">
                                <span class="font-medium">${alert.title}</span>
                                <span>${new Date(alert.timestamp).toLocaleTimeString()}</span>
                            </div>
                            <div class="mt-1">${alert.message}</div>
                        </div>
                    `;
                }
            }
        }

        async function fetchAlerts() {
            try {
                const response = await fetch('/api/alerts');
                const alerts = await response.json();
                const alertsDiv = document.getElementById('alerts-list');
                alertsDiv.innerHTML = '';
                for (const alert of alerts.slice(-20).reverse()) {
                    const levelClass = alert.level === 'critical' ? 'bg-red-100 text-red-800' :
                        alert.level === 'warning' ? 'bg-yellow-100 text-yellow-800' :
                        'bg-blue-100 text-blue-800';
                    alertsDiv.innerHTML += `
                        <div class="p-3 rounded ${levelClass} text-sm">
                            <div class="flex justify-between">
                                <span class="font-medium">${alert.title}</span>
                                <span>${new Date(alert.timestamp).toLocaleTimeString()}</span>
                            </div>
                            <div class="mt-1">${alert.message}</div>
                        </div>
                    `;
                }
            } catch (e) {
                console.error('Failed to fetch alerts:', e);
            }
        }

        connect();
        fetchAlerts();
        setInterval(fetchAlerts, 30000);
    </script>
</body>
</html>
        """

    def set_risk_manager(self, risk_manager: RiskManager) -> None:
        self.risk_manager = risk_manager

    def set_metrics_collector(self, collector: MetricsCollector) -> None:
        self.metrics_collector = collector

    def set_structured_logger(self, logger: StructuredLogger) -> None:
        self.structured_logger = logger

    def set_alert_manager(self, alert_manager: AlertManager) -> None:
        self.alert_manager = alert_manager

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._update_task = asyncio.create_task(self._update_loop())
        logger.info("Risk dashboard started")

    async def stop(self) -> None:
        self._running = False
        if self._update_task:
            self._update_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._update_task
        logger.info("Risk dashboard stopped")

    async def _update_loop(self) -> None:
        while self._running:
            try:
                await self._broadcast_update()
            except Exception as e:
                logger.error(f"Dashboard update error: {e}")
            await asyncio.sleep(self.update_interval)

    async def _broadcast_update(self) -> None:
        portfolio_dict = self._portfolio_to_dict(self.state.get_portfolio_state())
        risk_dict = (
            self._risk_metrics_to_dict(self.state.risk_metrics)
            if self.state.risk_metrics
            else {}
        )
        position_sizing = [
            self._position_size_to_dict(r) for r in self.state.position_sizing_results
        ]
        stress_tests = [
            self._stress_test_to_dict(r) for r in self.state.stress_test_results
        ]
        alerts = self.alert_manager.get_alerts() if self.alert_manager else []

        data = {
            "type": "update",
            "data": {
                "portfolio": portfolio_dict,
                "risk": risk_dict,
                "position_sizing": position_sizing,
                "stress_tests": stress_tests,
                "alerts": alerts,
            },
        }
        await self.ws_manager.broadcast(data)

    def update_from_risk_manager(
        self,
        portfolio_value: Decimal,
        cash: Decimal,
        positions: dict[str, Position],
        prices: dict[str, Decimal],
        price_history: dict[str, Any],
    ) -> None:
        self.state.update_portfolio(portfolio_value, cash, positions, prices)

        if self.risk_manager:
            self.risk_manager.reset_daily(portfolio_value, datetime.now())
            self.risk_manager.update_peak(portfolio_value)

            metrics = self.risk_manager.get_metrics(portfolio_value, positions, price_history)
            self.state.update_risk_metrics(metrics)

            if self.metrics_collector:
                self.metrics_collector.record_risk_metrics(
                    metrics.portfolio_var, metrics.leverage, metrics.max_correlation
                )

    def add_position_sizing(self, results: list[PositionSizeResult]) -> None:
        self.state.update_position_sizing(results)

    def add_stress_test(self, result: StressTestResult) -> None:
        self.state.stress_test_results.append(result)
        self.state._last_update = datetime.now()

    def get_app(self) -> FastAPI:
        return self._app


@asynccontextmanager
async def dashboard_session(config_path: str | None = None) -> AsyncIterator[RiskDashboard]:
    dashboard = RiskDashboard(config_path)
    await dashboard.start()
    try:
        yield dashboard
    finally:
        await dashboard.stop()


def run_dashboard(
    config_path: str | None = None, host: str = "0.0.0.0", port: int | None = None
) -> None:
    import uvicorn

    dashboard = RiskDashboard(config_path)
    app = dashboard.get_app()

    if port is None:
        settings = get_settings(config_path)
        port = getattr(settings.monitoring, "dashboard_port", 8080)

    async def startup() -> None:
        await dashboard.start()

    async def shutdown() -> None:
        await dashboard.stop()

    app.router.on_startup.append(startup)
    app.router.on_shutdown.append(shutdown)

    uvicorn.run(app, host=host, port=port, log_level="info")
