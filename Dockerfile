# 1) Use official Playwright image (Ubuntu + Chromium + all deps already baked in)
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# 2) Match Lambda layout (optional but nice for consistency)
WORKDIR /var/task
ENV LAMBDA_TASK_ROOT=/var/task
ENV PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1

# 3) Copy requirements (your own deps ONLY; playwright is already in the base image)
COPY requirements.txt .

# 4) Install your Python deps + Lambda Runtime Interface Client
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir awslambdaric

# 5) Copy application code
COPY web_search_tool.py ${LAMBDA_TASK_ROOT}/
COPY browser_session.py ${LAMBDA_TASK_ROOT}/
COPY search_engine.py ${LAMBDA_TASK_ROOT}/
COPY content_scraper.py ${LAMBDA_TASK_ROOT}/
COPY user_agents.py ${LAMBDA_TASK_ROOT}/
COPY lambda_handler.py ${LAMBDA_TASK_ROOT}/
COPY config.py ${LAMBDA_TASK_ROOT}/
COPY resource_monitor.py ${LAMBDA_TASK_ROOT}/
COPY s3_uploader.py ${LAMBDA_TASK_ROOT}/

# 6) Lambda entrypoint via awslambdaric
#    Format: python -m awslambdaric <module>.<function>
CMD ["python", "-m", "awslambdaric", "lambda_handler.lambda_handler"]
