FROM python:3.11

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /code

# Install dependencies
COPY pyproject.toml poetry.lock /code/

# Final RUN command: Remove the lock file and let poetry resolve fresh dependencies.
RUN pip install --upgrade pip \
    && pip install "poetry==1.7.1" \
    && poetry config virtualenvs.create false \
    && rm poetry.lock \
    && poetry install --no-interaction --no-ansi

# Copy project
COPY ./ /code/

# Expose the application's port
EXPOSE 4000

# Run the application
COPY entrypoint.sh /app_entry/
RUN chmod +x /app_entry/entrypoint.sh
ENTRYPOINT ["/app_entry/entrypoint.sh"]
