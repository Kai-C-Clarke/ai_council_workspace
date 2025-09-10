from setuptools import setup, find_packages

setup(
    name="ai_council_workspace",
    version="0.1.0",
    description="A collaborative framework enabling persistent AI-to-AI communication and task management across session boundaries",
    author="Kai-C-Clarke", 
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.104.1",
        "uvicorn>=0.24.0", 
        "websockets>=12.0",
        "pydantic>=2.5.0",
        "python-multipart>=0.0.6",
        "jinja2>=3.1.2",
        "redis>=5.0.1",
        "schedule>=1.2.0",
        "psutil>=5.9.6",
        "python-dotenv>=1.0.0"
    ],
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)