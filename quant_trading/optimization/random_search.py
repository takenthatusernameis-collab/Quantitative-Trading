"""Random search parameter optimization."""

from datetime import datetime

import numpy as np

from .base import BaseOptimizer, OptimizationResult


class RandomSearch(BaseOptimizer):
    """Random search optimizer for strategy parameters.

    Samples random parameter combinations from the parameter space.
    More efficient than grid search for high-dimensional spaces.
    """

    def __init__(
        self,
        n_iter: int = 100,
        random_state: int | None = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.n_iter = n_iter
        self.random_state = random_state
        self._rng = np.random.default_rng(random_state)

    def run(self) -> OptimizationResult:
        """Run random search optimization.

        Returns:
            OptimizationResult with best parameters and all results.
        """
        start_time = datetime.now()
        all_results = []
        best_score = float("-inf")
        best_params = {}
        best_result = None

        combinations = self.param_grid.sample_random(self.n_iter, self._rng)

        if self.verbose:
            print(f"RandomSearch: Evaluating {self.n_iter} random parameter combinations...")

        for i, params in enumerate(combinations):
            if self.verbose:
                print(f"  [{i+1}/{self.n_iter}] {params}")

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
            print(f"\nRandomSearch complete in {(end_time - start_time).total_seconds():.1f}s")
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
