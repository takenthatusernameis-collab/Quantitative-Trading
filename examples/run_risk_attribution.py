"""Example demonstrating risk attribution and decomposition functions."""

import numpy as np
import pandas as pd

from quant_trading.risk.metrics import (
    calculate_component_var,
    calculate_equal_risk_contribution_weights,
    calculate_marginal_var,
    calculate_risk_budget_weights,
    calculate_var,
    calculate_volatility,
    calculate_volatility_contributions,
)


def main():
    np.random.seed(42)

    # Create sample asset returns with realistic correlations
    n_periods = 500
    # Generate correlated returns using a factor model
    market = np.random.normal(0.001, 0.015, n_periods)
    sector_tech = np.random.normal(0, 0.01, n_periods)
    sector_consumer = np.random.normal(0, 0.008, n_periods)

    returns = pd.DataFrame({
        "AAPL": market + 0.5 * sector_tech + np.random.normal(0, 0.01, n_periods),
        "MSFT": market + 0.4 * sector_tech + np.random.normal(0, 0.009, n_periods),
        "GOOGL": market + 0.6 * sector_tech + np.random.normal(0, 0.012, n_periods),
        "AMZN": market + 0.3 * sector_consumer + np.random.normal(0, 0.015, n_periods),
    })

    # Equal-weight portfolio
    weights = pd.Series([0.25, 0.25, 0.25, 0.25], index=returns.columns)

    print("=" * 60)
    print("Risk Attribution Example")
    print("=" * 60)

    # 1. Marginal VaR
    print("\n1. Marginal VaR (95% confidence)")
    print("-" * 40)
    mvar = calculate_marginal_var(returns, weights, confidence=0.95)
    print(mvar.round(6))
    print(f"Sum of Marginal VaR * weights = {(mvar * weights).sum():.6f}")

    # 2. Component VaR
    print("\n2. Component VaR (95% confidence)")
    print("-" * 40)
    cvar = calculate_component_var(returns, weights, confidence=0.95)
    print(cvar.round(6))
    print(f"Sum of Component VaR = {cvar.sum():.6f}")

    # Verify Euler's theorem: sum of component VaR = portfolio VaR
    portfolio_returns = returns.values @ weights.values
    portfolio_var = calculate_var(pd.Series(portfolio_returns), 0.95)
    print(f"Portfolio VaR = {portfolio_var:.6f}")
    print(f"Difference = {abs(cvar.sum() - portfolio_var):.6f}")

    # 3. Volatility Contributions
    print("\n3. Volatility Contributions")
    print("-" * 40)
    vol_contrib = calculate_volatility_contributions(returns, weights, annualize=False)
    print(vol_contrib.round(6))
    print(f"Sum of Vol Contributions = {vol_contrib.sum():.6f}")

    portfolio_vol = calculate_volatility(pd.Series(portfolio_returns), annualize=False)
    print(f"Portfolio Volatility = {portfolio_vol:.6f}")
    print(f"Difference = {abs(vol_contrib.sum() - portfolio_vol):.6f}")

    # 4. Equal Risk Contribution (ERC) Portfolio - Long Only
    print("\n4. Equal Risk Contribution (ERC) Weights (Long Only)")
    print("-" * 40)
    erc_weights = calculate_equal_risk_contribution_weights(returns, annualize=False, long_only=True)
    print(erc_weights.round(6))
    print(f"Sum of weights = {erc_weights.sum():.6f}")
    print(f"All weights >= 0: {(erc_weights >= 0).all()}")

    # Verify equal risk contributions
    erc_contrib = calculate_volatility_contributions(returns, erc_weights, annualize=False)
    print("\nVolatility contributions under ERC:")
    print(erc_contrib.round(6))
    print(f"Range of contributions: {erc_contrib.max() - erc_contrib.min():.6f}")

    # 5. Risk Budgeting Portfolio - Long Only
    print("\n5. Risk Budget Weights (Long Only)")
    print("-" * 40)
    # Target: 40% risk from AAPL, 30% from MSFT, 20% from GOOGL, 10% from AMZN
    risk_budget = pd.Series([0.4, 0.3, 0.2, 0.1], index=returns.columns)
    rb_weights = calculate_risk_budget_weights(returns, risk_budget, annualize=False, long_only=True)
    print("Target risk budget:")
    print(risk_budget.round(6))
    print("\nResulting weights:")
    print(rb_weights.round(6))
    print(f"Sum of weights = {rb_weights.sum():.6f}")
    print(f"All weights >= 0: {(rb_weights >= 0).all()}")

    # Verify risk contributions match budget
    rb_contrib = calculate_volatility_contributions(returns, rb_weights, annualize=False)
    actual_budget = rb_contrib / rb_contrib.sum()
    print("\nActual risk contributions:")
    print(actual_budget.round(6))
    print(f"Max deviation from target: {(actual_budget - risk_budget).abs().max():.6f}")

    # 6. Different confidence levels
    print("\n6. VaR at Different Confidence Levels")
    print("-" * 40)
    for conf in [0.90, 0.95, 0.99]:
        mvar = calculate_marginal_var(returns, weights, confidence=conf)
        cvar = calculate_component_var(returns, weights, confidence=conf)
        print(f"Confidence {conf:.0%}: Component VaR sum = {cvar.sum():.6f}")

    # 7. Correlated assets example
    print("\n7. Correlated Assets Example")
    print("-" * 40)
    n = 500
    base = np.random.normal(0.001, 0.02, n)
    correlated_returns = pd.DataFrame({
        "Asset_A": base + np.random.normal(0, 0.01, n),
        "Asset_B": base + np.random.normal(0, 0.01, n),
        "Asset_C": np.random.normal(0.001, 0.02, n),  # Uncorrelated
    })
    corr_weights = pd.Series([1/3, 1/3, 1/3], index=correlated_returns.columns)

    corr_contrib = calculate_volatility_contributions(correlated_returns, corr_weights, annualize=False)
    print("Volatility contributions with correlated assets:")
    print(corr_contrib.round(6))
    print(f"Sum = {corr_contrib.sum():.6f}")

    # 8. Different volatilities - ERC allocates more to lower vol assets
    print("\n8. ERC with Different Volatilities (Long Only)")
    print("-" * 40)
    diff_vol_returns = pd.DataFrame({
        "Low_Vol": np.random.normal(0.001, 0.01, 500),
        "High_Vol": np.random.normal(0.001, 0.03, 500),
    })
    diff_weights = calculate_equal_risk_contribution_weights(diff_vol_returns, annualize=False, long_only=True)
    print("ERC weights (low vol should get higher weight):")
    print(diff_weights.round(6))
    assert diff_weights["Low_Vol"] > diff_weights["High_Vol"], "Lower vol asset should get higher weight"
    print("✓ Lower volatility asset receives higher weight")

    print("\n" + "=" * 60)
    print("All examples completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()