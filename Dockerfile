# Slim Debian image with the Apify SDK for Python preinstalled. No headless
# browser: Flashscore's data comes from two keyless HTTP APIs, and the one
# host that checks the TLS stack (www.flashscore.com, used only for match
# pages) is cleared by curl_cffi's Chrome impersonation. See docs/architecture.md.
FROM apify/actor-python:3.13

COPY --chown=myuser:myuser requirements.txt ./

RUN echo "Python version:" \
    && python --version \
    && echo "Installing dependencies from requirements.txt:" \
    && pip install --no-cache-dir -r requirements.txt \
    && echo "All installed Python packages:" \
    && pip freeze

COPY --chown=myuser:myuser . ./

CMD ["python3", "-m", "src"]
