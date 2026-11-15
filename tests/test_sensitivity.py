"""Tests for parameter sensitivity analysis."""

import pytest

from quant_trading.optimization.sensitivity import (
    SensitivityConfig,
    create_1d_sensitivity_plot,
    create_2d_sensitivity_heatmap,
    create_parameter_interaction_heatmap,
    generate_sensitivity_report_html,
    prepare_sensitivity_data,
)


class TestPrepareSensitivityData:
    """Tests for prepare_sensitivity_data function."""

    def test_prepare_sensitivity_data_basic(self):
        """Test basic data preparation from grid search results."""
        all_results = [
            {"params": {"fast_period": 5, "slow_period": 20}, "score": 1.5},
            {"params": {"fast_period": 10, "slow_period": 20}, "score": 2.0},
            {"params": {"fast_period": 5, "slow_period": 30}, "score": 1.0},
        ]
        df = prepare_sensitivity_data(all_results)
        assert len(df) == 3
        assert "fast_period" in df.columns
        assert "slow_period" in df.columns
        assert "score" in df.columns
        assert df["score"].tolist() == [1.5, 2.0, 1.0]

    def test_prepare_sensitivity_data_with_param_names(self):
        """Test data preparation with specific parameter names."""
        all_results = [
            {"params": {"fast_period": 5, "slow_period": 20, "extra": 1}, "score": 1.5},
            {"params": {"fast_period": 10, "slow_period": 20, "extra": 2}, "score": 2.0},
        ]
        df = prepare_sensitivity_data(all_results, param_names=["fast_period"])
        assert "fast_period" in df.columns
        assert "slow_period" not in df.columns
        assert "extra" not in df.columns

    def test_prepare_sensitivity_data_empty(self):
        """Test data preparation with empty results."""
        df = prepare_sensitivity_data([])
        assert df.empty

    def test_prepare_sensitivity_data_custom_score_key(self):
        """Test data preparation with custom score key."""
        all_results = [
            {"params": {"fast_period": 5}, "sharpe": 1.5},
            {"params": {"fast_period": 10}, "sharpe": 2.0},
        ]
        df = prepare_sensitivity_data(all_results, score_key="sharpe")
        assert df["score"].tolist() == [1.5, 2.0]


class TestCreate1DSensitivityPlot:
    """Tests for create_1d_sensitivity_plot function."""

    def test_create_1d_sensitivity_plot_basic(self):
        """Test basic 1D sensitivity plot generation."""
        import pandas as pd

        df = pd.DataFrame(
            {
                "fast_period": [5, 5, 10, 10, 15, 15],
                "score": [1.0, 1.2, 2.0, 1.8, 1.5, 1.6],
            }
        )
        chart = create_1d_sensitivity_plot(df, "fast_period", "score")
        assert isinstance(chart, str)
        assert len(chart) > 0

    def test_create_1d_sensitivity_plot_missing_column(self):
        """Test error when required column is missing."""
        import pandas as pd

        df = pd.DataFrame({"fast_period": [5, 10], "score": [1.0, 2.0]})
        with pytest.raises(ValueError, match="Required columns not found"):
            create_1d_sensitivity_plot(df, "missing_param", "score")


class TestCreate2DSensitivityHeatmap:
    """Tests for create_2d_sensitivity_heatmap function."""

    def test_create_2d_sensitivity_heatmap_basic(self):
        """Test basic 2D sensitivity heatmap generation."""
        import pandas as pd

        df = pd.DataFrame(
            {
                "fast_period": [5, 5, 10, 10],
                "slow_period": [20, 30, 20, 30],
                "score": [1.0, 1.2, 2.0, 1.8],
            }
        )
        chart = create_2d_sensitivity_heatmap(df, "fast_period", "slow_period", "score")
        assert isinstance(chart, str)
        assert len(chart) > 0

    def test_create_2d_sensitivity_heatmap_missing_column(self):
        """Test error when required column is missing."""
        import pandas as pd

        df = pd.DataFrame({"fast_period": [5, 10], "score": [1.0, 2.0]})
        with pytest.raises(ValueError, match="Required columns not found"):
            create_2d_sensitivity_heatmap(df, "fast_period", "missing_param", "score")


class TestCreateParameterInteractionHeatmap:
    """Tests for create_parameter_interaction_heatmap function."""

    def test_create_parameter_interaction_heatmap_basic(self):
        """Test basic parameter interaction heatmap generation."""
        import numpy as np
        import pandas as pd

        np.random.seed(42)
        df = pd.DataFrame(
            {
                "param1": np.repeat([1, 2, 3], 4),
                "param2": np.tile([10, 20, 30, 40], 3),
                "score": np.random.rand(12),
            }
        )
        chart = create_parameter_interaction_heatmap(df, ["param1", "param2"], "score")
        assert isinstance(chart, str)
        assert len(chart) > 0

    def test_create_parameter_interaction_heatmap_insufficient_params(self):
        """Test error when fewer than 2 parameters provided."""
        import pandas as pd

        df = pd.DataFrame({"param1": [1, 2], "score": [1.0, 2.0]})
        with pytest.raises(ValueError, match="At least 2 parameters required"):
            create_parameter_interaction_heatmap(df, ["param1"], "score")


class TestGenerateSensitivityReportHTML:
    """Tests for generate_sensitivity_report_html function."""

    def test_generate_sensitivity_report_html_basic(self):
        """Test basic HTML report generation."""
        all_results = [
            {"params": {"fast_period": 5, "slow_period": 20}, "score": 1.5},
            {"params": {"fast_period": 10, "slow_period": 20}, "score": 2.0},
            {"params": {"fast_period": 5, "slow_period": 30}, "score": 1.0},
        ]
        html = generate_sensitivity_report_html(all_results)
        assert isinstance(html, str)
        assert "Parameter Sensitivity Analysis" in html
        assert "fast_period" in html
        assert "slow_period" in html

    def test_generate_sensitivity_report_html_empty(self):
        """Test HTML report generation with empty results."""
        html = generate_sensitivity_report_html([])
        assert "No data for sensitivity analysis" in html

    def test_generate_sensitivity_report_html_with_output_path(self, tmp_path):
        """Test HTML report generation with output path."""
        all_results = [
            {"params": {"fast_period": 5, "slow_period": 20}, "score": 1.5},
            {"params": {"fast_period": 10, "slow_period": 20}, "score": 2.0},
        ]
        output_path = tmp_path / "sensitivity_report.html"
        html = generate_sensitivity_report_html(all_results, output_path=str(output_path))
        assert output_path.exists()
        assert output_path.read_text() == html


class TestSensitivityConfig:
    """Tests for SensitivityConfig dataclass."""

    def test_sensitivity_config_defaults(self):
        """Test default configuration values."""
        config = SensitivityConfig()
        assert config.include_charts is True
        assert config.dpi == 150
        assert config.colormap == "RdYlGn"
        assert config.figure_size == (10, 6)

    def test_sensitivity_config_custom(self):
        """Test custom configuration values."""
        config = SensitivityConfig(
            include_charts=False,
            dpi=300,
            colormap="viridis",
            figure_size=(12, 8),
        )
        assert config.include_charts is False
        assert config.dpi == 300
        assert config.colormap == "viridis"
        assert config.figure_size == (12, 8)
