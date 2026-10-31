import warnings

# Filter third-party warnings that are noisy in this environment
warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"yfinance.*")
warnings.filterwarnings("ignore", category=FutureWarning, module=r"yfinance.*")
warnings.filterwarnings("ignore", category=PendingDeprecationWarning, module=r"yfinance.*")
try:
    import pandas as _pd
    # Pandas4Warning may not exist in older pandas; ignore if missing
    _pd4 = getattr(_pd.errors, "Pandas4Warning", Warning)
    warnings.filterwarnings("ignore", category=_pd4, module=r"yfinance.*")
    warnings.filterwarnings("ignore", category=_pd4)
except (ImportError, AttributeError):
    pass

# General patterns
warnings.filterwarnings("ignore", message=r".*inplace keyword.*DataFrame\.rename.*")
warnings.filterwarnings("ignore", message=r".*Pandas4Warning.*")
