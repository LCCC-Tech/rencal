# Contributing to Weather Forecasting and Modelling

Thank you for your interest in contributing to The Low Carbon Contracts Company Weather Forecasting and Modelling project! This document provides guidelines and instructions for contributing.

## Code of Conduct

By participating in this project, you agree to abide by our Code of Conduct:
- Be respectful and inclusive
- Welcome newcomers and help them get started
- Focus on constructive criticism
- Accept responsibility and apologize when making mistakes

## How to Contribute

### Reporting Issues

Before creating an issue, please check if it already exists. When creating a new issue:

1. Use a clear and descriptive title
2. Provide a detailed description of the problem
3. Include steps to reproduce the issue
4. Specify your environment (OS, Python version, etc.)
5. Include relevant error messages and stack traces

### Suggesting Enhancements

Enhancement suggestions are welcome! Please:

1. Use a clear and descriptive title
2. Provide a detailed description of the proposed enhancement
3. Explain why this enhancement would be useful
4. Include examples of how it would work

### Pull Requests

1. **Fork the repository** and create your branch from `main`
2. **Follow the coding standards** (see below)
3. **Write tests** for your changes
4. **Update documentation** as needed
5. **Ensure all tests pass** before submitting
6. **Submit a pull request** with a clear description

#### Pull Request Process

1. Update the README.md with details of changes if applicable
2. Ensure any install or build dependencies are removed
3. Increase version numbers following [Semantic Versioning](https://semver.org/)
4. The PR will be merged after review and approval from maintainers

## Development Setup

### Setting up your environment

```bash
# Clone your fork
git clone https://github.com/your-username/weather.git
cd weather

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e .
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=weather --cov-report=html

# Run specific test file
pytest tests/test_wind_models.py

# Run with verbose output
pytest -v
```

## Coding Standards

### Python Style Guide

- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/)
- Use meaningful variable and function names
- Add type hints where appropriate
- Maximum line length: 100 characters

### Code Formatting

We use `black` for code formatting and `isort` for import sorting:

```bash
# Format code
black weather/ tests/

# Sort imports
isort weather/ tests/

# Check without modifying
black --check weather/ tests/
isort --check-only weather/ tests/
```

### Docstrings

Use Google-style docstrings:

```python
def calculate_wind_power(wind_speed: float, turbine_capacity: float) -> float:
    """Calculate wind power output based on wind speed.
    
    Args:
        wind_speed: Wind speed in m/s
        turbine_capacity: Turbine capacity in MW
        
    Returns:
        Power output in MW
        
    Raises:
        ValueError: If wind_speed is negative
    """
```

### Commit Messages

- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit first line to 72 characters
- Reference issues and pull requests when relevant

Example:
```
Add wind speed calibration module

- Implement Weibull distribution fitting
- Add validation against historical data
- Include unit tests for edge cases

Closes #123
```

## Testing Guidelines

### Writing Tests

- Write unit tests for all new functionality
- Aim for >80% code coverage
- Use descriptive test names
- Include edge cases and error conditions

### Test Structure

```python
import pytest
from weather.models import WindModel

class TestWindModel:
    def test_initialization(self):
        """Test model initialization with default parameters."""
        model = WindModel()
        assert model.horizon == 24
        
    def test_invalid_input_raises_error(self):
        """Test that invalid input raises appropriate error."""
        model = WindModel()
        with pytest.raises(ValueError):
            model.predict(wind_speed=-1)
```

## Documentation

### Code Documentation

- All public modules, functions, classes, and methods must have docstrings
- Update existing documentation when modifying code
- Include examples in docstrings where helpful

### User Documentation

- Update README.md for significant changes
- Add tutorials for new features in docs/tutorials/
- Update API documentation in docs/api/

## Release Process

1. Update version in `setup.py` and `__init__.py`
2. Update CHANGELOG.md
3. Create a release branch
4. Submit PR for review
5. After merge, tag the release
6. Build and publish to PyPI

## Getting Help

If you need help:

1. Check the [documentation](docs/)
2. Search existing [issues](https://github.com/LCCC/weather/issues)
3. Ask in discussions
4. Contact maintainers

## Recognition

Contributors will be recognized in:
- The AUTHORS file
- Release notes
- Project documentation

Thank you for contributing to The Low Carbon Contracts Company Weather Forecasting project!