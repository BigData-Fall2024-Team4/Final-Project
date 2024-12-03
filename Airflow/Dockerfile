FROM apache/airflow:2.10.2

USER root

# Install system dependencies and libraries
RUN apt-get update -o Acquire::Check-Valid-Until=false -o Acquire::Check-Date=false && \
    apt-get install -y \
    # PDF and image processing dependencies
    poppler-utils \
    tesseract-ocr \
    libtesseract-dev \
    libleptonica-dev \
    # Java and JRE dependencies
    openjdk-17-jre \
    openjdk-17-jdk \
    # Chrome and Selenium dependencies
    chromium \
    chromium-driver \
    xvfb \
    # Additional system libraries
    libgl1-mesa-glx \
    libglib2.0-0 \
    # Other utilities
    wget \
    unzip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create directories for Chrome and Java
RUN mkdir -p /opt/chrome /opt/java && \
    chmod -R 777 /opt/chrome /opt/java

# Set Java environment variables
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH=$PATH:$JAVA_HOME/bin

USER airflow

# Install Python packages with specific versions for compatibility
RUN pip install --no-cache-dir \
    # Base dependencies
    pandas \
    boto3 \
    requests \
    python-dateutil \
    tqdm \
    # PDF processing
    PyPDF2 \
    pdf2image \
    pytesseract \
    Pillow \
    PyMuPDF \
    tabula-py \
    # Web scraping and automation
    selenium \
    webdriver_manager \
    # First install langchain dependencies
    pydantic<3.0.0,>=1.7.4 \
    dataclasses-json<0.6.0 \
    PyYAML>=5.4.1 \
    SQLAlchemy<3,>=1.4 \
    # Then install langchain and related packages
    langchain-core==0.1.23 \
    langchain==0.1.0 \
    langchain-community==0.0.20 \
    openai \
    pinecone-client \
    sentence_transformers \
    # Cryptography and security
    cryptography \
    ntplib \
    # Additional utilities
    openpyxl \
    python-dotenv \
    xlrd \
    xlwt

# Set environment variables
ENV PYTHONPATH=/opt/airflow/dags \
    DISPLAY=:99 \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    CHROME_BINARY_PATH=/usr/bin/chromium \
    AWS_DEFAULT_REGION=us-east-1 \
    TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata

# Add a verification step to ensure langchain is installed correctly
RUN python -c "from langchain.text_splitter import RecursiveCharacterTextSplitter; print('Langchain successfully installed')"

# Start Xvfb (Virtual Framebuffer X Server) for headless browser
RUN Xvfb :99 -screen 0 1920x1080x24 > /dev/null 2>&1 &

WORKDIR /opt/airflow

# Ensure these Python packages are installed
RUN pip install --no-cache-dir \
    jpype1 \
    xvfbwrapper