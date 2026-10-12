"""Grid search parameter optimization."""

from datetime import datetime

from .base import BaseOptimizer, OptimizationResult


class GridSearch(BaseOptimizer):
    """Grid search optimizer for strategy parameters.

    Exhaustively searches all parameter combinations in the grid.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._combinations = self.param_grid.generate_combinations()

    def run(self) -> OptimizationResult:
        """Run grid search optimization.

        Returns:
            OptimizationResult with best parameters and all results.
        """
        start_time = datetime.now()
        all_results = []
        best_score = float("-inf")
        best_params = {}
        best_result = None

        total = len(self._combinations)
        if self.verbose:
            print(f"GridSearch: Evaluating {total} parameter combinations...")

        for i, params in enumerate(self._combinations):
            if self.verbose:
                print(f"  [{i+1}/{total}] {params}")

            params, score, result = self._evaluate_params(params)

            all_results.append(
                {
                    "params": params,
                    "score": score,
                    "total_return_pct": result.total_return_pct if result else None,
                    "sharpe_ratio": result.metrics.sharpe_ratio if result else None,
                    "max_drawdown_pct": result.metrics.max_drawdown_pct if result else None,
                    "win_rate": result.metrics.win_rate if result else None,
                    "profit_factor": result.metrics.profit_factor if result else None,
                    "num_trades": result.metrics.num_trades if result else None,
                }
            )

            if score > best_score:
                best_score = score
                best_params = params
                best_result = result
                if self.verbose:
                    print(f"    -> New best: {score:.4f}")

        end_time = datetime.now()

        if self.verbose:
            print(f"\nGridSearch complete in {(end_time - start_time).total_seconds():.1f}s")
            print(f"Best parameters: {best_params}")
            print(f"Best score: {best_score:.4f}")

        return OptimizationResult(
            best_params=best_params,
            best_score=best_score,
            best_result=best_result,
            all_results=all_results,
            start_time=start_time,
            end_time=end_time,
        )

    @property
    def n_combinations(self) -> int:
        """Total number of parameter combinations."""
        return len(self._combinations)
