"""Tests for parameter sensitivity analysis."""

import pytest

from quant_trading.optimization.sensitivity import (
    MATPLOTLIB_AVAILABLE,
    SensitivityConfig,
    create_1d_sensitivity_plot,
    create_2d_sensitivity_heatmap,
    create_parameter_interaction_heatmap,
    generate_sensitivity_report_html,
    prepare_sensitivity_data,
)

requires_matplotlib = pytest.mark.skipif(
    not MATPLOTLIB_AVAILABLE,
    reason="matplotlib not installed; install the optional 'reporting' extra",
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

    def test_prepare_sensitivity_data_skips_results_without_params(self):
        """Results without a ``params`` entry are skipped, not crashed on."""
        all_results = [
            {"score": 1.0},
            {"params": {"fast_period": 5}, "score": 2.0},
        ]
        df = prepare_sensitivity_data(all_results)
        assert len(df) == 1
        assert df["fast_period"].tolist() == [5]

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

    @requires_matplotlib
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

    @requires_matplotlib
    def test_create_1d_sensitivity_plot_missing_column(self):
        """Test error when required column is missing."""
        import pandas as pd

        df = pd.DataFrame({"fast_period": [5, 10], "score": [1.0, 2.0]})
        with pytest.raises(ValueError, match="Required columns not found"):
            create_1d_sensitivity_plot(df, "missing_param", "score")


class TestCreate2DSensitivityHeatmap:
    """Tests for create_2d_sensitivity_heatmap function."""

    @requires_matplotlib
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

    @requires_matplotlib
    def test_create_2d_sensitivity_heatmap_missing_column(self):
        """Test error when required column is missing."""
        import pandas as pd

        df = pd.DataFrame({"fast_period": [5, 10], "score": [1.0, 2.0]})
        with pytest.raises(ValueError, match="Required columns not found"):
            create_2d_sensitivity_heatmap(df, "fast_period", "missing_param", "score")


class TestCreateParameterInteractionHeatmap:
    """Tests for create_parameter_interaction_heatmap function."""

    @requires_matplotlib
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

    @requires_matplotlib
    def test_create_parameter_interaction_heatmap_insufficient_params(self):
        """Test error when fewer than 2 parameters provided."""
        import pandas as pd

        df = pd.DataFrame({"param1": [1, 2], "score": [1.0, 2.0]})
        with pytest.raises(ValueError, match="At least 2 parameters required"):
            create_parameter_interaction_heatmap(df, ["param1"], "score")

    @requires_matplotlib
    def test_create_parameter_interaction_heatmap_missing_param_column(self):
        """A missing parameter column is a ValueError naming the column.

        The sibling ``create_1d_sensitivity_plot`` and
        ``create_2d_sensitivity_heatmap`` already validate their columns and
        raise ``ValueError``; this function has to behave the same way instead
        of letting a raw ``KeyError`` escape from ``groupby``.
        """
        import pandas as pd

        df = pd.DataFrame(
            {
                "param1": [1, 1, 2, 2],
                "param2": [10, 20, 10, 20],
                "score": [1.0, 3.0, 4.0, 4.0],
            }
        )
        with pytest.raises(ValueError, match="Required columns not found: missing"):
            create_parameter_interaction_heatmap(df, ["param1", "param2", "missing"], "score")

    @requires_matplotlib
    def test_create_parameter_interaction_heatmap_missing_score_column(self):
        """A missing score column is a ValueError naming the column."""
        import pandas as pd

        df = pd.DataFrame({"param1": [1, 1, 2, 2], "param2": [10, 20, 10, 20]})
        with pytest.raises(ValueError, match="Required columns not found: score"):
            create_parameter_interaction_heatmap(df, ["param1", "param2"], "score")

    @requires_matplotlib
    def test_create_parameter_interaction_heatmap_single_value_diagonal(self):
        """A parameter with a single value yields a zero diagonal entry."""
        import pandas as pd

        df = pd.DataFrame(
            {
                "param1": [1, 1, 1, 1],
                "param2": [10, 20, 10, 20],
                "score": [1.0, 2.0, 3.0, 4.0],
            }
        )
        chart = create_parameter_interaction_heatmap(df, ["param1", "param2"], "score")
        assert isinstance(chart, str)
        assert len(chart) > 0

    @requires_matplotlib
    def test_create_parameter_interaction_heatmap_all_nan_scores(self):
        """An all-NaN score column yields an empty pivot and NaN interaction cells.

        ``pivot_table`` drops NaN rows, so the off-diagonal pivot is empty and
        the interaction entry stays NaN instead of raising.
        """
        import numpy as np
        import pandas as pd

        df = pd.DataFrame(
            {
                "param1": [1, 1, 2, 2],
                "param2": [10, 20, 10, 20],
                "score": [np.nan, np.nan, np.nan, np.nan],
            }
        )
        chart = create_parameter_interaction_heatmap(df, ["param1", "param2"], "score")
        assert isinstance(chart, str)
        assert len(chart) > 0

    @requires_matplotlib
    def test_create_parameter_interaction_heatmap_pivot_table_failure(self, monkeypatch):
        """A failing ``pivot_table`` leaves the interaction cell NaN instead of crashing.

        The off-diagonal branch catches ``ValueError``/``KeyError``/``IndexError``
        raised by ``DataFrame.pivot_table`` (quant_trading/optimization/sensitivity.py:362-363)
        and records NaN for that parameter pair rather than propagating the error.
        """
        import pandas as pd

        df = pd.DataFrame(
            {
                "param1": [1, 1, 2, 2],
                "param2": [10, 20, 10, 20],
                "score": [1.0, 3.0, 4.0, 4.0],
            }
        )

        def _raise_pivot_table(self, *args, **kwargs):
            raise ValueError("pivot_table failure")

        monkeypatch.setattr(pd.DataFrame, "pivot_table", _raise_pivot_table)

        chart = create_parameter_interaction_heatmap(df, ["param1", "param2"], "score")
        assert isinstance(chart, str)
        assert len(chart) > 0


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

    def test_generate_sensitivity_report_html_include_charts_false(self):
        """With charts disabled the report has a summary but no images."""
        all_results = [
            {"params": {"fast_period": 5, "slow_period": 20}, "score": 1.5},
            {"params": {"fast_period": 10, "slow_period": 20}, "score": 2.0},
        ]
        html = generate_sensitivity_report_html(
            all_results, config=SensitivityConfig(include_charts=False)
        )
        assert "Summary Statistics" in html
        assert "<img" not in html

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

    def test_generate_sensitivity_report_html_explicit_single_param(self):
        """An explicit single-parameter list skips the 2D and interaction charts."""
        all_results = [
            {"params": {"fast_period": 5, "slow_period": 20}, "score": 1.5},
            {"params": {"fast_period": 10, "slow_period": 20}, "score": 2.0},
        ]
        html = generate_sensitivity_report_html(all_results, param_names=["fast_period"])
        assert "Summary Statistics" in html
        assert "1D Sensitivity: fast_period" in html
        assert "2D Sensitivity" not in html
        assert "Parameter Interactions" not in html

    def test_generate_sensitivity_report_html_custom_score_key(self):
        """A custom score_key does not crash report generation.

        ``prepare_sensitivity_data`` always stores the score under the literal
        column name ``"score"`` regardless of the caller's ``score_key``. The
        report generator must therefore reference that column name (not
        ``score_key``) for its DataFrame operations; otherwise a non-default
        ``score_key`` raises ``KeyError`` and aborts the whole report.
        """
        all_results = [
            {"params": {"fast_period": 5, "slow_period": 20}, "sharpe": 1.5},
            {"params": {"fast_period": 10, "slow_period": 20}, "sharpe": 2.0},
            {"params": {"fast_period": 5, "slow_period": 30}, "sharpe": 1.0},
        ]
        html = generate_sensitivity_report_html(all_results, score_key="sharpe")
        assert "Summary Statistics" in html
        assert "1D Sensitivity: fast_period" in html
        assert "1D Sensitivity: slow_period" in html
        assert "2D Sensitivity: fast_period vs slow_period" in html

    def test_generate_sensitivity_report_html_survives_chart_errors(self, monkeypatch):
        """A failing chart helper is skipped without aborting the report.

        The report is a best-effort aggregation: if any single chart cannot be
        rendered, the remaining charts and the summary table are still produced.
        """
        from quant_trading.optimization import sensitivity

        all_results = [
            {"params": {"fast_period": 5, "slow_period": 20}, "score": 1.5},
            {"params": {"fast_period": 10, "slow_period": 20}, "score": 2.0},
            {"params": {"fast_period": 5, "slow_period": 30}, "score": 1.0},
        ]

        def _boom(*args, **kwargs):
            raise ValueError("chart failure")

        monkeypatch.setattr(sensitivity, "create_1d_sensitivity_plot", _boom)
        monkeypatch.setattr(sensitivity, "create_2d_sensitivity_heatmap", _boom)
        monkeypatch.setattr(sensitivity, "create_parameter_interaction_heatmap", _boom)

        html = generate_sensitivity_report_html(all_results)
        assert "Summary Statistics" in html
        assert "<img" not in html


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

    def test_sensitivity_config_to_dict(self):
        """A config serializes to a JSON-safe dictionary with a list figure size."""
        config = SensitivityConfig(
            include_charts=False,
            dpi=300,
            colormap="viridis",
            figure_size=(12, 8),
        )
        assert config.to_dict() == {
            "include_charts": False,
            "dpi": 300,
            "colormap": "viridis",
            "figure_size": [12, 8],
        }

    def test_sensitivity_config_from_dict_keeps_tuple(self):
        """A tuple figure size round-trips unchanged."""
        restored = SensitivityConfig.from_dict({"figure_size": (12, 8)})
        assert restored.figure_size == (12, 8)

    def test_sensitivity_config_from_dict_converts_list(self):
        """A list figure size is converted to a tuple."""
        restored = SensitivityConfig.from_dict({"figure_size": [12, 8]})
        assert restored.figure_size == (12, 8)


class TestMatplotlibUnavailable:
    """Tests for the guard that runs when matplotlib is missing."""

    def test_chart_generation_requires_matplotlib(self, monkeypatch):
        """Without matplotlib the chart helpers raise a helpful ImportError."""
        import pandas as pd

        from quant_trading.optimization import sensitivity

        monkeypatch.setattr(sensitivity, "MATPLOTLIB_AVAILABLE", False)
        df = pd.DataFrame({"fast_period": [5, 10], "score": [1.0, 2.0]})
        with pytest.raises(ImportError, match="matplotlib is required"):
            create_1d_sensitivity_plot(df, "fast_period", "score")

    def test_import_fallback_when_matplotlib_missing(self):
        """A failed matplotlib import flips MATPLOTLIB_AVAILABLE to False.

        ``sensitivity`` probes matplotlib at import time and falls back to
        chart-free operation when the import raises ``ImportError``
        (quant_trading/optimization/sensitivity.py:16-24). That fallback arm
        only runs when the import itself fails, so this test hides matplotlib
        in ``sys.modules`` (``None`` there makes ``import matplotlib`` raise
        ``ImportError``), reloads the module, and restores the original state
        afterwards so the rest of the suite sees the normal module.
        """
        import importlib
        import sys

        import pandas as pd

        from quant_trading.optimization import sensitivity

        missing = object()
        previous = sys.modules.get("matplotlib", missing)
        sys.modules["matplotlib"] = None
        try:
            reloaded = importlib.reload(sensitivity)
            assert reloaded.MATPLOTLIB_AVAILABLE is False
            # The chart helpers refuse cleanly through the import-time flag.
            df = pd.DataFrame({"fast_period": [5, 10], "score": [1.0, 2.0]})
            with pytest.raises(ImportError, match="matplotlib is required"):
                reloaded.create_1d_sensitivity_plot(df, "fast_period", "score")
        finally:
            if previous is missing:
                del sys.modules["matplotlib"]
            else:
                sys.modules["matplotlib"] = previous
            # Restore the module's normal (matplotlib-probing) state.
            importlib.reload(sensitivity)


class TestSensitivityReportHtmlStructure:
    """Tests for generate_sensitivity_report_html structural guarantees."""

    def test_generate_sensitivity_report_html_headings_per_section_when_charts_fail(
        self, monkeypatch
    ):
        """Each documented analysis section gets an <h3> even when all charts error.

        The report documents every section (1D per param, 2D per pair, interactions)
        regardless of whether the chart helper succeeds. This test asserts that
        every section title appears as an <h3> and no <img> tags are present.
        """
        from quant_trading.optimization import sensitivity

        all_results = [
            {"params": {"fast_period": 5, "slow_period": 20}, "score": 1.5},
            {"params": {"fast_period": 10, "slow_period": 20}, "score": 2.0},
            {"params": {"fast_period": 5, "slow_period": 30}, "score": 1.0},
            {"params": {"fast_period": 10, "slow_period": 30}, "score": 1.8},
        ]

        def _boom(*args, **kwargs):
            raise ValueError("chart failure")

        monkeypatch.setattr(sensitivity, "create_1d_sensitivity_plot", _boom)
        monkeypatch.setattr(sensitivity, "create_2d_sensitivity_heatmap", _boom)
        monkeypatch.setattr(sensitivity, "create_parameter_interaction_heatmap", _boom)

        html = generate_sensitivity_report_html(all_results)

        assert "Summary Statistics" in html
        assert "<img" not in html

        expected_sections = [
            "1D Sensitivity: fast_period",
            "1D Sensitivity: slow_period",
            "2D Sensitivity: fast_period vs slow_period",
            "Parameter Interactions",
        ]
        for section in expected_sections:
            assert f"<h3>{section}</h3>" in html, f"Missing <h3> for section: {section}"

    def test_generate_sensitivity_report_html_headings_per_section_matplotlib_unavailable(
        self, monkeypatch
    ):
        """Each documented section gets an <h3> when matplotlib is unavailable.

        Setting MATPLOTLIB_AVAILABLE=False simulates the optional dependency
        not being installed. The report must still document every section with
        an <h3> heading and include the summary table, with no <img> tags.
        """
        from quant_trading.optimization import sensitivity

        all_results = [
            {"params": {"fast_period": 5, "slow_period": 20}, "score": 1.5},
            {"params": {"fast_period": 10, "slow_period": 20}, "score": 2.0},
            {"params": {"fast_period": 5, "slow_period": 30}, "score": 1.0},
            {"params": {"fast_period": 10, "slow_period": 30}, "score": 1.8},
        ]

        monkeypatch.setattr(sensitivity, "MATPLOTLIB_AVAILABLE", False)

        html = generate_sensitivity_report_html(all_results)

        assert "Summary Statistics" in html
        assert "<img" not in html

        expected_sections = [
            "1D Sensitivity: fast_period",
            "1D Sensitivity: slow_period",
            "2D Sensitivity: fast_period vs slow_period",
            "Parameter Interactions",
        ]
        for section in expected_sections:
            assert f"<h3>{section}</h3>" in html, f"Missing <h3> for section: {section}"

    def test_generate_sensitivity_report_html_single_param_only_1d_sections(self, monkeypatch):
        """With a single parameter only 1D sections are documented."""
        from quant_trading.optimization import sensitivity

        all_results = [
            {"params": {"fast_period": 5}, "score": 1.5},
            {"params": {"fast_period": 10}, "score": 2.0},
        ]

        def _boom(*args, **kwargs):
            raise ValueError("chart failure")

        monkeypatch.setattr(sensitivity, "create_1d_sensitivity_plot", _boom)
        monkeypatch.setattr(sensitivity, "create_2d_sensitivity_heatmap", _boom)
        monkeypatch.setattr(sensitivity, "create_parameter_interaction_heatmap", _boom)

        html = generate_sensitivity_report_html(all_results, param_names=["fast_period"])

        assert "Summary Statistics" in html
        assert "<img" not in html
        assert "<h3>1D Sensitivity: fast_period</h3>" in html
        assert "2D Sensitivity" not in html
        assert "Parameter Interactions" not in html
