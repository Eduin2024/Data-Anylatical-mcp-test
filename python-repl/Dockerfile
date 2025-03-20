# Use official Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements files
COPY pyproject.toml uv.lock ./

# Install uv (Python package manager)
RUN pip install uv

# Create virtual environment
RUN uv venv .venv
ENV PATH="/app/.venv/bin:$PATH"

# Install dependencies directly from pyproject.toml
RUN uv pip install .

# Install commonly used packages
RUN uv pip install scikit-learn pandas numpy matplotlib

# Copy the rest of the application
COPY . .

# Command to run the server
CMD ["python", "server.py"] 